# -*- coding: utf-8 -*-
"""
[ETL]
=============================================================================
INGESTION Matrice TB Import / Lot Multiples produits -> nomenclature multi-composant
=============================================================================

Item #1b plan de captation (docs/plan_action.md). Lit l'onglet "Lot Multiples
produits" (752x122 : identite header colonnes 1-11, puis 8 blocs de 12
colonnes = composants, cf. docs/plan_action.md #1b). Charge :
  - achat.article_nomenclature (identite header, lot_vrac='Multiple')
  - achat.article_nomenclature_composant (1 ligne par composant, position 1-8)

Full-refresh sur les deux tables pour le sous-ensemble lot_vrac='Multiple'
(n'affecte pas les articles Lot-Vrac mono-composant deja charges).

Source : copie figee (mars 2026), cf. decision Antho 02/07.

Usage (poste, VPN) :
    python -m src.scripts.etl.transform_lot_multiples --file data/_raw_matrice.xlsx --dry-run
    python -m src.scripts.etl.transform_lot_multiples --file data/_raw_matrice.xlsx --commit
"""
from __future__ import annotations

import argparse
import logging
import math
from datetime import date

import pandas as pd
from sqlalchemy import text

from app.database import get_engine

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s -- %(message)s")
logger = logging.getLogger("transform_lot_multiples")

SHEET = "Lot Multiples produits"
HEADER_ROW = 4
NULL_LITERALS = {"", "/", "0", "nan", "#n/a"}

COMPOSANT_FIELDS = ["nom_composant", "epaisseur_mm", "longueur_mm", "poids_g",
                    "matiere_lame", "chrome_pct", "finition", "matiere_manche",
                    "pantone_manche", "marquage", "dim_marquage", "emplacement_marquage"]
COMPOSANT_STARTS = [12, 24, 36, 48, 60, 72, 84, 96]
NUM_FIELDS = {"epaisseur_mm", "longueur_mm", "poids_g", "chrome_pct"}


def _clean(v):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    s = str(v).strip()
    return None if s.lower() in NULL_LITERALS else s


def _num(v):
    s = _clean(v)
    if s is None:
        return None
    s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def read_records(path: str) -> tuple[list[dict], list[dict]]:
    df = pd.read_excel(path, sheet_name=SHEET, header=None)
    headers: list[dict] = []
    composants: list[dict] = []

    for _, row in df.iloc[HEADER_ROW + 1:].iterrows():
        code = _clean(row[1])
        if not code:
            continue
        date_creation = row[5]
        if pd.notna(date_creation) and not isinstance(date_creation, (date,)):
            try:
                date_creation = pd.to_datetime(date_creation, errors="coerce")
                date_creation = date_creation.date() if pd.notna(date_creation) else None
            except (ValueError, TypeError):
                date_creation = None
        elif pd.isna(date_creation):
            date_creation = None

        headers.append({
            "code_article": code,
            "description_fr": _clean(row[2]),
            "description_en": _clean(row[3]),
            "fournisseur": _clean(row[4]),
            "date_creation": date_creation,
            "gamme": _clean(row[6]),
            "lot_vrac": "Multiple",
            "nb_piece": None,  # texte libre ("1 set of 24") -> pas numerique, garde en description
            "ean13": _clean(row[8]),
            "ean14_spcb": _clean(row[9]),
            "ean14_pcb": _clean(row[10]),
            "hs_code": _clean(row[11]),
            "source_fichier": "Matrice TB Import.xlsx (copie figee mars 2026)",
        })

        position = 0
        for start in COMPOSANT_STARTS:
            nom = _clean(row[start])
            if not nom:
                continue
            position += 1
            vals = row[start:start + 12].tolist()
            rec = {"code_article": code, "position": position,
                   "source_fichier": "Matrice TB Import.xlsx (copie figee mars 2026)"}
            for i, field in enumerate(COMPOSANT_FIELDS):
                rec[field] = _num(vals[i]) if field in NUM_FIELDS else _clean(vals[i])
            composants.append(rec)

    return headers, composants


