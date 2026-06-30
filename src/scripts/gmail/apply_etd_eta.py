# -*- coding: utf-8 -*-
"""
=============================================================================
WRITE GMAIL -> achat.commande : ENRICHISSEMENT ETD CONFIRMÉ (niveau PO / ordre)
=============================================================================

Pattern A (décision 30/06) — séparation des zones :
- `etd_confirme` (niveau ORDRE, corps de mail) -> achat.commande, UPDATE par PO. <- CE SCRIPT.
- `etd_reel` / `eta` / `n_bl` / `n_conteneur` (niveau EXPÉDITION, BL) -> achat.ot_transport
  (UPSERT par n_conteneur, survit au full-refresh). Voir le skill achat-gmail-dwh.
Les vues v_previsionnel / v_retard_article fusionnent les deux (BL prioritaire).

Périmètre volontairement restreint (POC) :
- pas de création de ligne (UPDATE seulement) ;
- pas de prix/quantité par article (granularité article = PDF/jointure DB, hors périmètre) ;
- traçabilité : updated_at=NOW() (achat.commande n'a pas de colonne 'source').

Auth : config/.env via Config (PG_USER=platform_team, KEY_VAULT_NAME vide).
Connexion : réutilise app.database.get_engine() (pattern URL.create du projet).
VPN Stormshield requis (DWH Azure injoignable sinon).

Usage (depuis la racine du projet, VPN actif) :
    python -m src.scripts.gmail.apply_etd_eta --check
    python -m src.scripts.gmail.apply_etd_eta --dry-run --data "<json>"
    python -m src.scripts.gmail.apply_etd_eta --data "<json>"        # COMMIT réel

Format JSON attendu (liste) :
    [{"po_number": "00176529", "etd_confirme": "2026-07-29"},
     {"po_number": "00179321", "etd_confirme": "2026-08-02"}]
Champ date accepté : etd_confirme (ISO YYYY-MM-DD). etd_reel / eta relèvent désormais
de la zone expédition (achat.ot_transport) — voir le skill achat-gmail-dwh.
"""
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
logger = logging.getLogger("apply_etd_eta")

# Pattern A : ce script ne touche QUE l'ordre (etd_confirme) sur achat.commande.
# etd_reel / eta -> achat.ot_transport (zone expédition, skill achat-gmail-dwh).
ALLOWED_DATE_FIELDS = ("etd_confirme",)


def check() -> int:
    """Lecture seule : valide la connexion + affiche les vraies colonnes de achat.commande."""
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
        n = conn.execute(
            text(f"SELECT COUNT(*) FROM {Config.PG_SCHEMA}.commande")
        ).scalar()
        cols = conn.execute(
            text(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_schema = :s AND table_name = 'commande' "
                "ORDER BY ordinal_position"
            ),
            {"s": Config.PG_SCHEMA},
        ).fetchall()
    logger.info("[OK] Connexion DWH etablie. %s.commande = %d lignes.", Config.PG_SCHEMA, n)
    logger.info("[OK] Colonnes reelles de %s.commande :", Config.PG_SCHEMA)
    for name, dtype in cols:
        flag = "  <-- cible ETD/ETA" if name in ALLOWED_DATE_FIELDS else ""
        logger.info("       - %-22s %s%s", name, dtype, flag)
    missing = [f for f in ALLOWED_DATE_FIELDS if f not in {c[0] for c in cols}]
    if missing:
        logger.warning("[ATTENTION] Colonnes ETD/ETA absentes du DDL : %s", missing)
    return 0


def _build_update(row: dict) -> tuple[str, dict] | None:
    po = str(row.get("po_number", "")).strip()
    if not po:
        logger.warning("Ligne ignoree (po_number manquant) : %s", row)
        return None
    sets, params = [], {"po": po}
    for f in ALLOWED_DATE_FIELDS:
        if row.get(f):
            sets.append(f"{f} = :{f}")
            params[f] = row[f]
    if not sets:
        logger.warning("Ligne ignoree (aucun champ ETD/ETA) : %s", row)
        return None
    # NB: achat.commande n'a pas de colonne 'source' -- tracabilite via updated_at.
    sets.append("updated_at = NOW()")
    sql = (
        f"UPDATE {Config.PG_SCHEMA}.commande SET {', '.join(sets)} "
        f"WHERE po_number = :po"
    )
    return sql, params


def apply(data: list[dict], dry_run: bool) -> int:
    engine = get_engine()
    total = 0
    with engine.begin() as conn:
        for row in data:
            built = _build_update(row)
            if not built:
                continue
            sql, params = built
            res = conn.execute(text(sql), params)
            logger.info(
                "PO %s -> %d ligne(s) %s | champs: %s",
                params["po"],
                res.rowcount,
                "(simulees)" if dry_run else "MAJ",
                {k: v for k, v in params.items() if k != "po"},
            )
            total += res.rowcount or 0
        if dry_run:
            logger.info("[DRY-RUN] %d ligne(s) impactees -- ROLLBACK, rien n'est ecrit.", total)
            conn.rollback()
        else:
            logger.info("[COMMIT] %d ligne(s) ecrites dans %s.commande.", total, Config.PG_SCHEMA)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Enrichissement ETD/ETA niveau PO depuis Gmail.")
    parser.add_argument("--check", action="store_true", help="Lecture seule : connexion + colonnes.")
    parser.add_argument("--dry-run", action="store_true", help="Applique puis ROLLBACK (rien ecrit).")
    parser.add_argument("--data", type=str, default="", help="JSON (liste) en argument.")
    parser.add_argument("--file", type=str, default="", help="Chemin d'un fichier JSON (liste).")
    args = parser.parse_args()

    if args.check:
        return check()

    if args.file:
        with open(args.file, "r", encoding="utf-8-sig") as fh:
            raw = fh.read()
    else:
        raw = args.data or sys.stdin.read()
    if not raw.strip():
        logger.error("Aucune donnee fournie (--data ou stdin).")
        return 2
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("JSON invalide : %s", exc)
        return 2
    if not isinstance(data, list):
        logger.error("Le JSON doit etre une liste d'objets.")
        return 2

    return apply(data, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
