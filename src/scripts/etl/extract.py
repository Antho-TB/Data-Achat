# -*- coding: utf-8 -*-
"""
[DATA ENGINEERING]
Extraction des fichiers Excel du service Achats TB Groupe vers des DataFrames pandas.

Stratégie : chaque fonction est responsable d'un seul fichier source et retourne
un DataFrame brut avec les colonnes originales conservées. Aucune transformation
métier n'est effectuée ici -- c'est le contrat Extract du pipeline ETL.
Les trois sources couvrent le catalogue produit (Matrice), le suivi commandes
(IMPORT) et les dimensions logistiques (Base article).
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

    Junior Tip : header=2 signifie que pandas saute les 2 premières lignes
    (index 0 et 1) et utilise la ligne d'index 2 comme noms de colonnes.
    C'est une convention fréquente dans les fichiers Excel de gestion où
    les premières lignes contiennent des métadonnées ou un logo.

    Args:
        file_path: Chemin vers Matrice TB Import.xlsx
    Returns:
        DataFrame avec colonnes nommées et Référence propagée.
    """
    path = Path(file_path)
    logger.info("[INFO] Extraction Matrice TB Import : %s", path.name)

    df = pd.read_excel(path, sheet_name="Lot-Vrac Produits uniques", header=2)

    # Propager la référence vers le bas car Excel ne répète pas la valeur
    # sur chaque ligne d'un groupe de variantes (économie de saisie côté acheteur)
    df["Référence"] = df["Référence"].ffill()

    # Supprimer les lignes entièrement vides qui apparaissent parfois
    # en bas de tableau quand Excel étend la plage nommée au-delà des données
    df = df.dropna(subset=["Référence"])

    logger.info("[SUCCÈS] Matrice extraite : %d lignes, %d colonnes", len(df), len(df.columns))
    return df


def extract_import(file_path: str | Path) -> pd.DataFrame:
    """
    Lit IMPORT 2026.xlsx, onglet 'IMPORT 2025'.

    Structure particulière : les 3 premières lignes sont des en-têtes
    administratifs (EORI, SIREN, etc.). Le vrai header est à la ligne 3 (index 3).

    Junior Tip : Les fichiers douaniers placent souvent les numéros EORI/SIREN
    en haut du tableur pour les déclarations officielles. header=3 permet de
    sauter ces 3 lignes administratives et d'atteindre le vrai tableau de données.

    Args:
        file_path: Chemin vers IMPORT 2026.xlsx
    Returns:
        DataFrame avec les colonnes du suivi de commandes.
    """
    path = Path(file_path)
    logger.info("[INFO] Extraction IMPORT 2026 : %s", path.name)

    df = pd.read_excel(path, sheet_name="IMPORT 2025", header=3)

    # Supprimer les lignes sans PO# -- ce sont soit des lignes vides,
    # soit des sous-totaux Excel qui n'ont pas de numéro de commande
    df = df.dropna(subset=["PO#"])

    logger.info("[SUCCÈS] Import extrait : %d commandes", len(df))
    return df


def extract_dimensions(file_path: str | Path) -> pd.DataFrame:
    """
    Lit Base article dimensions volume.xlsx.

    Structure propre avec header en ligne 0 -- pas de transformation nécessaire.

    Junior Tip : Le BOM (Byte Order Mark) est un caractère invisible U+FEFF
    que certains éditeurs Excel ajoutent en début de fichier UTF-8. Il se glisse
    parfois dans le nom de la première colonne et casse les jointures sur Référence.
    lstrip() l'élimine proprement.

    Args:
        file_path: Chemin vers Base article dimensions volume.xlsx
    Returns:
        DataFrame avec colonnes logistiques par article.
    """
    path = Path(file_path)
    logger.info("[INFO] Extraction Base dimensions : %s", path.name)

    df = pd.read_excel(path, header=0)

    # Supprimer le BOM éventuel (U+FEFF) sur le nom de la première colonne
    # pour garantir que les jointures sur "Référence" fonctionnent correctement
    df.columns = [c.lstrip("﻿") for c in df.columns]
    df = df.dropna(subset=["Référence"])

    logger.info("[SUCCÈS] Dimensions extraites : %d articles", len(df))
    return df


def extract_suivi_maritime(file_path: str | Path | None) -> pd.DataFrame | None:
    """
    Lit le fichier transitaire 2026 SUIVI MARITIME.xlsx, feuille 'CONTENEUR PLEIN'.

    Source de verite des ETD reel / ETA / Date livraison (manque n°7 carto BI).
    MODE DEGRADE : si le chemin est vide ou le fichier introuvable (dossier
    TRANSITAIRE pas encore accessible), retourne None sans lever d'exception --
    le pipeline bascule alors sur le bootstrap depuis achat.commande.

    Junior Tip : retourner None plutot que de planter permet de livrer le branchement
    AUJOURD'HUI et de l'activer le jour ou l'acces reseau est ouvert, sans toucher
    au code. Le contrat "None = source absente" est interprete par transform_ot_transport.

    Args:
        file_path: Chemin vers 2026 SUIVI MARITIME.xlsx (ou None pour forcer le degrade).
    Returns:
        DataFrame de la feuille CONTENEUR PLEIN, ou None si la source est absente.
    """
    if not file_path:
        logger.warning("[ATTENTION] SUIVI_MARITIME_PATH non defini -- mode degrade")
        return None
    path = Path(file_path)
    if not path.exists():
        logger.warning("[ATTENTION] Fichier transitaire introuvable (%s) -- mode degrade", path)
        return None
    logger.info("[INFO] Extraction SUIVI MARITIME : %s", path.name)
    df = pd.read_excel(path, sheet_name="CONTENEUR PLEIN")
    logger.info("[SUCCÈS] SUIVI MARITIME extrait : %d lignes", len(df))
    return df
