# -*- coding: utf-8 -*-
"""
[ETL]
=============================================================================
LOADER GMAIL -> achat.ot_transport (zone EXPÉDITION, pattern A — décision 30/06)
=============================================================================

Upsert des enregistrements produits par `parse_bl.py` (ou `transform_maritime.py`,
même format de sortie) dans achat.ot_transport (PK n_conteneur).

- `n_bl`, `transitaire`, `n_facture`, `lieu_livraison`, `etd_reel` : UPSERT **COALESCE**
  inchangé -- un champ entrant NULL n'écrase jamais une valeur existante.
- `eta`, `date_livraison` : **historisés** depuis le 23/07 (décision spec
  `docs/20260722_FUSEAU_Spec_SuiviDatesETA_v1.md`, §2/§4) -- abandon du COALESCE,
  "la valeur la plus récemment TRANSMISE gagne" (préséance CHRONOLOGIQUE sur
  `date_transmission`, pas "le dernier load exécuté gagne"). Chaque changement de
  valeur est journalisé dans `achat.transport_evenement` (jamais remis à zéro,
  alimente `achat.v_ot_transport_suivi` pour les badges couleur ETA/livraison).
  Un record sans `date_transmission` est traité comme transmis "maintenant" (NOW()).

Provenance : source_fichier = 'gmail:<fichier>'.

Pourquoi ot_transport et pas achat.commande : commande est full-refresh (TRUNCATE)
par l'ETL Excel et migre vers le DWH Sylob V25 ; ot_transport survit. Les vues
v_previsionnel / v_retard_article fusionnent (COALESCE BL prioritaire). Voir
decisions_log/20260630_writepath_gmail_pattern_a.

⚠️ Jointure vue = commande.n_conteneur ↔ ot_transport.n_conteneur. Une ligne BL
n'enrichit le prévisionnel que si la commande porte déjà ce n_conteneur (fourni par
l'IMPORT Excel). Si le BL est en avance sur l'Excel, le merge attend la MAJ Excel.

Auth : config/.env via Config (PG_USER=platform_team sur poste Marlène). VPN requis.

Usage (depuis la racine, VPN actif) :
    python -m src.scripts.gmail.load_ot_gmail --check
    python -m src.scripts.gmail.load_ot_gmail --file data/PJ/_parsed.json --dry-run
    python -m src.scripts.gmail.load_ot_gmail --file data/PJ/_parsed.json        # COMMIT

Entrée : JSON liste (sortie de parse_bl). Clés utilisées :
    n_conteneur (obligatoire), n_bl, etd_reel, eta, transitaire, n_facture,
    lieu_livraison, source_fichier. Les autres clés (po_numbers, ...) sont ignorées.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone

from sqlalchemy import text

from app.database import get_engine
from src.utils.config_manager import Config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s -- %(message)s",
)
logger = logging.getLogger("load_ot_gmail")

# Colonnes texte et colonnes date (cast SQL explicite ::date pour ces dernières).
TEXT_FIELDS = ("n_bl", "transitaire", "n_facture", "lieu_livraison")
DATE_FIELDS = ("etd_reel", "eta")
ALL_FIELDS = TEXT_FIELDS + DATE_FIELDS

# Champs historises (spec ETA 20260722) : preseance chronologique + evenement de
# changement dans achat.transport_evenement, au lieu du simple COALESCE.
TRACKED_FIELDS = ("eta", "date_livraison")

UPSERT_SQL = """
INSERT INTO achat.ot_transport
    (n_conteneur, n_bl, etd_reel, eta, date_livraison, eta_maj_le, date_livraison_maj_le,
     transitaire, n_facture, lieu_livraison, source_fichier, charge_le)
VALUES
    (:n_conteneur, :n_bl, CAST(:etd_reel AS date), CAST(:eta AS date), CAST(:date_livraison AS timestamp),
     CAST(:eta_maj_le AS timestamp), CAST(:date_livraison_maj_le AS timestamp),
     :transitaire, :n_facture, :lieu_livraison, :source_fichier, NOW())