def load(headers: list[dict], composants: list[dict], dry_run: bool) -> tuple[int, int]:
    engine = get_engine()
    with engine.begin() as conn:
        if not dry_run:
            conn.execute(text(
                "DELETE FROM achat.article_nomenclature_composant "
                "WHERE code_article IN (SELECT code_article FROM achat.article_nomenclature WHERE lot_vrac='Multiple')"
            ))
        for rec in headers:
            logger.info("%s %s | %s -- %s", rec["code_article"],
                        "(simule)" if dry_run else "upsert", rec["gamme"], rec["fournisseur"])
            if dry_run:
                continue
            conn.execute(text("""
                INSERT INTO achat.article_nomenclature
                    (code_article, description_fr, description_en, fournisseur, date_creation,
                     gamme, lot_vrac, ean13, ean14_spcb, ean14_pcb, hs_code, source_fichier, charge_le)
                VALUES
                    (:code_article, :description_fr, :description_en, :fournisseur, :date_creation,
                     :gamme, :lot_vrac, :ean13, :ean14_spcb, :ean14_pcb, :hs_code, :source_fichier, NOW())
                ON CONFLICT (code_article) DO UPDATE SET
                    description_fr = EXCLUDED.description_fr,
                    description_en = EXCLUDED.description_en,
                    fournisseur = EXCLUDED.fournisseur,
                    date_creation = EXCLUDED.date_creation,
                    gamme = EXCLUDED.gamme,
                    lot_vrac = EXCLUDED.lot_vrac,
                    ean13 = EXCLUDED.ean13,
                    ean14_spcb = EXCLUDED.ean14_spcb,
                    ean14_pcb = EXCLUDED.ean14_pcb,
                    hs_code = EXCLUDED.hs_code,
                    source_fichier = EXCLUDED.source_fichier,
                    charge_le = NOW()
            """), rec)
        for rec in composants:
            if dry_run:
                continue
            conn.execute(text("""
                INSERT INTO achat.article_nomenclature_composant
                    (code_article, position, nom_composant, epaisseur_mm, longueur_mm, poids_g,
                     matiere_lame, chrome_pct, finition, matiere_manche, pantone_manche,
                     marquage, dim_marquage, emplacement_marquage, source_fichier, charge_le)
                VALUES
                    (:code_article, :position, :nom_composant, :epaisseur_mm, :longueur_mm, :poids_g,
                     :matiere_lame, :chrome_pct, :finition, :matiere_manche, :pantone_manche,
                     :marquage, :dim_marquage, :emplacement_marquage, :source_fichier, NOW())
                ON CONFLICT (code_article, position) DO UPDATE SET
                    nom_composant = EXCLUDED.nom_composant,
                    epaisseur_mm = EXCLUDED.epaisseur_mm,
                    longueur_mm = EXCLUDED.longueur_mm,
                    poids_g = EXCLUDED.poids_g,
                    matiere_lame = EXCLUDED.matiere_lame,
                    chrome_pct = EXCLUDED.chrome_pct,
                    finition = EXCLUDED.finition,
                    matiere_manche = EXCLUDED.matiere_manche,
                    pantone_manche = EXCLUDED.pantone_manche,
                    marquage = EXCLUDED.marquage,
                    dim_marquage = EXCLUDED.dim_marquage,
                    emplacement_marquage = EXCLUDED.emplacement_marquage,
                    source_fichier = EXCLUDED.source_fichier,
                    charge_le = NOW()
            """), rec)
        if dry_run:
            conn.rollback()
    if dry_run:
        logger.info("[DRY-RUN] %d article(s) / %d composant(s) simule(s) -- ROLLBACK.",
                     len(headers), len(composants))
    else:
        logger.info("[COMMIT] %d article(s) / %d composant(s) charge(s).",
                     len(headers), len(composants))
    return len(headers), len(composants)


def main() -> int:
    ap = argparse.ArgumentParser(description="Ingestion Lot Multiples -> nomenclature multi-composant.")
    ap.add_argument("--file", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--commit", action="store_true")
    args = ap.parse_args()

    headers, composants = read_records(args.file)
    logger.info("[INFO] %d article(s), %d composant(s) lus depuis %s / %s",
                len(headers), len(composants), args.file, SHEET)
    if not args.dry_run and not args.commit:
        logger.info("Utiliser --dry-run ou --commit.")
        return 0
    load(headers, composants, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
