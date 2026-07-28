# -*- coding: utf-8 -*-
"""
[GMAIL]
=============================================================================
INGESTION DES ALERTES DE NON-CONFORMITE (NCR) REMONTEES PAR MAIL
=============================================================================

Eric T. signale les rejets et non-conformites par mail, jamais dans un
fichier structure. Ce module transforme ces alertes en donnee exploitable
dans FUSEAU pour que Marlene voie le probleme sur la ligne de commande
concernee sans avoir a fouiller sa boite mail.

Strategie : comme enrich_reception_sylob, on ecrit dans
achat.commande_enrichissement et jamais directement dans achat.commande ou
achat.qualite, qui sont rechargees en full-refresh chaque nuit.

Junior Tip : le ciblage exige un PO. La version precedente acceptait
"PO OU code article", ce qui marquait NON CONFORME toutes les lignes
historiques de l'article, tous fournisseurs et toutes commandes confondus,
sur la foi d'un seul mail. Un rejet qualite concerne une livraison precise,
donc une commande precise : sans PO, on refuse et on loggue plutot que de
polluer l'historique.

Usage :
    python -m src.scripts.gmail.load_email_ncr --file data/_ncr.json [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

from sqlalchemy import text

from app.database import get_engine
from src.scripts.gmail.parse_email_ncr import parse_email_ncr
from src.utils.logging_setup import setup_logging

logger = logging.getLogger(__name__)

SCHEMA = "achat"
SOURCE = "load_email_ncr"

# 'FAIL' et pas 'NON CONFORME' : c'est la valeur attendue par le reste de
# l'application (load.py, vue achat.v_qualite_fournisseur). Avec une valeur
# hors nomenclature, la ligne comptait dans nb_inspectes mais jamais dans
# nb_fail, ce qui sous-evaluait le taux d'echec du fournisseur.
RESULTAT_NON_CONFORME = "FAIL"

SQL_UPSERT = f"""
    INSERT INTO {SCHEMA}.commande_enrichissement
        (po_number, code_article, non_conformite, ncr_ref, resultat_inspection,
         source, maj_le)
    VALUES (:po_number, :code_article, :motif, :ncr_ref, :resultat, :source, NOW())
    ON CONFLICT (po_number, code_article) DO UPDATE
    SET non_conformite      = EXCLUDED.non_conformite,
        ncr_ref             = EXCLUDED.ncr_ref,
        resultat_inspection = EXCLUDED.resultat_inspection,
        source              = EXCLUDED.source,
        maj_le              = NOW()
"""


def load_ncr_data(ncr: dict[str, Any], dry_run: bool = False) -> dict[str, int]:
    """
    Enregistre une alerte NCR dans la table d'enrichissement FUSEAU.

    Args:
        ncr: alerte parsee par parse_email_ncr (po_number, code_article,
             ncr_ref, motif).
        dry_run: si True, valide l'alerte sans ecrire en base.

    Returns:
        Compteur {"enrichissements_ecrits"}.
    """
    po_number = ncr.get("po_number")
    if not po_number:
        logger.warning("[ATTENTION] NCR ignoree : aucun PO identifie dans le mail (%s).",
                       (ncr.get("motif") or "")[:80])
        return {"enrichissements_ecrits": 0}

    ncr_ref = ncr.get("ncr_ref") or "NCR-EMAIL"
    motif = ncr.get("motif") or "Rejet qualite"
    params = {
        "po_number": str(po_number).lstrip("0"),
        # Chaine vide = alerte au niveau du PO complet, la cle primaire de la
        # table d'enrichissement n'accepte pas de NULL.
        "code_article": (ncr.get("code_article") or "").strip(),
        "motif": motif,
        "ncr_ref": ncr_ref if len(ncr_ref) >= 20 else f"{ncr_ref} - {motif}",
        "resultat": RESULTAT_NON_CONFORME,
        "source": SOURCE,
    }

    if dry_run:
        logger.info("[INFO] [DRY-RUN] NCR %s sur PO=%s article=%s",
                    ncr_ref, params["po_number"], params["code_article"] or "(tout le PO)")
        return {"enrichissements_ecrits": 0}

    engine = get_engine()
    with engine.begin() as conn:
        res = conn.execute(text(SQL_UPSERT), params)

    logger.info("[SUCCES] NCR %s enregistree sur PO=%s article=%s.",
                ncr_ref, params["po_number"], params["code_article"] or "(tout le PO)")
    return {"enrichissements_ecrits": res.rowcount}


def load_ncr_batch(alertes: list[dict[str, Any]], dry_run: bool = False) -> dict[str, int]:
    """Traite une liste d'alertes NCR et agrege les compteurs."""
    total = 0
    for alerte in alertes:
        total += load_ncr_data(alerte, dry_run=dry_run)["enrichissements_ecrits"]
    logger.info("[SUCCES] %d alerte(s) NCR traitee(s), %d enrichissement(s) ecrit(s).",
                len(alertes), total)
    return {"enrichissements_ecrits": total}


def process_messages(messages: list[dict[str, Any]], dry_run: bool = False) -> int:
    """
    Chaine complete mail brut -> alerte NCR -> base, sur une liste de messages.

    C'est le point d'entree attendu par la tache planifiee : parse_email_ncr
    n'etait relie a aucun appelant, donc aucune non-conformite remontee par
    mail n'arrivait jamais jusqu'a FUSEAU.

    Args:
        messages: messages Gmail (subject, body, from_email, date).
        dry_run: si True, parse et journalise sans ecrire en base.
    Returns:
        Nombre d'alertes NCR reconnues.
    """
    alertes: list[dict[str, Any]] = []
    for msg in messages:
        alerte = parse_email_ncr(
            body=msg.get("body", ""),
            subject=msg.get("subject", ""),
            sender=msg.get("from_email", msg.get("from", "")),
            date_sent=msg.get("date", msg.get("date_info", "")),
        )
        if alerte:
            alertes.append(alerte)

    if not alertes:
        logger.info("[INFO] Aucune non-conformite detectee dans les %d message(s).", len(messages))
        return 0

    load_ncr_batch(alertes, dry_run=dry_run)
    return len(alertes)


def main() -> None:
    setup_logging()
    ap = argparse.ArgumentParser(description="Ingere des alertes NCR parsees depuis Gmail")
    ap.add_argument("--file", required=True,
                    help="JSON : alertes deja parsees, ou messages bruts avec --from-messages")
    ap.add_argument("--from-messages", action="store_true",
                    help="Le fichier contient des messages Gmail bruts a parser")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    contenu = json.loads(Path(args.file).read_text(encoding="utf-8-sig"))
    if isinstance(contenu, dict):
        contenu = [contenu]

    if args.from_messages:
        process_messages(contenu, dry_run=args.dry_run)
    else:
        load_ncr_batch(contenu, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