ON CONFLICT (n_conteneur) DO UPDATE SET
    n_bl                   = COALESCE(EXCLUDED.n_bl,           achat.ot_transport.n_bl),
    etd_reel               = COALESCE(EXCLUDED.etd_reel,       achat.ot_transport.etd_reel),
    eta                    = EXCLUDED.eta,
    date_livraison         = EXCLUDED.date_livraison,
    eta_maj_le             = EXCLUDED.eta_maj_le,
    date_livraison_maj_le  = EXCLUDED.date_livraison_maj_le,
    transitaire            = COALESCE(EXCLUDED.transitaire,    achat.ot_transport.transitaire),
    n_facture              = COALESCE(EXCLUDED.n_facture,      achat.ot_transport.n_facture),
    lieu_livraison         = COALESCE(EXCLUDED.lieu_livraison, achat.ot_transport.lieu_livraison),
    source_fichier         = EXCLUDED.source_fichier,
    charge_le              = NOW()
"""

# L'id est laisse a la sequence native de la table : le calculer par
# (SELECT MAX(id) + 1) provoquait une collision de cle primaire des que deux
# executions se croisaient (tache planifiee et lancement manuel).
EVENT_SQL = """
INSERT INTO achat.transport_evenement
    (cle_idempotence, n_conteneur, source, date_info, type, champ_date,
     ancienne_valeur, nouvelle_valeur, texte)
VALUES
    (:cle, :n_conteneur, :source, CAST(:date_info AS date), 'chgt_date', :champ_date,
     CAST(:ancienne_valeur AS date), CAST(:nouvelle_valeur AS date), :texte)
ON CONFLICT (cle_idempotence) DO NOTHING
"""


def check() -> int:
    """Lecture seule : connexion + colonnes réelles d'achat.ot_transport."""
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
        n = conn.execute(
            text(f"SELECT COUNT(*) FROM {Config.PG_SCHEMA}.ot_transport")
        ).scalar()
        cols = conn.execute(
            text(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_schema = :s AND table_name = 'ot_transport' "
                "ORDER BY ordinal_position"
            ),
            {"s": Config.PG_SCHEMA},
        ).fetchall()
    logger.info("[OK] %s.ot_transport = %d conteneur(s).", Config.PG_SCHEMA, n)
    for name, dtype in cols:
        logger.info("       - %-16s %s", name, dtype)
    return 0


def _row_params(rec: dict) -> dict | None:
    conteneur = str(rec.get("n_conteneur") or "").strip()
    if not conteneur:
        logger.warning("Ignoré (n_conteneur manquant -> niveau PO, voir apply_etd_eta) : %s",
                       {k: rec.get(k) for k in ("n_bl", "po_numbers")})
        return None
    params = {"n_conteneur": conteneur}
    for f in ALL_FIELDS:
        val = rec.get(f)
        params[f] = (str(val).strip() or None) if isinstance(val, str) else val
    fichier = rec.get("source_fichier")
    params["source_fichier"] = f"gmail:{fichier}" if fichier else "gmail"
    dt = rec.get("date_transmission")
    params["date_transmission"] = (str(dt).strip() or None) if isinstance(dt, str) else dt
    params["date_livraison"] = rec.get("date_livraison")
    return params


