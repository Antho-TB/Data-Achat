# -*- coding: utf-8 -*-
"""
[ETL]
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
import re
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
    raw_path = Path(Config.DATA_DIR)
    data_dir = raw_path if raw_path.is_absolute() else get_base_path() / raw_path
    if not data_dir.exists():
        raise FileNotFoundError(f"Répertoire introuvable : {data_dir}")
    return data_dir


# Emplacements des sources Excel sur le partage réseau
# \\<serveur>\partage\ADA\METIER\SUIVI CDES IMPORT (compte de service AD).
#
# Chaque source déclare des chemins relatifs EXPLICITES, essayés dans l'ordre,
# puis un motif de repli. Le repli est volontairement strict et ancré en début
# de nom de fichier.
#
# Junior Tip : le motif large "*IMPORT*.xlsx" semblait pratique, mais le glob
# Windows est insensible à la casse : il attrapait aussi
# "LIS-ACH-53-0-Matrice TB Import.xlsx", plus récemment modifié, donc classé
# premier. Le pipeline lisait la Matrice en croyant lire l'IMPORT et mourait
# sur "Aucun onglet 'IMPORT <annee>'". Une recherche floue sur un partage
# réseau de plusieurs milliers de fichiers finit toujours par trouver le
# mauvais : on nomme les chemins attendus, et le flou ne sert que de secours.
SOURCES_EXCEL: dict[str, dict[str, object]] = {
    "import": {
        "libelle": "IMPORT de l'année",
        "chemins": ["2026/IMPORT 2026.xlsx", "IMPORT 2026.xlsx"],
        "motif": r"^IMPORT \d{4}\.xlsx$",
        "dossiers": ["2026", "."],
    },
    "matrice": {
        "libelle": "Matrice TB Import",
        "chemins": ["PRODUITS/LIS-ACH-53-0-Matrice TB Import.xlsx",
                    "Matrice TB Import.xlsx"],
        "motif": r"^(LIS-ACH-\d+-\d+-)?Matrice TB Import\.xlsx$",
        "dossiers": ["PRODUITS", "."],
    },
    "dimensions": {
        "libelle": "Base article dimensions volume",
        "chemins": ["PRODUITS/Base article dimensions volume.xlsx",
                    "Base article dimensions volume.xlsx"],
        "motif": r"^Base article dimensions volume\.xlsx$",
        "dossiers": ["PRODUITS", "."],
    },
}

# Fichiers à ignorer quel que soit le motif : verrous Excel et copies de travail.
PREFIXES_IGNORES = ("~$",)
MOTIFS_IGNORES = ("copie de", "copy of", " - copie", "ancien", "old", "backup", "sauvegarde")


def _fichier_ignorable(nom: str) -> bool:
    """Ecarte les verrous Excel et les copies de travail laissées sur le partage."""
    minuscule = nom.lower()
    return (nom.startswith(PREFIXES_IGNORES)
            or any(motif in minuscule for motif in MOTIFS_IGNORES))


def _find_file(data_dir: Path, cle_source: str) -> Path:
    """
    Localise une source Excel sur le partage réseau.

    Args:
        data_dir: racine du partage (`Config.DATA_DIR`).
        cle_source: clé de `SOURCES_EXCEL` ("import", "matrice", "dimensions").
    Returns:
        Chemin du fichier retenu.
    Raises:
        FileNotFoundError: si aucun candidat ne correspond au motif attendu.
    """
    source = SOURCES_EXCEL[cle_source]
    libelle = source["libelle"]
    motif = re.compile(source["motif"], re.IGNORECASE)

    # 1. Chemins explicites, dans l'ordre de préférence.
    for relatif in source["chemins"]:
        candidat = data_dir / relatif
        if candidat.exists() and not _fichier_ignorable(candidat.name):
            logger.info("[INFO] %s : %s", libelle, candidat)
            return candidat

    # 2. Repli : balayage des seuls dossiers attendus, filtré par motif strict.
    #    Pas de parcours récursif du partage : les archives des années
    #    précédentes contiennent des IMPORT 2023, 2024, 2025 qui matcheraient.
    candidats: list[Path] = []
    for dossier in source["dossiers"]:
        racine = (data_dir / dossier).resolve() if dossier != "." else data_dir
        if not racine.exists():
            continue
        for fichier in racine.glob("*.xlsx"):
            if not _fichier_ignorable(fichier.name) and motif.match(fichier.name):
                candidats.append(fichier)

    if candidats:
        retenu = max(candidats, key=lambda p: p.stat().st_mtime)
        if len(candidats) > 1:
            logger.warning("[ATTENTION] %d fichiers correspondent pour %s, le plus récent est "
                           "retenu : %s", len(candidats), libelle, retenu)
        logger.info("[INFO] %s : %s", libelle, retenu)
        return retenu

    raise FileNotFoundError(
        f"{libelle} introuvable. Cherché aux emplacements "
        f"{source['chemins']} puis par motif {source['motif']} dans "
        f"{source['dossiers']}, sous {data_dir}."
    )


def run(dry_run: bool = False) -> dict[str, int]:
    """
    Exécute le pipeline ETL complet (Extract -> Transform -> Load).

    Chaque étape est encapsulée dans un try/except indépendant pour retourner
    au processus appelant (CI, orchestrateur n8n) de détecter un échec partiel
    via le compteur erreurs sans avoir à analyser les logs.

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
        "produits": 0, "commandes": 0, "artwork": 0, "ot_transport": 0, "qualite": 0,
        "acompte": 0, "receptions_sylob": 0, "enrichissements_appliques": 0, "erreurs": 0
    }
    data_dir = _get_data_dir()

    # ── EXTRACT ──────────────────────────────────────────────────────────────
    logger.info("[INFO] === EXTRACT ===")
    try:
        f_matrice = _find_file(data_dir, "matrice")
        f_dimensions = _find_file(data_dir, "dimensions")
        f_import = _find_file(data_dir, "import")

        df_matrice = extract_matrice(f_matrice)
        df_dimensions = extract_dimensions(f_dimensions)
        df_import = extract_import(f_import)
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

    # ── ENRICH ───────────────────────────────────────────────────────────────
    # Etape obligatoire APRES le LOAD : achat.commande et achat.qualite viennent
    # d'etre videes puis rechargees depuis l'Excel. Tout ce qui ne vient pas de
    # ce fichier (reception physique Sylob, non-conformite signalee par mail)
    # est stocke a part dans achat.commande_enrichissement et doit etre
    # reprojete ici, sinon l'information disparait de l'application chaque nuit.
    logger.info("[INFO] === ENRICH ===")
    try:
        from src.scripts.etl.apply_enrichissement import apply_enrichissement
        from src.scripts.etl.enrich_reception_sylob import enrich_receptions_sylob

        stats["receptions_sylob"] = enrich_receptions_sylob()["enrichissements_ecrits"]
        applique = apply_enrichissement()
        stats["enrichissements_appliques"] = applique["commandes_maj"] + applique["qualite_maj"]
    except Exception as exc:
        logger.error("[ERREUR] Enrichissement post-chargement échoué : %s", exc, exc_info=True)
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
        for statut, n in df_commande["statut"].value_counts().items():
            logger.info("    - %-20s %6d", statut, n)
    logger.info(sep)


def main() -> int:
    """
    Point d'entree CLI -- python -m src.scripts.etl.pipeline [--dry-run].

    Junior Tip : ce garde-fou (if __name__ == "__main__") etait absent avant
    le 02/07 -- la commande documentee dans docs/plan_action.md n'executait
    donc rien (import silencieux, exit 0, aucun log). Corrige suite a l'audit
    de nettoyage AIOps du 02/07.
    """
    ap = argparse.ArgumentParser(description="Pipeline ETL Data-Achat (Extract -> Transform -> Load).")
    ap.add_argument("--dry-run", action="store_true",
                     help="Extract + Transform uniquement, sans écriture PostgreSQL.")
    args = ap.parse_args()

    stats = run(dry_run=args.dry_run)
    if stats.get("erreurs"):
        logger.error("[ÉCHEC] Pipeline terminé avec %d erreur(s).", stats["erreurs"])
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
 