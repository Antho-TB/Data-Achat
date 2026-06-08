"""
Enrichissement achat.produit depuis tarrerias_production_dwh.
Trois schémas Sylob interrogés en cascade (GDD → SE → CIE) :
  - TARRERIAS_GENERALE_DE_DECOUPAGE_Article  → produits GDD/import Chine
  - TARRERIAS_SE_TARRERIAS_BONJEAN_Article   → catalogue TB principal (SE)
  - TARRERIAS_TARRERIAS_BONJEAN_ET_CIE_Article → CIE
Deux stratégies de jointure par schéma :
  1. code_article exact (match direct)
  2. EAN13 (fallback quand le code article diffère)
"""
import logging
import sys
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

SCHEMAS = [
    "TARRERIAS_GENERALE_DE_DECOUPAGE_Article",
    "TARRERIAS_SE_TARRERIAS_BONJEAN_Article",
    "TARRERIAS_TARRERIAS_BONJEAN_ET_CIE_Article",
]


def fetch_sylob_by_code(codes: list[str], schema: str, conn) -> dict[str, dict]:
    """Jointure directe sur code_article dans un schéma donné."""
    from sqlalchemy import text
    if not codes:
        return {}
    ph = "','".join(codes)
    rows = conn.execute(text(f"""
        SELECT code_article, code_gtin_13, designation,
               CASE WHEN poids_unitaire > 0 THEN poids_unitaire * 1000 ELSE NULL END,
               volume_unitaire,
               CASE WHEN dernier_prix_d_achat > 0 THEN dernier_prix_d_achat ELSE NULL END,
               delai_de_reapprovisionnement
        FROM "{schema}".af_article
        WHERE code_article IN ('{ph}')
    """)).fetchall()
    return {r[0]: _to_dict(r, schema) for r in rows}


def fetch_sylob_by_ean(eans: list[str], schema: str, conn) -> dict[str, dict]:
    """Jointure par EAN13 dans un schéma donné — retourne {ean: data_sylob}."""
    from sqlalchemy import text
    if not eans:
        return {}
    ph = "','".join(eans)
    rows = conn.execute(text(f"""
        SELECT code_article, code_gtin_13, designation,
               CASE WHEN poids_unitaire > 0 THEN poids_unitaire * 1000 ELSE NULL END,
               volume_unitaire,
               CASE WHEN dernier_prix_d_achat > 0 THEN dernier_prix_d_achat ELSE NULL END,
               delai_de_reapprovisionnement
        FROM "{schema}".af_article
        WHERE code_gtin_13 IN ('{ph}')
    """)).fetchall()
    return {r[1]: _to_dict(r, schema) for r in rows}  # keyed by EAN


def _to_dict(r, schema: str) -> dict:
    # Déduire la société depuis le schéma
    if "SE_TARRERIAS_BONJEAN" in schema:
        societe = "SE"
    elif "TARRERIAS_BONJEAN_ET_CIE" in schema:
        societe = "CIE"
    else:
        societe = "GDD"
    return {
        "sylob_code_article": r[0],
        "ean13": r[1],
        "designation_fr_sylob": r[2],
        "poids_uvc_g_sylob": float(r[3]) if r[3] else None,
        "volume_m3_sylob": float(r[4]) if r[4] else None,
        "dernier_prix_sylob": float(r[5]) if r[5] else None,
        "delai_reappro_jours": r[6],
        "sylob_societe": societe,
    }


def ensure_sylob_columns(engine) -> None:
    from sqlalchemy import text
    with engine.begin() as conn:
        conn.execute(text("""
            ALTER TABLE achat.produit
              ADD COLUMN IF NOT EXISTS delai_reappro_jours   INTEGER,
              ADD COLUMN IF NOT EXISTS sylob_last_price      NUMERIC,
              ADD COLUMN IF NOT EXISTS sylob_code_article    TEXT,
              ADD COLUMN IF NOT EXISTS sylob_match_type      TEXT,
              ADD COLUMN IF NOT EXISTS sylob_synced_at       TIMESTAMPTZ,
              ADD COLUMN IF NOT EXISTS sylob_societe         TEXT;
        """))
    logger.info("Colonnes Sylob vérifiées.")


