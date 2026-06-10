# -*- coding: utf-8 -*-
"""
[DATA ENGINEERING]
Enrichissement de achat.produit depuis le DWH Sylob On-Premise (tarrerias_production_dwh).

Stratégie : la table achat.produit contient les articles issus des fichiers Excel
Achats. Ce script la complète avec les données de référence Sylob (ERP TB Groupe) :
prix d'achat, délai réappro, désignation officielle. Trois schémas correspondant
aux trois entités juridiques (GDD, SE, CIE) sont interrogés en cascade -- le premier
schéma qui répond pour un code article ou un EAN13 gagne (priorité GDD > SE > CIE).
Ce script nécessite un accès réseau au serveur Sylob (VPN Stormshield obligatoire).
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
    """
    Jointure directe sur code_article dans un schéma Sylob donné.

    Junior Tip : La jointure par batch (voir enrich_produits) découpe la liste
    en tranches de 200 pour éviter de dépasser la limite de paramètres SQL
    ou de générer une requête IN() trop longue que le parseur PostgreSQL refuse.

    Args:
        codes: Liste de codes articles à rechercher.
        schema: Nom du schéma Sylob (ex: 'TARRERIAS_GENERALE_DE_DECOUPAGE_Article').
        conn: Connexion SQLAlchemy active sur tarrerias_production_dwh.
    Returns:
        Dictionnaire {code_article: data_sylob}.
    """
    from sqlalchemy import bindparam, text
    if not codes:
        return {}
    # Paramètre bindé "expanding" : SQLAlchemy génère IN (:v1, :v2, ...) côté
    # driver -- jamais de valeurs concaténées dans le SQL (anti-injection,
    # standard etl-tb). Le nom de schéma reste interpolé car il provient de la
    # constante interne SCHEMAS, pas d'une donnée externe.
    stmt = text(f"""
        SELECT code_article, code_gtin_13, designation,
               CASE WHEN poids_unitaire > 0 THEN poids_unitaire * 1000 ELSE NULL END,
               volume_unitaire,
               CASE WHEN dernier_prix_d_achat > 0 THEN dernier_prix_d_achat ELSE NULL END,
               delai_de_reapprovisionnement
        FROM "{schema}".af_article
        WHERE code_article IN :codes
    """).bindparams(bindparam("codes", expanding=True))
    rows = conn.execute(stmt, {"codes": codes}).fetchall()
    return {r[0]: _to_dict(r, schema) for r in rows}


def fetch_sylob_by_ean(eans: list[str], schema: str, conn) -> dict[str, dict]:
    """
    Jointure par EAN13 dans un schéma Sylob donné -- retourne {ean: data_sylob}.

    Ce fallback est nécessaire quand le code article de la Matrice Excel ne
    correspond pas au code article Sylob (cas fréquent pour les articles
    récents ou les articles GDD pas encore intégrés dans SE/CIE).

    Args:
        eans: Liste d'EAN13 à rechercher.
        schema: Nom du schéma Sylob.
        conn: Connexion SQLAlchemy active sur tarrerias_production_dwh.
    Returns:
        Dictionnaire {ean13: data_sylob}.
    """
    from sqlalchemy import bindparam, text
    if not eans:
        return {}
    # Même pattern anti-injection que fetch_sylob_by_code (bindparam expanding)
    stmt = text(f"""
        SELECT code_article, code_gtin_13, designation,
               CASE WHEN poids_unitaire > 0 THEN poids_unitaire * 1000 ELSE NULL END,
               volume_unitaire,
               CASE WHEN dernier_prix_d_achat > 0 THEN dernier_prix_d_achat ELSE NULL END,
               delai_de_reapprovisionnement
        FROM "{schema}".af_article
        WHERE code_gtin_13 IN :eans
    """).bindparams(bindparam("eans", expanding=True))
    rows = conn.execute(stmt, {"eans": eans}).fetchall()
    return {r[1]: _to_dict(r, schema) for r in rows}  # keyed by EAN


def _to_dict(r, schema: str) -> dict:
    # Déduire la société depuis le nom du schéma pour tracer l'origine de la donnée
    # et permettre des analyses par entité juridique dans le dashboard
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
    """
    Ajoute les colonnes Sylob à achat.produit si elles n'existent pas encore.

    ADD COLUMN IF NOT EXISTS est idempotent -- on peut appeler cette fonction
    à chaque exécution sans risque d'erreur, même si les colonnes existent déjà.
    C'est le pattern de migration "forward-only" sans outil de migration dédié.

    Junior Tip : ALTER TABLE avec ADD COLUMN IF NOT EXISTS est disponible depuis
    PostgreSQL 9.6. Contrairement à CREATE TABLE IF NOT EXISTS, cette instruction
    n'est pas standard SQL -- elle est spécifique à PostgreSQL.

    Args:
        engine: SQLAlchemy engine connecté à achat (PostgreSQL bitb-2025).
    Returns:
        None
    """
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
    logger.info("[SUCCÈS] Colonnes Sylob vérifiées.")


def enrich_produits(achat_engine, sylob_engine) -> dict[str, int]:
    """
    Enrichit achat.produit avec les données de référence Sylob (prix, délais, désignations).

    Algorithme en deux passes :
    1. Collecte tous les codes/EAN depuis achat.produit
    2. Pour chaque schéma Sylob (GDD -> SE -> CIE), récupère les données manquantes
       en batch et consolide les résultats (premier schéma qui répond gagne)
    3. UPDATE en base article par article avec les données trouvées

    Junior Tip : L'ordre GDD -> SE -> CIE n'est pas arbitraire -- GDD est l'entité
    qui gère les imports Chine, donc elle a le plus de chances de matcher les articles
    de la Matrice TB Import. SE et CIE sont des fallbacks pour les articles multi-entités.

    Args:
        achat_engine: SQLAlchemy engine connecté à PostgreSQL bitb-2025 (schéma achat).
        sylob_engine: SQLAlchemy engine connecté à tarrerias_production_dwh (Sylob).
    Returns:
        Dictionnaire de statistiques : total, match_code, match_ean, non_trouves.
    """
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
    logger.info("[INFO] Articles à traiter : %d (%d avec EAN)", len(all_codes), len(all_eans))

    batch = 200

    # Construire les mappings consolidés : {code: data} et {ean: data}
    # Stratégie "first wins" : GDD -> SE -> CIE -- on n'écrase pas un match
    # déjà trouvé dans un schéma prioritaire avec un résultat d'un schéma secondaire
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

    logger.info("[INFO] Total match code_article : %d | Total match EAN : %d",
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
        format="%(asctime)s [%(levelname)s] %(name)s  -- %(message)s")
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
    sep = "=" * 55
    logger.info(sep)
    logger.info("  Rapport enrichissement Sylob v3  -- multi-schéma")
    logger.info(sep)
    logger.info("  Articles total             : %d", stats["total"])
    logger.info("  Match code_article (total) : %d", stats["match_code"])
    logger.info("  Match EAN13 (fallback)     : %d", stats["match_ean"])
    logger.info("  Total enrichis             : %d", total_enrichis)
    logger.info("  Vraiment absents Sylob     : %d", stats["non_trouves"])
    logger.info("  Taux couverture            : %.1f%%",
                total_enrichis / stats["total"] * 100)
    logger.info(sep)
    logger.info("  Détail par schéma :")
    schema_keys = {
        s: s.split("_Article")[0].split("TARRERIAS_")[-1][:6]
        for s in SCHEMAS
    }
    for schema, key in schema_keys.items():
        code_n = stats.get(f"schema_{key}_code", 0)
        ean_n  = stats.get(f"schema_{key}_ean", 0)
        label = schema.replace("_Article", "")
        for pfx in ["TARRERIAS_GENERALE_DE_DECOUPAGE", "TARRERIAS_SE_TARRERIAS_BONJEAN",
                    "TARRERIAS_TARRERIAS_BONJEAN_ET_CIE"]:
            if schema.startswith(pfx):
                label = pfx.replace("TARRERIAS_", "").replace("_", " ")
                break
        logger.info("    %-38s code=%4d  ean=%3d", label, code_n, ean_n)
    logger.info(sep)


if __name__ == "__main__":
    run()
                                     