def _resolve_tracked(conn, params: dict) -> list[dict]:
    """
    Applique la préséance chronologique sur les champs historisés (eta, date_livraison)
    et prépare les événements de changement à insérer dans achat.transport_evenement.

    Junior Tip : on ne peut pas se contenter d'écraser avec la valeur entrante (ce
    serait "le dernier load exécuté gagne") -- la spec ETA §4 demande explicitement
    "la valeur la plus récemment TRANSMISE gagne". On compare donc `date_transmission`
    (horodatage de la source, ex. date du fichier maritime) à la dernière transmission
    déjà appliquée (`<champ>_maj_le`, stockée en base) avant d'accepter la nouvelle valeur.

    Args:
        conn: connexion SQLAlchemy active (transaction en cours).
        params: dict de _row_params, MUTÉ en place (eta/date_livraison/*_maj_le finaux).
    Returns:
        Liste d'événements à insérer (dicts prêts pour EVENT_SQL), vide si rien n'a changé.
    """
    date_transmission = params.get("date_transmission") or datetime.now(timezone.utc).isoformat()
    current = conn.execute(text(
        "SELECT eta, date_livraison, eta_maj_le, date_livraison_maj_le "
        "FROM achat.ot_transport WHERE n_conteneur = :c"
    ), {"c": params["n_conteneur"]}).fetchone()

    events = []
    for champ in TRACKED_FIELDS:
        incoming = params.get(champ)
        if incoming is None:
            # Rien de transmis pour ce champ -> on garde la valeur courante telle quelle.
            if current is not None:
                idx = 0 if champ == "eta" else 1
                maj_idx = 2 if champ == "eta" else 3
                params[champ] = current[idx]
                params[f"{champ}_maj_le"] = current[maj_idx]
            else:
                params[f"{champ}_maj_le"] = None
            continue

        if current is None:
            # Premiere transmission pour ce conteneur : accepte sans evenement (pas d'"ancienne_valeur").
            params[f"{champ}_maj_le"] = date_transmission
            continue

        idx = 0 if champ == "eta" else 1
        maj_idx = 2 if champ == "eta" else 3
        valeur_actuelle, maj_le_actuel = current[idx], current[maj_idx]

        if maj_le_actuel is not None and str(date_transmission) < str(maj_le_actuel):
            # Transmission plus ancienne que ce qu'on a deja applique -> ignoree (spec §4).
            logger.info("conteneur %s : transmission %s plus ancienne que %s deja appliquee pour %s -- ignoree.",
                        params["n_conteneur"], date_transmission, maj_le_actuel, champ)
            params[champ] = valeur_actuelle
            params[f"{champ}_maj_le"] = maj_le_actuel
            continue

        params[f"{champ}_maj_le"] = date_transmission
        if valeur_actuelle is not None and str(valeur_actuelle) != str(incoming):
            cle = f"transport:{params['n_conteneur']}:{champ}:{incoming}:{date_transmission}:{params['source_fichier']}"
            events.append({
                "cle": cle, "n_conteneur": params["n_conteneur"], "source": params["source_fichier"],
                "date_info": date_transmission, "champ_date": champ,
                "ancienne_valeur": valeur_actuelle, "nouvelle_valeur": incoming,
                "texte": f"{champ} : {valeur_actuelle} -> {incoming}",
            })
    return events


def load(records: list[dict], dry_run: bool) -> int:
    engine = get_engine()
    total = 0
    n_events = 0
    with engine.begin() as conn:
        for rec in records:
            params = _row_params(rec)
            if not params:
                continue
            events = _resolve_tracked(conn, params)
            conn.execute(text(UPSERT_SQL), params)
            for ev in events:
                conn.execute(text(EVENT_SQL), ev)
                n_events += 1
                logger.info("conteneur %s : changement %s (%s -> %s)",
                            params["n_conteneur"], ev["champ_date"], ev["ancienne_valeur"], ev["nouvelle_valeur"])
            logger.info("conteneur %s %s | bl=%s etd=%s eta=%s livraison=%s",
                        params["n_conteneur"],
                        "(simulé)" if dry_run else "upsert",
                        params.get("n_bl"), params.get("etd_reel"), params.get("eta"), params.get("date_livraison"))
            total += 1
        if dry_run:
            logger.info("[DRY-RUN] %d conteneur(s), %d evenement(s) -- ROLLBACK, rien n'est écrit.", total, n_events)
            conn.rollback()
        else:
            logger.info("[COMMIT] %d conteneur(s) upsert dans %s.ot_transport, %d evenement(s) de changement historise(s).",
                        total, Config.PG_SCHEMA, n_events)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Upsert Gmail -> achat.ot_transport (pattern A).")
    ap.add_argument("--check", action="store_true", help="Lecture seule : connexion + colonnes.")
    ap.add_argument("--dry-run", action="store_true", help="Applique puis ROLLBACK.")
    ap.add_argument("--data", type=str, default="", help="JSON (liste) en argument.")
    ap.add_argument("--file", type=str, default="", help="Chemin d'un fichier JSON (liste).")
    args = ap.parse_args()

    if args.check:
        return check()

    if args.file:
        with open(args.file, "r", encoding="utf-8-sig") as fh:
            raw = fh.read()
    else:
        raw = args.data or sys.stdin.read()
    if not raw.strip():
        logger.error("Aucune donnée fournie (--data, --file ou stdin).")
        return 2
    try:
        records = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("JSON invalide : %s", exc)
        return 2
    if not isinstance(records, list):
        logger.error("Le JSON doit être une liste d'objets.")
        return 2

    return load(records, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
