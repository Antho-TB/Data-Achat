# -*- coding: utf-8 -*-
"""
[ETL]
=============================================================================
ENRICHISSEMENT DIMENSIONS/PACKAGING SYLOB -> achat.produit
=============================================================================

Item #2 du plan de captation (docs/plan_action.md) -- REVISE suite audit Sylob
V25 du 2026-07-02 (docs/20260702_audit_champs_sylob_v25.md) : les dimensions
et le packaging (EAN, PCB/SPCB, poids, volume) sont DEJA natifs dans Sylob
(Article.af_article, colonnes sup_*), peuples a 84-97% sur 9827 articles.
-> Pas de nouveau pipeline de capture depuis un Excel Andrea : on tire
directement ces colonnes du DWH Sylob, meme pattern cascade GDD->SE->CIE que
enrich_from_sylob.py (priorite au premier schema qui matche).

Politique d'ecrasement (different de enrich_from_sylob.py qui protege
l'existant) : Sylob est desormais la source de verite pour le packaging
(cf. audit) -> on ECRASE la valeur FUSEAU par la valeur Sylob quand cette
derniere est renseignee (pas de COALESCE protecteur). Objectif : arreter la
double-saisie Excel cote Andrea a terme.

Usage (VPN actif) :
    python -m src.scripts.etl.enrich_dimensions --dry-run
    python -m src.scripts.etl.enrich_dimensions
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s -- %(message)s")
logger = logging.getLogger("enrich_dimensions")

SCHEMAS = [
    "TARRERIAS_GENERALE_DE_DECOUPAGE_Article",
    "TARRERIAS_SE_TARRERIAS_BONJEAN_Article",
    "TARRERIAS_TARRERIAS_BONJEAN_ET_CIE_Article",
]

# Colonnes source Sylob (af_article) -> colonnes cible achat.produit
COLUMN_MAP = {
    "code_gtin_13": "ean13",
    "sup_ean14_pcb": "ean14_pcb",
    "sup_ean14_spcb": "ean14_spcb",
    "sup_pcb": "pcb",
    "sup_spcb": "spcb",
    "sup_longueur_pcb": "longueur_pcb_cm",
    "sup_largeur_pcb": "largeur_pcb_cm",
    "sup_hauteur_pcb": "hauteur_pcb_cm",
    "sup_poids_pcb": "poids_pcb_kg",
}
SYLOB_COLS = list(COLUMN_MAP.keys())


def ensure_source_columns(engine) -> None:
    """
    Ajoute source_dimensions / sylob_dimensions_synced_at si absentes (idempotent).

    Colonne dediee (distincte de sylob_synced_at, deja utilisee par
    enrich_from_sylob.py pour le bloc prix/delai) pour ne pas ecraser le
    marqueur de l'autre job d'enrichissement -- cf. sql/20260702_source_dimensions_produit.sql.
    """
    from sqlalchemy import text
    with engine.begin() as conn:
        conn.execute(text("""
            ALTER TABLE achat.produit
              ADD COLUMN IF NOT EXISTS source_dimensions          TEXT,
              ADD COLUMN IF NOT EXISTS sylob_dimensions_synced_at  TIMESTAMPTZ;
        """))
    logger.info("[SUCCÈS] Colonnes source_dimensions vérifiées.")


def available_columns(schema: str, conn) -> list[str]:
    """
    Certaines societes (GDD) n'ont pas les memes colonnes sup_* custom que
    SE -- les customisations Nubo sont faites par entite. On introspecte
    avant de construire le SELECT pour ne jamais demander une colonne
    absente (UndefinedColumn sinon).
    """
    from sqlalchemy import text
    rows = conn.execute(text("""
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = :s AND table_name = 'af_article'
          AND column_name = ANY(:cols)
    """), {"s": schema, "cols": SYLOB_COLS}).fetchall()
    return [r[0] for r in rows]


def fetch_batch(codes: list[str], schema: str, cols: list[str], conn) -> dict[str, dict]:
    from sqlalchemy import bindparam, text
    if not codes or not cols:
        return {}
    cols_sql = ", ".join(cols)
    stmt = text(f"""
        SELECT code_article, {cols_sql}
        FROM "{schema}".af_article
        WHERE code_article IN :codes
    """).bindparams(bindparam("codes", expanding=True))
    rows = conn.execute(stmt, {"codes": codes}).fetchall()
    out = {}
    for r in rows:
        code = r[0]
        data = {COLUMN_MAP[cols[i]]: r[i + 1] for i in range(len(cols))}
        # Ne garder que si au moins un champ dimension/packaging est renseigne
        if any(v not in (None, "", 0) for k, v in data.items() if k != "ean13"):
            out[code] = data
    return out


def enrich(achat_engine, sylob_engine, dry_run: bool) -> dict[str, int]:
    from sqlalchemy import text

    with achat_engine.connect() as ca:
        rows = ca.execute(text(
            "SELECT code_article FROM achat.produit "
            "WHERE code_article IS NOT NULL AND code_article != ''"
        )).fetchall()
    all_codes = [r[0] for r in rows]
    logger.info("[INFO] Articles a traiter : %d", len(all_codes))

    batch = 200
    by_code: dict[str, dict] = {}
    stats = {"total": len(all_codes)}

    with sylob_engine.connect() as cs:
        for schema in SCHEMAS:
            remaining = [c for c in all_codes if c not in by_code]
            cols = available_columns(schema, cs)
            if not cols:
                logger.info("Schema %-45s  aucune colonne sup_* packaging -- skip", schema)
                continue
            schema_hits: dict[str, dict] = {}
            for i in range(0, len(remaining), batch):
                schema_hits.update(fetch_batch(remaining[i:i + batch], schema, cols, cs))
            by_code.update(schema_hits)
            key = schema.split("_Article")[0].split("TARRERIAS_")[-1][:6]
            stats[f"schema_{key}"] = len(schema_hits)
            logger.info("Schema %-45s  colonnes=%d  match=%d", schema, len(cols), len(schema_hits))

    stats["match_total"] = len(by_code)
    stats["non_trouves"] = stats["total"] - len(by_code)
    now = datetime.now(timezone.utc)

    if dry_run:
        for code, data in by_code.items():
            logger.info("(simule) %s -> %s", code, {k: v for k, v in data.items() if v})
        stats["updated"] = 0
        return stats

    # Bulk via table temporaire + UPDATE...FROM (1 aller-retour reseau au lieu
    # de len(by_code) UPDATE individuels) -- meme pattern que load_produit()
    # dans load.py. Le mode ligne-a-ligne precedent depassait le timeout de la
    # session d'execution sur > 1000 articles (constate 02/07).
    import pandas as pd
    pcb_cols = ["ean13", "ean14_pcb", "ean14_spcb", "pcb", "spcb",
                "longueur_pcb_cm", "largeur_pcb_cm", "hauteur_pcb_cm", "poids_pcb_kg"]
    rows = []
    for code, data in by_code.items():
        row = {"code_article": code, **{c: data.get(c) for c in pcb_cols}}
        rows.append(row)
    df_tmp = pd.DataFrame(rows)

    updated = 0
    with achat_engine.begin() as ca:
        df_tmp.to_sql("_tmp_enrich_dim", ca, schema="achat", if_exists="replace",
                      index=False, method="multi", chunksize=500)
        result = ca.execute(text("""
            UPDATE achat.produit p SET
                ean13 = COALESCE(NULLIF(t.ean13, ''), p.ean13),
                ean14_pcb = COALESCE(NULLIF(t.ean14_pcb, ''), p.ean14_pcb),
                ean14_spcb = COALESCE(NULLIF(t.ean14_spcb, ''), p.ean14_spcb),
                pcb = COALESCE(t.pcb::numeric::integer, p.pcb),
                spcb = COALESCE(t.spcb::numeric::integer, p.spcb),
                longueur_pcb_cm = COALESCE(t.longueur_pcb_cm::numeric, p.longueur_pcb_cm),
                largeur_pcb_cm = COALESCE(t.largeur_pcb_cm::numeric, p.largeur_pcb_cm),
                hauteur_pcb_cm = COALESCE(t.hauteur_pcb_cm::numeric, p.hauteur_pcb_cm),
                poids_pcb_kg = COALESCE(t.poids_pcb_kg::numeric, p.poids_pcb_kg),
                source_dimensions = 'sylob_v25',
                sylob_dimensions_synced_at = :synced
            FROM achat._tmp_enrich_dim t
            WHERE p.code_article = t.code_article
        """), {"synced": now})
        updated = result.rowcount
        ca.execute(text("DROP TABLE IF EXISTS achat._tmp_enrich_dim;"))
    stats["updated"] = updated
    return stats


def run(dry_run: bool) -> None:
    for noisy in ("azure.core.pipeline", "azure.identity", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    sys.path.insert(0, ".")
    from src.utils.config_manager import Config
    from sqlalchemy import create_engine

    achat_engine = create_engine(Config.get_pg_url())
    sylob_engine = create_engine(Config.get_sylob_url(), connect_args={"connect_timeout": 10})

    ensure_source_columns(achat_engine)
    stats = enrich(achat_engine, sylob_engine, dry_run)

    sep = "=" * 55
    logger.info(sep)
    logger.info("  Enrichissement dimensions/packaging Sylob -> produit")
    logger.info(sep)
    logger.info("  Articles total     : %d", stats["total"])
    logger.info("  Match Sylob        : %d", stats["match_total"])
    logger.info("  Non trouves        : %d", stats["non_trouves"])
    if dry_run:
        logger.info("  [DRY-RUN] %d article(s) simules -- ROLLBACK, rien n'est ecrit.", stats["match_total"])
    else:
        logger.info("  [COMMIT] %d article(s) mis a jour.", stats["updated"])
    logger.info(sep)


def main() -> int:
    ap = argparse.ArgumentParser(description="Enrichit achat.produit avec dimensions/packaging Sylob.")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    run(dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
