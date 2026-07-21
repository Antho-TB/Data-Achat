# -*- coding: utf-8 -*-
"""
[ETL]
=============================================================================
LOADER -> achat.artwork_statut (zone DESIGN, pattern A -- decision 30/06)
=============================================================================

Upsert des enregistrements produits par `transform_artwork.py` dans
achat.artwork_statut (PK code_article). UPSERT COALESCE : un champ entrant
NULL n'ecrase jamais une valeur existante. Meme pattern que load_ot_gmail.

Voir sql/20260630_artwork_statut.sql, docs/profil_artworks.md.

Usage (depuis la racine, VPN actif) :
    python -m src.scripts.gmail.load_artwork --check
    python -m src.scripts.gmail.load_artwork --file data/_artwork.json --dry-run
    python -m src.scripts.gmail.load_artwork --file data/_artwork.json        # COMMIT

Entree : JSON liste (sortie de transform_artwork). Cle : code_article.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys

from sqlalchemy import text

from app.database import get_engine
from src.utils.config_manager import Config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s -- %(message)s",
)
logger = logging.getLogger("load_artwork")

TEXT_FIELDS = ("designation", "statut_artwork", "valideur", "commentaire")
DATE_FIELDS = ("date_demande", "date_validation", "derniere_version")
INT_FIELDS = ("priorite",)
ALL_FIELDS = TEXT_FIELDS + DATE_FIELDS + INT_FIELDS

UPSERT_SQL = """
INSERT INTO achat.artwork_statut
    (code_article, designation, statut_artwork, date_demande, date_validation,
     derniere_version, priorite, valideur, commentaire, source_fichier, charge_le)
VALUES
    (:code_article, :designation, :statut_artwork,
     CAST(:date_demande AS date), CAST(:date_validation AS date), CAST(:derniere_version AS date),
     :priorite, :valideur, :commentaire, :source_fichier, NOW())
ON CONFLICT (code_article) DO UPDATE SET
    designation      = COALESCE(EXCLUDED.designation,      achat.artwork_statut.designation),
    statut_artwork   = COALESCE(EXCLUDED.statut_artwork,   achat.artwork_statut.statut_artwork),
    date_demande     = COALESCE(EXCLUDED.date_demande,     achat.artwork_statut.date_demande),
    date_validation  = COALESCE(EXCLUDED.date_validation,  achat.artwork_statut.date_validation),
    derniere_version = COALESCE(EXCLUDED.derniere_version, achat.artwork_statut.derniere_version),
    priorite         = COALESCE(EXCLUDED.priorite,         achat.artwork_statut.priorite),
    valideur         = COALESCE(EXCLUDED.valideur,         achat.artwork_statut.valideur),
    commentaire      = COALESCE(EXCLUDED.commentaire,      achat.artwork_statut.commentaire),
    source_fichier   = EXCLUDED.source_fichier,
    charge_le        = NOW()
"""

# achat.v_artwork part de achat.artwork (LEFT JOIN artwork_statut sur code_article) :
# un article jamais commande (code provisoire NOUVEAU-<slug>, cf. transform_artwork.py
# 21/07, ecart KPI artwork_en_attente) n'a par definition AUCUNE ligne achat.artwork
# (alimentee par le pipeline mail/PO). Sans ligne fantome, il reste invisible dans la
# vue meme apres l'upsert ci-dessus. Le NOT EXISTS evite de dupliquer les ~390 articles
# qui ont deja une vraie ligne (avec PO) issue du pipeline mail.
GHOST_ARTWORK_SQL = """
INSERT INTO achat.artwork (po_number, code_article, designation, statut_artwork, updated_at)
SELECT 'SANS-PO', :code_article, :designation, :statut_artwork, NOW()
WHERE NOT EXISTS (
    SELECT 1 FROM achat.artwork WHERE code_article = :code_article
)
ON CONFLICT (po_number, code_article) DO NOTHING
"""


def check() -> int:
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
        n = conn.execute(
            text(f"SELECT COUNT(*) FROM {Config.PG_SCHEMA}.artwork_statut")
        ).scalar()
    logger.info("[OK] %s.artwork_statut = %d article(s).", Config.PG_SCHEMA, n)
    return 0


def _row_params(rec: dict) -> dict | None:
    code = str(rec.get("code_article") or "").strip()
    if not code:
        logger.warning("Ignore (code_article manquant) : %s", rec.get("designation"))
        return None
    params = {"code_article": code}
    for f in ALL_FIELDS:
        val = rec.get(f)
        params[f] = (str(val).strip() or None) if isinstance(val, str) else val
    fichier = rec.get("source_fichier")
    params["source_fichier"] = f"drive:{fichier}" if fichier else "drive"
    return params


def load(records: list[dict], dry_run: bool) -> int:
    engine = get_engine()
    total = 0
    with engine.begin() as conn:
        for rec in records:
            params = _row_params(rec)
            if not params:
                continue
            conn.execute(text(UPSERT_SQL), params)
            conn.execute(text(GHOST_ARTWORK_SQL), {
                "code_article": params["code_article"],
                "designation": params.get("designation"),
                "statut_artwork": params.get("statut_artwork"),
            })
            logger.info("article %s %s | statut=%s valideur=%s",
                        params["code_article"],
                        "(simule)" if dry_run else "upsert",
                        params.get("statut_artwork"), params.get("valideur"))
            total += 1
        if dry_run:
            logger.info("[DRY-RUN] %d article(s) -- ROLLBACK, rien n'est ecrit.", total)
            conn.rollback()
        else:
            logger.info("[COMMIT] %d article(s) upsert dans %s.artwork_statut.",
                        total, Config.PG_SCHEMA)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Upsert Drive -> achat.artwork_statut (pattern A).")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--data", type=str, default="")
    ap.add_argument("--file", type=str, default="")
    args = ap.parse_args()

    if args.check:
        return check()

    if args.file:
        with open(args.file, "r", encoding="utf-8-sig") as fh:
            raw = fh.read()
    else:
        raw = args.data or sys.stdin.read()
    if not raw.strip():
        logger.error("Aucune donnee fournie (--data, --file ou stdin).")
        return 2
    try:
        records = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("JSON invalide : %s", exc)
        return 2
    if not isinstance(records, list):
        logger.error("Le JSON doit etre une liste d'objets.")
        return 2

    return load(records, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
