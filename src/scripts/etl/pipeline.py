"""
Pipeline ETL principal — Data-Achat
Orchestre extract → transform → load pour le Circuit B (réappro).

Usage :
    python -m src.etl.pipeline
    python -m src.etl.pipeline --dry-run   # Extract + Transform uniquement, sans écriture DB
"""
import argparse
import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
# Réduire le bruit des SDK Azure (trop verbeux en INFO)
for _noisy in ("azure", "urllib3", "msrest"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


def _get_data_dir() -> Path:
    """Localise le répertoire Service_Achat depuis la racine du projet."""
    from src.utils.config_manager import Config, get_base_path
    base = get_base_path()
    data_dir = base / Config.DATA_DIR
    if not data_dir.exists():
        raise FileNotFoundError(f"Répertoire introuvable : {data_dir}")
    return data_dir


def run(dry_run: bool = False) -> dict[str, int]:
    """
    Exécute le pipeline complet.

    Args:
        dry_run: Si True, skip le chargement PostgreSQL (test extract+transform).
    Returns:
        Dictionnaire avec les compteurs : produits, commandes, erreurs.
    """
    from src.scripts.etl.extract import extract_dimensions, extract_import, extract_matrice
    from src.scripts.etl.transform import transform_commande, transform_produit

    stats: dict[str, int] = {"produits": 0, "commandes": 0, "erreurs": 0}
    data_dir = _get_data_dir()

    # ── EXTRACT ──────────────────────────────────────────────────────────────
    logger.info("=== EXTRACT ===")
    try:
        df_matrice = extract_matrice(data_dir / "Matrice TB Import.xlsx")
        df_dimensions = extract_dimensions(data_dir / "Base article dimensions volume.xlsx")
        df_import = extract_import(data_dir / "IMPORT 2026.xlsx")
    except Exception as exc:
        logger.error("Échec extraction : %s", exc, exc_info=True)
        stats["erreurs"] += 1
        return stats

    # ── TRANSFORM ────────────────────────────────────────────────────────────
    logger.info("=== TRANSFORM ===")
    try:
        df_produit = transform_produit(df_matrice, df_dimensions)
        df_commande = transform_commande(df_import)
    except Exception as exc:
        logger.error("Échec transformation : %s", exc, exc_info=True)
        stats["erreurs"] += 1
        return stats

    # ── RAPPORT DRY-RUN ──────────────────────────────────────────────────────
    if dry_run:
        logger.info("=== DRY-RUN — pas d'écriture PostgreSQL ===")
        _print_report(df_produit, df_commande, dry_run=True)
        stats["produits"] = len(df_produit)
        stats["commandes"] = len(df_commande)
        return stats

    # ── LOAD ─────────────────────────────────────────────────────────────────
    logger.info("=== LOAD ===")
    try:
        from sqlalchemy import create_engine
        from src.utils.config_manager import Config
        from src.scripts.etl.load import create_tables_if_not_exist, load_commande, load_produit

        engine = create_engine(Config.get_pg_url())
        create_tables_if_not_exist(engine)
        stats["produits"] = load_produit(df_produit, engine)
        stats["commandes"] = load_commande(df_commande, engine)
    except Exception as exc:
        logger.error("Échec chargement PostgreSQL : %s", exc, exc_info=True)
        stats["erreurs"] += 1

    _print_report(df_produit, df_commande, dry_run=False)
    return stats


def _print_report(
    df_produit: "pd.DataFrame",
    df_commande: "pd.DataFrame",
    dry_run: bool,
) -> None:
    """Affiche un rapport lisible du résultat du pipeline."""
    import pandas as pd  # noqa: F401 (import local pour éviter dépendance circulaire)

    mode = "[DRY-RUN]" if dry_run else "[PROD]"
    sep = "=" * 50
    logger.info(sep)
    logger.info("  Rapport ETL Data-Achat %s", mode)
    logger.info(sep)
    logger.info("  Produits prêts     : %6d", len(df_produit))
    logger.info("  Commandes prêtes   : %6d", len(df_commande))

    if not df_commande.empty and "statut" in df_commande.columns:
        logger.info("  Répartition statuts commandes :")
        for statut, count in df_commande["statut"].value_counts().items():
            logger.info("    %-30s %4d", statut, count)
    logger.info(sep)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ETL Data-Achat")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Extract + Transform uniquement, sans écriture PostgreSQL"
    )
    args = parser.parse_args()

    stats = run(dry_run=args.dry_run)
    if stats["erreurs"] > 0:
        sys.exit(1)
