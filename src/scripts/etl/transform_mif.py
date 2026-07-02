# -*- coding: utf-8 -*-
"""
=============================================================================
INGESTION IMPORT 2026 / POINT MIF -> achat.mif_suivi
=============================================================================

Item #3 plan de captation (docs/plan_action.md). Lit l'onglet "POINT MIF"
(pivot gamme x coloris, 3 blocs LAGUIOLE ACCESS/MEDIUM/PREMIUM) et normalise
en lignes (gamme, stade, lot_pp, coloris, quantite). Full-refresh.

Format source : pour chaque bloc, une ligne "en-tete gamme" (colonne 3),
une ligne "en-tete coloris" (colonnes 3..8), puis des lignes de donnees
(colonne 0 = stade -- rempli seulement sur la 1ere ligne du stade, colonne 1
= lot PP, colonne 2 = total, colonnes 3..8 = quantite par coloris ou "/").

Source : copie figee (mars 2026), cf. decision Antho 02/07 (pas de gsheet
vivant connu pour l'instant -- l'IMPORT 2026 vivant est sur \\Srv-files-pom\...).

Usage (poste, VPN) :
    python -m src.scripts.etl.transform_mif --file data/_raw_import2026.xlsx --dry-run
    python -m src.scripts.etl.transform_mif --file data/_raw_import2026.xlsx --commit
"""
from __future__ import annotations

import argparse
import logging
import math

import pandas as pd
from sqlalchemy import text

from app.database import get_engine

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s -- %(message)s")
logger = logging.getLogger("transform_mif")

SHEET = "POINT MIF"
COLORIS_RANGE = range(3, 9)  # colonnes D..I


def _isna(v) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v))


def read_records(path: str) -> list[dict]:
    df = pd.read_excel(path, sheet_name=SHEET, header=None)
    records: list[dict] = []
    gamme = None
    coloris_cols: list[tuple[int, str]] = []
    stade = None

    for row in df.values.tolist():
        c0, c1, c2 = row[0], row[1], row[2]

        # Ligne en-tete gamme : A/B/C vides, D = "LAGUIOLE ..."
        if _isna(c0) and _isna(c1) and _isna(c2) and not _isna(row[3]) \
                and isinstance(row[3], str) and "LAGUIOLE" in row[3].upper():
            gamme = row[3].strip()
            stade = None
            coloris_cols = []
            continue

        # Ligne en-tete coloris : A/B/C vides, D..I = labels texte (pas "LAGUIOLE")
        if _isna(c0) and _isna(c1) and _isna(c2) and gamme and not coloris_cols:
            maybe = [(i, row[i]) for i in COLORIS_RANGE
                     if not _isna(row[i]) and isinstance(row[i], str)]
            if maybe and not any("LAGUIOLE" in v.upper() for _, v in maybe):
                coloris_cols = maybe
                continue

        # Ligne de donnees : B (lot PP) renseigne
        if not _isna(c1):
            if not _isna(c0):
                stade = c0.strip()
            if not (gamme and stade and coloris_cols):
                continue
            lot = str(c1).strip()
            total = None if _isna(c2) else float(c2)
            for idx, label in coloris_cols:
                v = row[idx]
                if _isna(v):
                    continue
                if isinstance(v, str) and v.strip() == "/":
                    continue
                try:
                    qty = float(v)
                except (ValueError, TypeError):
                    continue
                records.append({
                    "gamme": gamme, "stade": stade, "lot_pp": lot,
                    "coloris": label, "quantite": qty, "total_ligne": total,
                    "source_fichier": "IMPORT 2026.xlsx (copie figee mars 2026)",
                })
    return records


def load(records: list[dict], dry_run: bool) -> int:
    engine = get_engine()
    with engine.begin() as conn:
        if not dry_run:
            conn.execute(text("TRUNCATE TABLE achat.mif_suivi"))
        for rec in records:
            logger.info("%s %s | %s / %s / %s -> %s", rec["gamme"],
                        "(simule)" if dry_run else "insert",
                        rec["stade"], rec["lot_pp"], rec["coloris"], rec["quantite"])
            if dry_run:
                continue
            conn.execute(text("""
                INSERT INTO achat.mif_suivi
                    (gamme, stade, lot_pp, coloris, quantite, total_ligne, source_fichier, charge_le)
                VALUES
                    (:gamme, :stade, :lot_pp, :coloris, :quantite, :total_ligne, :source_fichier, NOW())
                ON CONFLICT (gamme, stade, lot_pp, coloris) DO UPDATE SET
                    quantite = EXCLUDED.quantite,
                    total_ligne = EXCLUDED.total_ligne,
                    source_fichier = EXCLUDED.source_fichier,
                    charge_le = NOW()
            """), rec)
        if dry_run:
            conn.rollback()
    if dry_run:
        logger.info("[DRY-RUN] %d ligne(s) simulee(s) -- ROLLBACK, rien n'est ecrit.", len(records))
    else:
        logger.info("[COMMIT] %d ligne(s) chargee(s) dans achat.mif_suivi.", len(records))
    return len(records)


def main() -> int:
    ap = argparse.ArgumentParser(description="Ingestion POINT MIF -> achat.mif_suivi.")
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
