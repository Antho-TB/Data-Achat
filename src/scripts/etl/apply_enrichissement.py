# -*- coding: utf-8 -*-
"""
[ETL]
=============================================================================
REPROJECTION DES ENRICHISSEMENTS SUR achat.commande ET achat.qualite
=============================================================================

achat.commande et achat.qualite sont rechargees en full-refresh par l'ETL
(TRUNCATE + INSERT depuis IMPORT 2026.xlsx). Les informations qui ne viennent
pas de ce fichier (reception physique Sylob, non-conformite signalee par
mail) sont conservees a part dans achat.commande_enrichissement, puis
reappliquees ici, une fois le chargement termine.

Ce module est donc la DERNIERE etape du pipeline. Sans lui, les
enrichissements existent en base mais restent invisibles dans l'application.

Junior Tip : chaque UPDATE est protege par IS DISTINCT FROM. Sans ce garde-fou
on reecrit les memes valeurs a chaque nuit, ce qui fait remonter updated_at
sur toute la table et rend inexploitable la question "qu'est-ce qui a bouge
depuis hier".

Usage :
    python -m src.scripts.etl.apply_enrichissement [--dry-run]
"""
from __future__ import annotations

import argparse
import logging

from sqlalchemy import text

from app.database import get_engine
from src.utils.logging_setup import setup_logging

logger = logging.getLogger(__name__)

SCHEMA = "achat"

STATUT_LIVREE = "Livrée"

# Statuts que l'enrichissement ne doit jamais ecraser : une commande annulee
# reste annulee meme si une reception partielle est remontee de Sylob, et une
# commande deja soldee cote comptabilite ne redevient pas "Livree".
STATUTS_FIGES = ("Annulee", "Annulée", "CLOTUREE", "Payee", "Payée", "Paye")

# Liste SQL construite depuis la constante ci-dessus. Un parametre lie ne
# fonctionne pas avec IN sans bindparam(expanding=True), et ces valeurs sont
# une constante du code, pas une saisie utilisateur : aucun risque d'injection.
SQL_STATUTS_FIGES = "(" + ", ".join(f"'{s}'" for s in STATUTS_FIGES) + ")"

# La jointure se fait sur le PO nettoye de ses zeros de tete des deux cotes :
# Sylob ecrit 0181325 la ou le fichier Excel ecrit 181325.
SQL_JOIN_PO = "LTRIM(TRIM(c.po_number::text), '0') = LTRIM(TRIM(e.po_number::text), '0')"

SQL_COMMANDE = f"""
    UPDATE {SCHEMA}.commande c
    SET date_reception_sylob = COALESCE(e.date_reception_sylob, c.date_reception_sylob),
        date_livraison       = COALESCE(c.date_livraison, e.date_reception_sylob),
        non_conformite       = COALESCE(e.non_conformite, c.non_conformite),
        statut               = CASE
            WHEN e.date_reception_sylob IS NOT NULL
                 AND c.statut NOT IN {SQL_STATUTS_FIGES} THEN '{STATUT_LIVREE}'
            ELSE c.statut
        END,
        updated_at           = NOW()
    FROM {SCHEMA}.commande_enrichissement e
    WHERE {SQL_JOIN_PO}
      AND (e.code_article = '' OR e.code_article = c.code_article)
      AND (
            c.date_reception_sylob IS DISTINCT FROM COALESCE(e.date_reception_sylob, c.date_reception_sylob)
         OR c.non_conformite       IS DISTINCT FROM COALESCE(e.non_conformite, c.non_conformite)
         OR (e.date_reception_sylob IS NOT NULL
             AND c.statut NOT IN {SQL_STATUTS_FIGES}
             AND c.statut IS DISTINCT FROM '{STATUT_LIVREE}')
      )
"""

SQL_QUALITE = f"""
    UPDATE {SCHEMA}.qualite c
    SET date_reception_sylob = COALESCE(e.date_reception_sylob, c.date_reception_sylob),
        reception            = CASE
            WHEN e.date_reception_sylob IS NOT NULL
                 AND (c.reception IS NULL OR c.reception IN ('En attente', '', '-'))
            THEN 'Receptionne Sylob'
            ELSE c.reception
        END,
        ncr                  = COALESCE(e.ncr_ref, c.ncr),
        resultat_inspection  = COALESCE(e.resultat_inspection, c.resultat_inspection)
    FROM {SCHEMA}.commande_enrichissement e
    WHERE {SQL_JOIN_PO}
      AND (e.code_article = '' OR e.code_article = c.code_article)
      AND (
            c.date_reception_sylob IS DISTINCT FROM COALESCE(e.date_reception_sylob, c.date_reception_sylob)
         OR c.ncr                  IS DISTINCT FROM COALESCE(e.ncr_ref, c.ncr)
         OR c.resultat_inspection  IS DISTINCT FROM COALESCE(e.resultat_inspection, c.resultat_inspection)
      )
"""


def apply_enrichissement(dry_run: bool = False) -> dict[str, int]:
    """
    Reapplique achat.commande_enrichissement sur achat.commande et achat.qualite.

    Args:
        dry_run: si True, compte les enrichissements en attente sans ecrire.

    Returns:
        Compteurs {"commandes_maj", "qualite_maj"}.
    """
    engine = get_engine()

    with engine.begin() as conn:
        en_attente = conn.execute(
            text(f"SELECT COUNT(*) FROM {SCHEMA}.commande_enrichissement")
        ).scalar_one()

        if dry_run:
            logger.info("[INFO] [DRY-RUN] %d enrichissement(s) en attente de reprojection.",
                        en_attente)
            return {"commandes_maj": 0, "qualite_maj": 0}

        nb_cmd = conn.execute(text(SQL_COMMANDE)).rowcount
        nb_qua = conn.execute(text(SQL_QUALITE)).rowcount

    logger.info("[SUCCES] Enrichissements reprojetes : %d ligne(s) de commande, "
                "%d fiche(s) qualite (sur %d enrichissement(s) stockes).",
                nb_cmd, nb_qua, en_attente)
    return {"commandes_maj": nb_cmd, "qualite_maj": nb_qua}


def main() -> None:
    setup_logging()
    ap = argparse.ArgumentParser(description="Reprojette les enrichissements sur commande/qualite")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    apply_enrichissement(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
