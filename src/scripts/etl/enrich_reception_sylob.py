"""
Module d'enrichissement et rapprochement des réceptions physiques réelles Sylob.

Ce script parcourt la table Sylob 'public.receptions_detaillees2' pour extraire les dates
réelles de réception en magasin/dépôt et les rapprocher avec la table FUSEAU 'achat.commande'
et l'onglet Qualité 'achat.qualite'.

Règles métier :
1. N° PO normalisé par nettoyage des zéros de tête LTRIM(TRIM(...), '0').
2. Mise à jour de 'date_reception_sylob' et 'date_livraison' sur 'achat.commande'.
3. Basculement automatique du statut de la commande à 'Livrée' lorsque la réception Sylob est confirmée.
4. Mise à jour du statut de réception dans 'achat.qualite'.
"""

import logging
from typing import Dict
from sqlalchemy import text
from app.database import get_engine

SCHEMA = "achat"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def enrich_receptions_sylob() -> Dict[str, int]:
    """Extrait les réceptions réelles Sylob et effectue le rapprochement global avec achat.commande et achat.qualite.

    Returns:
        Dict[str, int]: Compteur des commandes et fiches qualité enrichies.
    """
    logger.info("[INFO] Début du rapprochement des réceptions réelles Sylob...")
    engine = get_engine()

    update_cmd_sql = text(f"""
        UPDATE {SCHEMA}.commande
        SET 
            date_reception_sylob = s.date_reception_sylob,
            date_livraison = COALESCE(date_livraison, s.date_reception_sylob),
            statut = CASE 
                WHEN statut IN ('CLOTUREE', 'Payée', 'Paye') THEN statut 
                ELSE 'Livrée' 
            END,
            updated_at = NOW()
        FROM (
            SELECT 
                LTRIM(TRIM(r.commande_numero_de_la_commande::text), '0') AS po_clean,
                MAX(r.ligne_receptionnee_le)                              AS date_reception_sylob
            FROM public.receptions_detaillees2 r
            WHERE r.commande_numero_de_la_commande IS NOT NULL
              AND r.ligne_receptionnee_le IS NOT NULL
            GROUP BY LTRIM(TRIM(r.commande_numero_de_la_commande::text), '0')
        ) s
        WHERE LTRIM(TRIM(commande.po_number::text), '0') = s.po_clean;
    """)

    update_qualite_sql = text(f"""
        UPDATE {SCHEMA}.qualite
        SET 
            date_reception_sylob = s.date_reception_sylob,
            reception = CASE 
                WHEN qualite.reception IS NULL OR qualite.reception IN ('En attente', '', '—') THEN 'Réceptionné Sylob'
                ELSE qualite.reception
            END
        FROM (
            SELECT 
                LTRIM(TRIM(r.commande_numero_de_la_commande::text), '0') AS po_clean,
                MAX(r.ligne_receptionnee_le)                              AS date_reception_sylob
            FROM public.receptions_detaillees2 r
            WHERE r.commande_numero_de_la_commande IS NOT NULL
              AND r.ligne_receptionnee_le IS NOT NULL
            GROUP BY LTRIM(TRIM(r.commande_numero_de_la_commande::text), '0')
        ) s
        WHERE LTRIM(TRIM(qualite.po_number::text), '0') = s.po_clean;
    """)

    with engine.connect() as conn:
        try:
            res_cmd = conn.execute(update_cmd_sql)
            res_q = conn.execute(update_qualite_sql)
            conn.commit()

            stats = {
                "commandes_mises_a_jour": res_cmd.rowcount,
                "qualite_mises_a_jour": res_q.rowcount,
            }
            logger.info(
                f"[SUCCÈS] Rapprochement Sylob terminé : "
                f"{res_cmd.rowcount} lignes de commandes et {res_q.rowcount} fiches qualité mises à jour."
            )
            return stats
        except Exception as e:
            logger.error(f"[ERREUR] Échec du rapprochement réceptions Sylob : {e}")
            raise


if __name__ == "__main__":
    enrich_receptions_sylob()
