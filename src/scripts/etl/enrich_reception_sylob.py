# -*- coding: utf-8 -*-
"""
[ETL]
=============================================================================
RAPPROCHEMENT DES RECEPTIONS PHYSIQUES SYLOB
=============================================================================

Sylob enregistre la date a laquelle la marchandise est physiquement entree au
depot (public.receptions_detaillees2). Le fichier IMPORT d'Andrea, lui, ne
contient qu'une date de livraison previsionnelle saisie a la main. Rapprocher
les deux donne aux Achats la vraie date d'arrivee, sans ressaisie.

Strategie : on N'ECRIT PAS directement dans achat.commande. Cette table est
rechargee en full-refresh (TRUNCATE + INSERT) par l'ETL nocturne, donc tout
UPDATE direct serait efface la nuit suivante. On depose l'information dans
achat.commande_enrichissement (table persistante, cf.
sql/20260728_commande_enrichissement.sql), et apply_enrichissement.py la
reprojette sur achat.commande et achat.qualite apres chaque chargement.

Junior Tip : les numeros de PO ne sont pas ecrits pareil des deux cotes
(Sylob prefixe de zeros : 0181325 contre 181325 dans le fichier Excel). D'ou
le LTRIM(..., '0') des deux cotes de la jointure, sinon zero ligne ne matche
et l'enrichissement passe pour vide alors qu'il ne l'est pas.

Usage :
    python -m src.scripts.etl.enrich_reception_sylob [--dry-run]
"""
from __future__ import annotations

import argparse
import logging

from sqlalchemy import text

from app.database import get_engine
from src.utils.logging_setup import setup_logging

logger = logging.getLogger(__name__)

SCHEMA = "achat"
SOURCE = "enrich_reception_sylob"

# Reception Sylob agregee par PO : public.receptions_detaillees2 ne ventile pas
# par code article, on retient donc la derniere date de reception du PO.
SQL_RECEPTIONS = f"""
    SELECT LTRIM(TRIM(r.commande_numero_de_la_commande::text), '0') AS po_number,
           MAX(r.ligne_receptionnee_le)                             AS date_reception_sylob
    FROM public.receptions_detaillees2 r
    WHERE r.commande_numero_de_la_commande IS NOT NULL
      AND r.ligne_receptionnee_le IS NOT NULL
      AND EXISTS (
          SELECT 1 FROM {SCHEMA}.commande c
          WHERE LTRIM(TRIM(c.po_number::text), '0')
              = LTRIM(TRIM(r.commande_numero_de_la_commande::text), '0')
      )
    GROUP BY 1
"""

SQL_UPSERT = f"""
    INSERT INTO {SCHEMA}.commande_enrichissement
        (po_number, code_article, date_reception_sylob, source, maj_le)
    VALUES (:po_number, '', :date_reception_sylob, :source, NOW())
    ON CONFLICT (po_number, code_article) DO UPDATE
    SET date_reception_sylob = EXCLUDED.date_reception_sylob,
        source              = EXCLUDED.source,
        maj_le              = NOW()
    WHERE {SCHEMA}.commande_enrichissement.date_reception_sylob
          IS DISTINCT FROM EXCLUDED.date_reception_sylob
"""


def enrich_receptions_sylob(dry_run: bool = False) -> dict[str, int]:
    """
    Depose les dates de reception physique Sylob dans la table d'enrichissement.

    Args:
        dry_run: si True, compte les lignes sans rien ecrire en base.

    Returns:
        Compteurs {"receptions_lues", "enrichissements_ecrits"}.
    """
    logger.info("[INFO] Lecture des receptions physiques Sylob...")
    engine = get_engine()

    with engine.begin() as conn:
        receptions = [dict(row) for row in
                      conn.execute(text(SQL_RECEPTIONS)).mappings().all()]
        logger.info("[INFO] %d PO avec une reception Sylob rapprochable.", len(receptions))

        if dry_run:
            logger.info("[INFO] [DRY-RUN] aucune ecriture effectuee.")
            return {"receptions_lues": len(receptions), "enrichissements_ecrits": 0}

        ecrits = 0
        for rec in receptions:
            res = conn.execute(text(SQL_UPSERT), {**rec, "source": SOURCE})
            ecrits += res.rowcount

    logger.info("[SUCCES] Receptions Sylob rapprochees : %d PO lus, %d enrichissements ecrits.",
                len(receptions), ecrits)
    return {"receptions_lues": len(receptions), "enrichissements_ecrits": ecrits}


def main() -> None:
    setup_logging()
    ap = argparse.ArgumentParser(description="Rapproche les receptions physiques Sylob")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    enrich_receptions_sylob(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
