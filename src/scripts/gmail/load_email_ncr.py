"""
Module de chargement BDD des alertes de non-conformités et rejets issus de mails.

Ce script ingère les données extraites par parse_email_ncr.py et met à jour
la table 'achat.qualite' (colonne ncr et resultat_inspection) et la table
'achat.commande' (colonne non_conformite).
"""

import logging
from typing import Any, Dict
from sqlalchemy import text
from app.database import get_engine

SCHEMA = "achat"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def load_ncr_data(ncr: Dict[str, Any]) -> Dict[str, int]:
    """Ingère une alerte NCR dans la base de données FUSEAU.

    Args:
        ncr (Dict[str, Any]): Données NCR parsées (po_number, code_article, ncr_ref, motif, etc.).

    Returns:
        Dict[str, int]: Compteur d'enregistrements mis à jour.
    """
    po_number = ncr.get("po_number")
    code_article = ncr.get("code_article")
    ncr_ref = ncr.get("ncr_ref", "NCR-EMAIL")
    motif = ncr.get("motif", "Rejet qualité")

    if not po_number and not code_article:
        logger.warning("[ATTENTION] Impossible d'ingérer une NCR sans PO_NUMBER ni CODE_ARTICLE.")
        return {"qualite_updated": 0, "commande_updated": 0}

    engine = get_engine()
    po_clean = str(po_number).lstrip('0') if po_number else None

    stats = {"qualite_updated": 0, "commande_updated": 0}

    # 1. Update qualite
    update_qualite = text(f"""
        UPDATE {SCHEMA}.qualite
        SET 
            ncr = :ncr_ref,
            resultat_inspection = 'NON CONFORME',
            charge_le = NOW()
        WHERE LTRIM(TRIM(po_number::text), '0') = :po_clean
           OR (:code_article IS NOT NULL AND code_article = :code_article)
    """)

    # 2. Update commande
    update_commande = text(f"""
        UPDATE {SCHEMA}.commande
        SET 
            non_conformite = :motif,
            updated_at = NOW()
        WHERE LTRIM(TRIM(po_number::text), '0') = :po_clean
           OR (:code_article IS NOT NULL AND code_article = :code_article)
    """)

    with engine.connect() as conn:
        try:
            res_q = conn.execute(update_qualite, {
                "po_clean": po_clean,
                "code_article": code_article,
                "ncr_ref": f"{ncr_ref} - {motif}" if len(ncr_ref) < 20 else ncr_ref,
            })
            stats["qualite_updated"] = res_q.rowcount

            res_c = conn.execute(update_commande, {
                "po_clean": po_clean,
                "code_article": code_article,
                "motif": motif,
            })
            stats["commande_updated"] = res_c.rowcount

            conn.commit()
            logger.info(
                f"[SUCCÈS] NCR ingérée pour PO={po_number}/Article={code_article} : "
                f"{res_q.rowcount} fiches qualité et {res_c.rowcount} commandes affectées."
            )
            return stats
        except Exception as e:
            logger.error(f"[ERREUR] Échec de l'ingestion NCR : {e}")
            raise


if __name__ == "__main__":
    sample_ncr = {
        "po_number": "181325",
        "code_article": None,
        "ncr_ref": "NCR2026-04",
        "decision": "NON CONFORME",
        "motif": "[Décision Eric T.] Piqûres de rouille observées lors des tests labo.",
        "expediteur": "eric.tarrerias@tb-groupe.fr",
    }
    load_ncr_data(sample_ncr)
