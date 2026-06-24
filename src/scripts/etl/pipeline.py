# -*- coding: utf-8 -*-
"""
=============================================================================
ETL ACHATS - ORCHESTRATEUR (Extract -> Transform -> Load)
=============================================================================

Pipeline ETL principal du projet Data-Achat TB Groupe.

Stratégie : ce module est le point d'entrée unique qui orchestre les trois
étapes Extract -> Transform -> Load. Il gère les erreurs à chaque étape de
façon indépendante (une erreur en LOAD ne masque pas les stats TRANSFORM)
et supporte un mode --dry-run pour valider les fichiers sans toucher la DB.
Ce pipeline couvre principalement le Circuit B (réappro) et les imports Chine.

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
    """
    Localise le répertoire Service_Achat depuis la racine du projet.

    Junior Tip : get_base_path() gère deux cas d'exécution distincts --
    le mode script normal (Path(__file__)) et le mode PyInstaller (sys.executable).
    Cette abstraction permet de packager le pipeline en .exe sans modifier ce code.

    Returns:
        Path vers le répertoire contenant les fichiers Excel source.
    Raises:
        FileNotFoundError: Si le répertoire DATA_DIR n'existe pas.
    """
    from src.utils.config_manager import Config, get_base_path
    base = get_base_path()
    data_dir = base / Config.DATA_DIR
    if not data_dir.exists():
        raise FileNotFoundError(f"Répertoire introuvable : {data_dir}")
    return data_dir


def run(dry_run: bool = False) -> dict[str, int]:
    """
    Exécute le pipeline ETL complet (Extract -> Transform -> Load).

    Chaque étape est encapsulée dans un try/except indépendant pour retourner
    des statistiques partielles même en cas d'erreur, plutôt que de propager
    une exception non gérée vers le scheduler ou l'appelant.

    Junior Tip : Le pattern "stats dict + erreurs += 1" permet au processus
    appelant (CI, orchestrateur n8n) de détecter un échec partiel via le
    compteur erreurs sans avoir à analyser les logs.

    Args:
        dry_run: Si True, skip le chargement PostgreSQL (test extract+transform).
    Returns:
        Dictionnaire avec les compteurs : produits, commandes, erreurs.
    """
    from src.scripts.etl.extract import (
        extract_dimensions,
        extract_import,
        extract_matrice,
        extract_suivi_maritime,
    )
    from src.scripts.etl.transform import (
        transform_artwork,
        transform_commande,
        transform_ot_transport,
        transform_produit,
        transform_qualite,
        transform_acompte,
    )
    from src.utils.config_manager import Config

    stats: dict[str, int] = {
        "produits": 0, "commandes": 0, "artwork": 0, "ot_transport": 0, "qualite": 0, "acompte": 0, "erreurs": 0
    }
    data_dir = _get_data_dir()

    # ── EXTRACT ──────────────────────────────────────────────────────────────
    logger.info("[INFO] === EXTRACT ===")
    try:
        df_matrice = extract_matrice(data_dir / "Matrice TB Import.xlsx")
        df_dimensions = extract_dimensions(data_dir / "Base article dimensions volume.xlsx")
        df_import = extract_import(data_dir / "IMPORT 2026.xlsx")
        # Source transitaire (None si dossier non accessible -> bootstrap commande)
        df_maritime = extract_suivi_maritime(Config.SUIVI_MARITIME_PATH or None)
    except Exception as exc:
        logger.error("[ÉCHEC] Pipeline interrompu -- extraction impossible : %s", exc, exc_info=True)
        stats["erreurs"] += 1
        return stats

    # ── TRANSFORM ────────────────────────────────────────────────────────────
    logger.info("[INFO] === TRANSFORM ===")
    try:
        df_produit = transform_produit(df_matrice, df_dimensions)
        df_commande = transform_commande(df_import)
        df_artwork = transform_artwork(df_import)
        df_ot_transport = transform_ot_transport(df_commande, df_maritime)
        df_qualite = transform_qualite(df_import)
        df_acompte = transform_acompte(df_import)
    except Exception as exc:
        logger.error("[ÉCHEC] Pipeline interrompu -- transformation impossible : %s", exc, exc_info=True)
        stats["erreurs"] += 1
        return stats

    # ── RAPPORT DRY-RUN ──────────────────────────────────────────────────────
    if dry_run:
        logger.info("[INFO] === DRY-RUN -- pas d'écriture PostgreSQL ===")
        _print_report(df_produit, df_commande, dry_run=True)
        stats["produits"] = len(df_produit)
        stats["commandes"] = len(df_commande)
        return stats

    # ── LOAD ─────────────────────────────────────────────────────────────────
    logger.info("[INFO] === LOAD ===")
    try:
        from sqlalchemy import create_engine
        from src.utils.config_manager import Config
        from src.scripts.etl.load import create_tables_if_not_exist, load_commande, load_produit

        from src.scripts.etl.load import load_artwork, load_ot_transport, load_qualite, load_acompte

        engine = create_engine(Config.get_pg_url())
        create_tables_if_not_exist(engine)
        stats["produits"] = load_produit(df_produit, engine)
        stats["commandes"] = load_commande(df_commande, engine)
        stats["artwork"] = load_artwork(df_artwork, engine)
        stats["ot_transport"] = load_ot_transport(df_ot_transport, engine)
        stats["qualite"] = load_qualite(df_qualite, engine)
        stats["acompte"] = load_acompte(df_acompte, engine)
    except Exception as exc:
        logger.error("[ERREUR] Chargement PostgreSQL échoué : %s", exc, exc_info=True)
        stats["erreurs"] += 1

    _print_report(df_produit, df_commande, dry_run=False)
    return stats


def _print_report(
    df_produit: "pd.DataFrame",
    df_commande: "pd.DataFrame",
    dry_run: bool,
) -> None:
    """
    Affiche un rapport lisible du résultat du pipeline dans les logs.

    La répartition des statuts commandes permet de détecter rapidement
    des anomalies (ex: 0 commande "En cours" alors qu'il devrait y en avoir).

    Args:
        df_produit: DataFrame produit transformé.
        df_commande: DataFrame commande transformé.
        dry_run: True si le pipeline a été exécuté en mode test.
    Returns:
        None
    """
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
 