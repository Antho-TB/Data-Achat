# -*- coding: utf-8 -*-
"""
=============================================================================
INGESTION IMPORT 2026 / STOP REF CARREFOUR -> achat.article_cycle_vie
=============================================================================

Item #4 plan de captation (docs/plan_action.md). Lit l'onglet "STOP REF
CARREFOUR" de IMPORT 2026.xlsx (16x7 : fournisseur, code, designation, qte
en commande, statut, ean13) et charge achat.article_cycle_vie en full-refresh.

Skip les 2 lignes de notes libres en bas de feuille (PO ... -- structure
differente, pas le meme grain) et les lignes vides.

Source : copie figee (mars 2026), pas de gsheet vivant connu (decision Antho
02/07 -- l'IMPORT 2026 vivant est sur \\Srv-files-pom\... mais acces reseau
direct refuse ; a rafraichir manuellement plus tard).

Usage (poste, VPN) :
    python -m src.scripts.etl.transform_stop_ref --file data/_raw_import2026.xlsx --dry-run
    python -m src.scripts.etl.transform_stop_ref --file data/_raw_import2026.xlsx --commit
"""
from __future__ import annotations

import argparse
import logging

import pandas as pd
from sqlalchemy import text

from app.database import get_engine
from src.utils.config_manager import Config

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s -- %(message)s")
logger = logging.getLogger("transform_stop_ref")

SHEET = "STOP REF CARREFOUR"


def read_records(path: str) -> list[dict]:
    df = pd.read_excel(path, sheet_name=SHEET, header=None, dtype=str)
    records = []
    for _, row in df.iloc[1:].iterrows():  # skip header row 0
        fournisseur = (row[0] or "").strip() if isinstance(row[0], str) else None
        code = (row[1] or "").strip() if isinstance(row[1], str) else None
        if not fournisseur or not code:
            continue  # ligne vide ou note libre en bas de feuille
        qte_raw = row[3]
        try:
            qte = int(float(qte_raw)) if pd.notna(qte_raw) else None
        except (ValueError, TypeError):
            qte = None
        ean = (row[5] or "").strip().lstrip("​") if isinstance(row[5], str) else None
        records.append({
            "code_article": code,
            "fournisseur": fournisseur,
            "designation": (row[2] or "").strip() if isinstance(row[2], str) else None,
            "quantite_en_commande": qte,
            "statut": (row[4] or "").strip() if isinstance(row[4], str) else None,
            "ean13": ean or None,
            "source_fichier": "IMPORT 2026.xlsx (copie figee mars 2026)",
        })
    return records


def load(records: list[dict], dry_run: bool) -> int:
    engine = get_engine()
    with engine.begin() as conn:
        if not dry_run:
            conn.execute(text("TRUNCATE TABLE achat.article_cycle_vie"))
        for rec in records:
            logger.info("%s %s | %s -- %s", rec["code_article"],
                        "(simule)" if dry_run else "insert", rec["fournisseur"], rec["statut"])
            if dry_run:
                continue
            conn.execute(text("""
                INSERT INTO achat.article_cycle_vie
                    (code_article, fournisseur, designation, quantite_en_commande,
                     statut, ean13, source_fichier, charge_le)
                VALUES
                    (:code_article, :fournisseur, :designation, :quantite_en_commande,
                     :statut, :ean13, :source_fichier, NOW())
                ON CONFLICT (code_article) DO UPDATE SET
                    fournisseur = EXCLUDED.fournisseur,
                    designation = EXCLUDED.designation,
                    quantite_en_commande = EXCLUDED.quantite_en_commande,
                    statut = EXCLUDED.statut,
                    ean13 = EXCLUDED.ean13,
                    source_fichier = EXCLUDED.source_fichier,
                    charge_le = NOW()
            """), rec)
        if dry_run:
            conn.rollback()
    if dry_run:
        logger.info("[DRY-RUN] %d ligne(s) simulee(s) -- ROLLBACK, rien n'est ecrit.", len(records))
    else:
        logger.info("[COMMIT] %d ligne(s) chargee(s) dans achat.article_cycle_vie.", len(records))
    return len(records)


def main() -> int:
    ap = argparse.ArgumentParser(description="Ingestion STOP REF CARREFOUR -> achat.article_cycle_vie.")
    ap.add_argument("--file", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--commit", action="store_true")
    args = ap.parse_args()

    records = read_records(args.file)
    logger.info("[INFO] %d ligne(s) valide(s) lue(s) depuis %s / %s", len(records), args.file, SHEET)
    if not args.dry_run and not args.commit:
        logger.info("Utiliser --dry-run ou --commit.")
        return 0
    load(records, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