def enrich_produits(achat_engine, sylob_engine) -> dict[str, int]:
    from sqlalchemy import text

    stats: dict[str, int] = {
        "total": 0,
        "match_code": 0,
        "match_ean": 0,
        "non_trouves": 0,
    }
    # stats par schéma
    for s in SCHEMAS:
        key = s.split("_Article")[0].split("TARRERIAS_")[-1][:6]
        stats[f"schema_{key}_code"] = 0
        stats[f"schema_{key}_ean"] = 0

    with achat_engine.connect() as ca:
        rows = ca.execute(text("""
            SELECT code_article, COALESCE(ean13,'') FROM achat.produit
            WHERE code_article IS NOT NULL AND code_article != ''
        """)).fetchall()

    all_codes = [r[0] for r in rows]
    all_eans  = [r[1] for r in rows if r[1] and len(r[1]) > 8]
    stats["total"] = len(all_codes)
    logger.info("Articles à traiter : %d (%d avec EAN)", len(all_codes), len(all_eans))

    batch = 200

    # Construire les mappings consolidés : {code: data} {ean: data}
    # Premier schéma qui répond gagne (GDD → SE → CIE)
    by_code: dict[str, dict] = {}
    by_ean:  dict[str, dict] = {}

    with sylob_engine.connect() as cs:
        for schema in SCHEMAS:
            # Codes non encore trouvés
            codes_remaining = [c for c in all_codes if c not in by_code]
            eans_remaining  = [e for e in all_eans  if e not in by_ean]

            schema_code: dict[str, dict] = {}
            schema_ean:  dict[str, dict] = {}

            for i in range(0, len(codes_remaining), batch):
                schema_code.update(
                    fetch_sylob_by_code(codes_remaining[i:i+batch], schema, cs)
                )
            for i in range(0, len(eans_remaining), batch):
                schema_ean.update(
                    fetch_sylob_by_ean(eans_remaining[i:i+batch], schema, cs)
                )

            by_code.update(schema_code)
            by_ean.update(schema_ean)

            key = schema.split("_Article")[0].split("TARRERIAS_")[-1][:6]
            stats[f"schema_{key}_code"] = len(schema_code)
            stats[f"schema_{key}_ean"] = len(schema_ean)
            logger.info(
                "Schéma %-45s  code=%d  ean=%d",
                schema, len(schema_code), len(schema_ean)
            )

    logger.info("Total match code_article : %d | Total match EAN : %d",
                len(by_code), len(by_ean))

    now = datetime.now(timezone.utc)

    with achat_engine.begin() as ca:
        for code, ean in [(r[0], r[1]) for r in rows]:
            data = None
            match_type = None

            if code in by_code:
                data = by_code[code]
                match_type = "code_article"
                stats["match_code"] += 1
            elif ean and ean in by_ean:
                data = by_ean[ean]
                match_type = "ean13"
                stats["match_ean"] += 1
            else:
                stats["non_trouves"] += 1
                continue

            ca.execute(text("""
                UPDATE achat.produit SET
                    ean13 = COALESCE(NULLIF(ean13,''), :ean13),
                    designation_fr = COALESCE(NULLIF(designation_fr,''), :desig),
                    poids_uvc_g = COALESCE(poids_uvc_g, :poids),
                    volume_m3 = COALESCE(volume_m3, :vol),
                    delai_reappro_jours = :delai,
                    sylob_last_price = :prix,
                    sylob_code_article = :sylob_code,
                    sylob_match_type = :match_type,
                    sylob_synced_at = :synced,
                    sylob_societe = :societe
                WHERE code_article = :code
            """), {
                "ean13": data["ean13"],
                "desig": data["designation_fr_sylob"],
                "poids": data["poids_uvc_g_sylob"],
                "vol": data["volume_m3_sylob"],
                "delai": data["delai_reappro_jours"],
                "prix": data["dernier_prix_sylob"],
                "sylob_code": data["sylob_code_article"],
                "match_type": match_type,
                "synced": now,
                "societe": data["sylob_societe"],
                "code": code,
            })

    return stats


def run() -> None:
    logging.basicConfig(level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s")
    for noisy in ("azure.core.pipeline", "azure.identity", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    sys.path.insert(0, ".")
    from src.utils.config_manager import Config
    from sqlalchemy import create_engine

    achat_engine = create_engine(Config.get_pg_url())
    sylob_engine = create_engine(Config.get_sylob_url(),
                                 connect_args={"connect_timeout": 10})

    ensure_sylob_columns(achat_engine)
    stats = enrich_produits(achat_engine, sylob_engine)

    total_enrichis = stats["match_code"] + stats["match_ean"]
    print("\n" + "=" * 55)
    print("  Rapport enrichissement Sylob v3 — multi-schéma")
    print("=" * 55)
    print(f"  Articles total             : {stats['total']}")
    print(f"  Match code_article (total) : {stats['match_code']}")
    print(f"  Match EAN13 (fallback)     : {stats['match_ean']}")
    print(f"  Total enrichis             : {total_enrichis}")
    print(f"  Vraiment absents Sylob     : {stats['non_trouves']}")
    print(f"  Taux couverture            : {total_enrichis / stats['total'] * 100:.1f}%")
    print("=" * 55)
    print("  Détail par schéma :")
    # Clés construites de façon cohérente avec enrich_produits()
    schema_keys = {
        s: s.split("_Article")[0].split("TARRERIAS_")[-1][:6]
        for s in SCHEMAS
    }
    for schema, key in schema_keys.items():
        code_n = stats.get(f"schema_{key}_code", 0)
        ean_n  = stats.get(f"schema_{key}_ean", 0)
        # Label lisible : retire préfixe TARRERIAS_ commun
        label = schema.replace("_Article", "")
        for pfx in ["TARRERIAS_GENERALE_DE_DECOUPAGE", "TARRERIAS_SE_TARRERIAS_BONJEAN",
                    "TARRERIAS_TARRERIAS_BONJEAN_ET_CIE"]:
            if schema.startswith(pfx):
                label = pfx.replace("TARRERIAS_", "").replace("_", " ")
                break
        print(f"    {label:<38} code={code_n:4d}  ean={ean_n:3d}")
    print("=" * 55)


if __name__ == "__main__":
    run()
