"""
Extraction des fichiers Excel du service Achats.
Chaque fonction retourne un DataFrame pandas brut (colonnes originales conservées).
"""
import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


def extract_matrice(file_path: str | Path) -> pd.DataFrame:
    """
    Lit Matrice TB Import.xlsx, onglet 'Lot-Vrac Produits uniques'.

    Structure particulière : header sur la ligne 2 (index 0-based),
    et la colonne Référence n'est renseignée qu'une fois par groupe de variantes.
    Le ffill() est appliqué ici pour propager la référence vers le bas.

    Args:
        file_path: Chemin vers Matrice TB Import.xlsx
    Returns:
        DataFrame avec colonnes nommées et Référence propagée.
    """
    path = Path(file_path)
    logger.info("Extraction Matrice TB Import : %s", path.name)

    df = pd.read_excel(path, sheet_name="Lot-Vrac Produits uniques", header=2)

    # Propager la référence (structure hiérarchique Excel)
    df["Référence"] = df["Référence"].ffill()

    # Supprimer les lignes sans aucune donnée utile
    df = df.dropna(subset=["Référence"])

    logger.info("Matrice extraite : %d lignes, %d colonnes", len(df), len(df.columns))
    return df


def extract_import(file_path: str | Path) -> pd.DataFrame:
    """
    Lit IMPORT 2026.xlsx, onglet 'IMPORT 2025'.

    Structure particulière : les 3 premières lignes sont des en-têtes
    administratifs (EORI, SIREN, etc.). Le vrai header est à la ligne 3 (index 3).

    Args:
        file_path: Chemin vers IMPORT 2026.xlsx
    Returns:
        DataFrame avec les colonnes du suivi de commandes.
    """
    path = Path(file_path)
    logger.info("Extraction IMPORT 2026 : %s", path.name)

    df = pd.read_excel(path, sheet_name="IMPORT 2025", header=3)

    # Supprimer les lignes sans PO# (lignes vides ou sous-totaux)
    df = df.dropna(subset=["PO#"])

    logger.info("Import extrait : %d commandes", len(df))
    return df


def extract_dimensions(file_path: str | Path) -> pd.DataFrame:
    """
    Lit Base article dimensions volume.xlsx.

    Structure propre avec header en ligne 0 — pas de transformation nécessaire.

    Args:
        file_path: Chemin vers Base article dimensions volume.xlsx
    Returns:
        DataFrame avec colonnes logistiques par article.
    """
    path = Path(file_path)
    logger.info("Extraction Base dimensions : %s", path.name)

    df = pd.read_excel(path, header=0)

    # Nettoyer le BOM éventuel sur la colonne Référence
    df.columns = [c.lstrip("﻿") for c in df.columns]
    df = df.dropna(subset=["Référence"])

    logger.info("Dimensions extraites : %d articles", len(df))
    return df
