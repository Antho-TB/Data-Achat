# -*- coding: utf-8 -*-
"""
[ETL]
=============================================================================
LOADER GMAIL -> achat.ot_transport (zone EXPÉDITION, pattern A — décision 30/06)
=============================================================================

Upsert des enregistrements produits par `parse_bl.py` dans achat.ot_transport
(PK n_conteneur). UPSERT **COALESCE** : un champ entrant NULL n'écrase JAMAIS une
valeur existante (contrairement au load_ot_transport Excel qui fait EXCLUDED).
Provenance : source_fichier = 'gmail:<fichier>'.

Pourquoi ot_transport et pas achat.commande : commande est full-refresh (TRUNCATE)
par l'ETL Excel et migre vers le DWH Sylob V25 ; ot_transport survit. Les vues
v_previsionnel / v_retard_article fusionnent (COALESCE BL prioritaire). Voir
decisions_log/20260630_writepath_gmail_pattern_a.

⚠️ Jointure vue = commande.n_conteneur ↔ ot_transport.n_conteneur. Une ligne BL
n'enrichit le prévisionnel que si la commande porte déjà ce n_conteneur (fourni par
l'IMPORT Excel). Si le BL est en avance sur l'Excel, le merge attend la MAJ Excel.

Auth : config/.env via Config (PG_USER=platform_team sur poste Marlène). VPN requis.

Usage (depuis la racine, VPN actif) :
    python -m src.scripts.gmail.load_ot_gmail --check
    python -m src.scripts.gmail.load_ot_gmail --file data/PJ/_parsed.json --dry-run
    python -m src.scripts.gmail.load_ot_gmail --file data/PJ/_parsed.json        # COMMIT

Entrée : JSON liste (sortie de parse_bl). Clés utilisées :
    n_conteneur (obligatoire), n_bl, etd_reel, eta, transitaire, n_facture,
    lieu_livraison, source_fichier. Les autres clés (po_numbers, ...) sont ignorées.
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
logger = logging.getLogger("load_ot_gmail")

# Colonnes texte et colonnes date (cast SQL explicite ::date pour ces dernières).
TEXT_FIELDS = ("n_bl", "transitaire", "n_facture", "lieu_livraison")
DATE_FIELDS = ("etd_reel", "eta")
ALL_FIELDS = TEXT_FIELDS + DATE_FIELDS

UPSERT_SQL = """
INSERT INTO achat.ot_transport
    (n_conteneur, n_bl, etd_reel, eta, transitaire, n_facture,
     lieu_livraison, source_fichier, charge_le)
VALUES
    (:n_conteneur, :n_bl, CAST(:etd_reel AS date), CAST(:eta AS date),
     :transitaire, :n_facture, :lieu_livraison, :source_fichier, NOW())
ON CONFLICT (n_conteneur) DO UPDATE SET
    n_bl           = COALESCE(EXCLUDED.n_bl,           achat.ot_transport.n_bl),
    etd_reel       = COALESCE(EXCLUDED.etd_reel,       achat.ot_transport.etd_reel),
    eta            = COALESCE(EXCLUDED.eta,            achat.ot_transport.eta),
    transitaire    = COALESCE(EXCLUDED.transitaire,    achat.ot_transport.transitaire),
    n_facture      = COALESCE(EXCLUDED.n_facture,      achat.ot_transport.n_facture),
    lieu_livraison = COALESCE(EXCLUDED.lieu_livraison, achat.ot_transport.lieu_livraison),
    source_fichier = EXCLUDED.source_fichier,
    charge_le      = NOW()
"""


def check() -> int:
    """Lecture seule : connexion + colonnes réelles d'achat.ot_transport."""
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
        n = conn.execute(
            text(f"SELECT COUNT(*) FROM {Config.PG_SCHEMA}.ot_transport")
        ).scalar()
        cols = conn.execute(
            text(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_schema = :s AND table_name = 'ot_transport' "
                "ORDER BY ordinal_position"
            ),
            {"s": Config.PG_SCHEMA},
        ).fetchall()
    logger.info("[OK] %s.ot_transport = %d conteneur(s).", Config.PG_SCHEMA, n)
    for name, dtype in cols:
        logger.info("       - %-16s %s", name, dtype)
    return 0


def _row_params(rec: dict) -> dict | None:
    conteneur = str(rec.get("n_conteneur") or "").strip()
    if not conteneur:
        logger.warning("Ignoré (n_conteneur manquant -> niveau PO, voir apply_etd_eta) : %s",
                       {k: rec.get(k) for k in ("n_bl", "po_numbers")})
        return None
    params = {"n_conteneur": conteneur}
    for f in ALL_FIELDS:
        val = rec.get(f)
        params[f] = (str(val).strip() or None) if isinstance(val, str) else val
    fichier = rec.get("source_fichier")
    params["source_fichier"] = f"gmail:{fichier}" if fichier else "gmail"
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
            logger.info("conteneur %s %s | bl=%s etd=%s eta=%s",
                        params["n_conteneur"],
                        "(simulé)" if dry_run else "upsert",
                        params.get("n_bl"), params.get("etd_reel"), params.get("eta"))
            total += 1
        if dry_run:
            logger.info("[DRY-RUN] %d conteneur(s) -- ROLLBACK, rien n'est écrit.", total)
            conn.rollback()
        else:
            logger.info("[COMMIT] %d conteneur(s) upsert dans %s.ot_transport.",
                        total, Config.PG_SCHEMA)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Upsert Gmail -> achat.ot_transport (pattern A).")
    ap.add_argument("--check", action="store_true", help="Lecture seule : connexion + colonnes.")
    ap.add_argument("--dry-run", action="store_true", help="Applique puis ROLLBACK.")
    ap.add_argument("--data", type=str, default="", help="JSON (liste) en argument.")
    ap.add_argument("--file", type=str, default="", help="Chemin d'un fichier JSON (liste).")
    args = ap.parse_args()

    if args.check:
        return check()

    if args.file:
        with open(args.file, "r", encoding="utf-8-sig") as fh:
            raw = fh.read()
    else:
        raw = args.data or sys.stdin.read()
    if not raw.strip():
        logger.error("Aucune donnée fournie (--data, --file ou stdin).")
        return 2
    try:
        records = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("JSON invalide : %s", exc)
        return 2
    if not isinstance(records, list):
        logger.error("Le JSON doit être une liste d'objets.")
        return 2

    return load(records, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
