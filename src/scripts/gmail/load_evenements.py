# -*- coding: utf-8 -*-
r"""
[GMAIL] Routeur d'événements métier extraits des threads -> tables achat.* par sujet
=====================================================================================
Remplace le fourre-tout achat.commande_annotation par 4 tables structurées
(créées par sql/20260722_tables_evenements_metier.sql) :
  - qualite_decision    (domaine="qualite")
  - transport_evenement (domaine="transport")
  - commerce_decision   (domaine="commerce")
  - design_evenement    (domaine="design")

Chaque enregistrement JSON porte un `domaine` + les colonnes communes
(po_number, code_article, n_conteneur, thread_id, acteur, source, date_info, texte)
+ les colonnes propres au sujet. Idempotent via cle_idempotence (ON CONFLICT DO NOTHING),
sauf la réservation d'inspection DEKRA, mise à jour quand elle est reportée.
PO, décision, type et stade sont normalisés avant le calcul de la clé.

Usage : python -m src.scripts.gmail.load_evenements --file data\_evenements.json [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import sys

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from app.database import get_engine  # noqa: E402
from src.utils.logging_setup import setup_logging  # noqa: E402

logger = logging.getLogger(__name__)

COMMON = ["po_number", "code_article", "n_conteneur", "thread_id",
          "acteur", "source", "date_info", "texte"]

# domaine -> (table, colonnes spécifiques, champ discriminant pour la clé)
ROUTES = {
    "qualite":   ("achat.qualite_decision",    ["decision", "motif", "stade"],                         "decision"),
    "transport": ("achat.transport_evenement", ["type", "champ_date", "ancienne_valeur",
                                                 "nouvelle_valeur", "motif"],                            "type"),
    "commerce":  ("achat.commerce_decision",   ["type", "contenu"],                                     "type"),
    "design":    ("achat.design_evenement",    ["type", "statut"],                                      "type"),
}


# Champs ajoutés au discriminant de la clé d'idempotence quand ils sont
# présents. Sans eux, l'ETA et la date de livraison issues du même mail
# partagent thread_id, domaine, type et PO : la clé est identique et le second
# événement est silencieusement avalé par le ON CONFLICT DO NOTHING.
# Réservé aux domaines autres que la qualité : sur une décision qualité, la
# tâche Cowork remplit ces champs au hasard (3 doublons mesurés le 06/10/2026).
DISCRIMINANTS_SECONDAIRES = ("n_conteneur", "champ_date", "nouvelle_valeur")

# Stades qualité ramenés à une forme unique. Le prompt Cowork écrit tantôt
# "FRI", tantôt "inspection" pour la même inspection finale DEKRA ; tantôt
# "RECEP", tantôt "reception". Les stades hors de cette table sont gardés en
# minuscules (echantillon, plan, reprise...).
STADES_CANONIQUES = {
    "MAT": "MAT", "SP": "SP", "BAT": "BAT",
    "FRI": "inspection", "INSPECTION": "inspection",
    "RECEP": "reception", "RECEPTION": "reception",
}

# Préfixe de la clé fournie par le prompt Cowork pour une réservation
# d'inspection DEKRA : "dekra_resa|<thread_id>|<po_number>".
PREFIXE_RESERVATION = "dekra_resa|"
DECISION_RESERVEE = "reservee"


def normaliser_po(po: object) -> str | None:
    """
    PO sur 8 chiffres quand il n'est fait que de chiffres.

    Junior Tip : le même PO arrivait écrit "00187324" et "187324" selon le mail.
    Deux écritures donnaient deux clés d'idempotence, donc deux lignes pour une
    seule décision (38 doublons mesurés le 06/10/2026). zfill ne tronque jamais
    un PO plus long ; un PO non numérique ("PO142645") est seulement nettoyé.
    """
    if po is None:
        return None
    valeur = str(po).strip()
    if not valeur:
        return None
    return valeur.zfill(8) if valeur.isdigit() else valeur


def normaliser_stade(stade: object) -> str | None:
    """Stade canonique : MAT/SP/BAT en majuscules, FRI -> inspection, RECEP -> reception."""
    if stade is None:
        return None
    valeur = str(stade).strip()
    if not valeur:
        return None
    return STADES_CANONIQUES.get(valeur.upper(), valeur.lower())


def _minuscule(valeur: object) -> str | None:
    """strip().lower(), None si vide."""
    if valeur is None:
        return None
    nettoyee = str(valeur).strip().lower()
    return nettoyee or None


def normaliser(rec: dict) -> dict:
    """
    Copie normalisée d'un enregistrement, appliquée AVANT le calcul de la clé
    et AVANT l'insertion : la clé et les colonnes restent ainsi cohérentes.

    Une clé de réservation fournie voit son segment PO normalisé, pour qu'un
    report annoncé avec "187324" retombe sur la réservation "00187324".
    """
    out = dict(rec)
    out["domaine"] = _minuscule(rec.get("domaine")) or ""
    out["po_number"] = normaliser_po(rec.get("po_number"))
    code = rec.get("code_article")
    out["code_article"] = (str(code).strip() or None) if code is not None else None
    for champ in ("decision", "type"):
        if champ in rec:
            out[champ] = _minuscule(rec.get(champ))
    if "stade" in rec:
        out["stade"] = normaliser_stade(rec.get("stade"))
    fournie = str(rec.get("cle_idempotence") or "").strip()
    if fournie.startswith(PREFIXE_RESERVATION):
        parties = fournie.split("|")
        if len(parties) >= 3:
            parties[2] = normaliser_po(parties[2]) or ""
        fournie = "|".join(parties)
    out["cle_idempotence"] = fournie or None
    return out


def _cle(rec: dict, discr: str) -> str:
    """
    Construit la clé d'idempotence d'un événement DÉJÀ normalisé (normaliser()).

    Si le parser a déjà fourni une clé (cas de parse_email_eta, qui connaît le
    contexte métier mieux que ce routeur générique), on la respecte.

    Qualité : thread_id|qualite|decision|po_number|code_article|stade.
    Le stade fait partie de la clé : sans lui, "MAT conforme" puis "SP conforme"
    sur le même PO dans un même fil partageaient la clé et la décision SP était
    avalée en silence. Cette formule est recopiée en SQL dans
    sql/20261008_dedoublonnage_qualite_decision.sql : les deux doivent rester
    identiques.

    Autres domaines : thread_id|domaine|discriminant|po_number|code_article
    + DISCRIMINANTS_SECONDAIRES (inchangé).

    Args:
        rec: enregistrement d'événement normalisé.
        discr: nom du champ discriminant propre au domaine (decision, type...).
    Returns:
        Clé stable, rejouable sans créer de doublon.
    """
    fournie = rec.get("cle_idempotence")
    if fournie:
        return str(fournie)
    parties = [
        rec.get("thread_id") or "?", rec.get("domaine") or "?",
        str(rec.get(discr) or ""), rec.get("po_number") or "",
        rec.get("code_article") or "",
    ]
    if rec.get("domaine") == "qualite":
        parties.append(rec.get("stade") or "")
    else:
        parties += [str(rec.get(champ) or "") for champ in DISCRIMINANTS_SECONDAIRES]
    return "|".join(parties)


def sql_insertion(table: str, col_list: list[str], rec: dict) -> str:
    """
    Requête d'insertion d'un événement normalisé.

    Cas général : ON CONFLICT DO NOTHING, rejouer un mail ne change rien.
    Réservation d'inspection DEKRA (decision "reservee") : une réservation peut
    être reportée. Le mail suivant porte la même clé et doit METTRE À JOUR la
    date prévue, pas être ignoré. La clause WHERE ... IS DISTINCT FROM évite de
    réécrire une ligne identique quand le même mail est rejoué.
    """
    placeholders = ", ".join(f":{c}" for c in col_list)
    base = f"INSERT INTO {table} AS t ({', '.join(col_list)}) VALUES ({placeholders}) "
    if rec.get("domaine") == "qualite" and rec.get("decision") == DECISION_RESERVEE:
        return base + (
            "ON CONFLICT (cle_idempotence) DO UPDATE SET "
            "date_info = EXCLUDED.date_info, motif = EXCLUDED.motif, texte = EXCLUDED.texte "
            "WHERE (t.date_info, t.motif, t.texte) "
            "IS DISTINCT FROM (EXCLUDED.date_info, EXCLUDED.motif, EXCLUDED.texte)"
        )
    return base + "ON CONFLICT (cle_idempotence) DO NOTHING"


def load(records: list[dict], dry_run: bool = False) -> None:
    """
    Route les événements vers leur table métier.

    Junior Tip : le mode dry-run sort AVANT get_engine(). Sinon un simple
    "qu'est-ce que ce mail produirait ?" exigeait le VPN et la connexion au
    DWH, ce qui rendait les tests inexécutables hors du réseau du bureau.
    """
    if dry_run:
        _log_dry_run(records)
        return

    engine = get_engine()
    stats: dict[str, int] = {}
    ignored = 0
    inchanges = 0
    with engine.begin() as conn:
        for brut in records:
            rec = normaliser(brut)
            dom = rec["domaine"]
            if dom not in ROUTES:
                ignored += 1
                logger.warning("[ATTENTION] Ignoré (domaine inconnu '%s') : %s",
                               dom, (rec.get("texte") or "")[:60])
                continue
            table, spec_cols, discr = ROUTES[dom]
            cols = COMMON + spec_cols
            payload = {k: rec.get(k) for k in cols}
            payload["cle_idempotence"] = _cle(rec, discr)
            col_list = ["cle_idempotence"] + cols
            # L'id est laissé à la séquence native de la table. Le calculer par
            # (SELECT MAX(id) + 1) court-circuitait la séquence et provoquait
            # une collision de clé primaire dès que deux exécutions se
            # croisaient (tâche planifiée et lancement manuel). Les séquences
            # ont été recalées par sql/20260728_commande_enrichissement.sql.
            res = conn.execute(text(sql_insertion(table, col_list, rec)), payload)
            stats[dom] = stats.get(dom, 0) + 1
            if res.rowcount == 0:
                inchanges += 1
    logger.info("[SUCCES] %s ; déjà présents ou inchangés=%d ; ignorés=%d",
                ", ".join(f"{k}={v}" for k, v in stats.items()) or "0 enregistrement",
                inchanges, ignored)


def _log_dry_run(records: list[dict]) -> None:
    """Simule le routage sans aucun accès base, pour tester un parsing hors VPN."""
    stats: dict[str, int] = {}
    ignored = 0
    for brut in records:
        rec = normaliser(brut)
        dom = rec["domaine"]
        if dom not in ROUTES:
            ignored += 1
            logger.warning("[ATTENTION] Ignoré (domaine inconnu '%s') : %s",
                           dom, (rec.get("texte") or "")[:60])
            continue
        table, _, discr = ROUTES[dom]
        logger.info("[INFO] (dry-run) -> %s | %s", table, _cle(rec, discr))
        stats[dom] = stats.get(dom, 0) + 1
    logger.info("[INFO] [DRY-RUN] %s ; ignorés=%d",
                ", ".join(f"{k}={v}" for k, v in stats.items()) or "0 enregistrement", ignored)


def main() -> None:
    setup_logging()
    ap = argparse.ArgumentParser(description="Route les événements Gmail -> tables achat.* par sujet")
    ap.add_argument("--file", required=True, help="JSON (liste d'événements avec 'domaine')")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    records = json.loads(Path(args.file).read_text(encoding="utf-8-sig"))
    if isinstance(records, dict):
        records = [records]
    logger.info("%d enregistrement(s) à router (dry_run=%s)", len(records), args.dry_run)
    load(records, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
