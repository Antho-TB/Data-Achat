# -*- coding: utf-8 -*-
"""
[ETL]
=============================================================================
INGESTION Matrice TB Import -> achat.article_nomenclature (source #nomenclature)
=============================================================================

Lit l'onglet "Lot-Vrac Produits uniques" de `Matrice TB Import.xlsx` (référentiel
nomenclature : composant + packaging + gamme + HS code) et charge achat.article_
nomenclature en full-refresh. Mapping des colonnes PAR NOM (robuste aux retours
ligne / accents dans les en-têtes). Voir docs/audit_excels_service_achat.md.

⚠️ Étape POC. Cible stratégique = Sylob (vérifier d'abord ce qui y existe déjà).
L'onglet "Lot Multiples produits" (multi-composants, 122 col) = 2ᵉ passe à venir.

Usage (poste, VPN) :
    python -m src.scripts.etl.transform_nomenclature --check
    python -m src.scripts.etl.transform_nomenclature --dry-run
    python -m src.scripts.etl.transform_nomenclature --commit
"""
from __future__ import annotations

import argparse
import logging
import re
import unicodedata
from typing import Optional

import pandas as pd
from sqlalchemy import text

from app.database import get_engine
from src.utils.config_manager import Config

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s -- %(message)s")
logger = logging.getLogger("transform_nomenclature")

FILE = "Service_Achat/Matrice TB Import.xlsx"
SHEET = "Lot-Vrac Produits uniques"
HEADER_ROW = 2  # 0-based : ligne 3 du fichier

# cible <- fragments à chercher dans l'en-tête normalisé (accents/nl retirés)
COLMAP = {
    "code_article": "reference",
    "description_fr": "description fr",
    "description_en": "description eng",
    "fournisseur": "fournisseur",
    "date_creation": "date c",           # "Date céation" (typo source)
    "gamme": "gamme",
    "lot_vrac": "lot/vrac",
    "nb_piece": "nombre de piece",
    "ean13": "ean 13",
    "ean14_spcb": "ean 14 spcb",
    "ean14_pcb": "ean 14 pcb",
    "hs_code": "nomenclature",
    "epaisseur_mm": "epaisseur",
    "longueur_mm": "longueur",
    "poids_g": "poids",
    "matiere_lame": "matiere lame",
    "chrome_pct": "chrome",
    "finition": "finition",
    "matiere_manche": "matiere manche",
    "marquage": "marquage",
    "dim_marquage": "dimensions marquage",
    "emplacement_marquage": "emplacement",
}
NUM = {"nb_piece", "epaisseur_mm", "longueur_mm", "poids_g", "chrome_pct"}


def _norm(s) -> str:
    s = "".join(c for c in unicodedata.normalize("NFD", str(s)) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s.strip().lower())


def _num(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).replace(",", ".")
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    return float(m.group()) if m else None


def _clean(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).strip()
    return s if s and s not in {"/", "#N/A", "nan", "0"} else (s if s == "0" else None)


def build_records(df: pd.DataFrame) -> list[dict]:
    norm_cols = {_norm(c): c for c in df.columns}

    def find(frag: str) -> Optional[str]:
        return next((orig for n, orig in norm_cols.items() if frag in n), None)

    resolved = {tgt: find(frag) for tgt, frag in COLMAP.items()}
    missing = [t for t, c in resolved.items() if c is None]
    if missing:
        logger.warning("[ATTENTION] colonnes non trouvées : %s", missing)

    # colonnes Pantone/Motif manche N°1..6 -> concat
    pantone_cols = [orig for n, orig in norm_cols.items() if "pantone" in n or "motif manche" in n]

    out: dict[str, dict] = {}
    for _, row in df.iterrows():
        ref = _clean(row[resolved["code_article"]]) if resolved["code_article"] else None
        if not ref:
            continue
        rec = {"code_article": ref, "source_fichier": "Matrice TB Import.xlsx"}
        for tgt, col in resolved.items():
            if tgt == "code_article" or col is None:
                continue
            val = row[col]
            rec[tgt] = _num(val) if tgt in NUM else _clean(val)
        pant = [str(row[c]).strip() for c in pantone_cols
                if _clean(row[c]) not in (None, "/")]
        rec["pantone_manche"] = " | ".join(p for p in pant if p and p != "/") or None
        out[ref] = rec   # dédoublonnage : dernière occurrence
    return list(out.values())


def load(records: list[dict], commit: bool) -> int:
    if not records:
        logger.warning("[ATTENTION] aucun enregistrement.")
        return 0
    engine = get_engine()
    df = pd.DataFrame(records)
    if not commit:
        # dry-run sans DB : on valide le transform + les colonnes contre le schéma cible
        with engine.connect() as conn:
            cible = {r[0] for r in conn.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='achat' AND table_name='article_nomenclature'"))}
        extra = [c for c in df.columns if c not in cible]
        logger.info("[DRY-RUN] %d articles prêts. Colonnes hors schéma cible : %s",
                    len(df), extra or "aucune")
        return len(df)
    # Types PostgreSQL : dates / numériques (sinon INSERT texte -> colonne date/numeric échoue)
    df["date_creation"] = pd.to_datetime(df.get("date_creation"), errors="coerce").dt.date
    for c in ("epaisseur_mm", "longueur_mm", "poids_g", "chrome_pct"):
        df[c] = pd.to_numeric(df.get(c), errors="coerce")
    df["nb_piece"] = pd.to_numeric(df.get("nb_piece"), errors="coerce").astype("Int64")
    df = df.astype(object).where(pd.notnull(df), None)  # NaN/NaT -> None (NULL)
    # full-refresh : TRUNCATE + insert direct (types pandas adaptés par psycopg2)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE achat.article_nomenclature;"))
        df.to_sql("article_nomenclature", conn, schema="achat",
                  if_exists="append", index=False, method="multi", chunksize=400)
        logger.info("[COMMIT] %d articles chargés dans achat.article_nomenclature.", len(df))
    return len(df)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--commit", action="store_true")
    args = ap.parse_args()

    df = pd.read_excel(FILE, sheet_name=SHEET, header=HEADER_ROW, dtype=str)
    logger.info("[INFO] %s / %s : %d lignes brutes, %d colonnes.", FILE, SHEET, len(df), len(df.columns))
    recs = build_records(df)
    logger.info("[INFO] %d articles (dédoublonnés).", len(recs))
    if args.check:
        for r in recs[:3]:
            logger.info("  ex: %s", {k: v for k, v in r.items() if v is not None})
        return 0
    return 0 if load(recs, commit=args.commit) is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
