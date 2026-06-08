"""
Transformations métier — nettoyage et normalisation des données Achats.
"""
import logging
import re
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Regex pour extraire une date au format JJ/MM/AAAA
_DATE_PATTERN = re.compile(r"(\d{2})/(\d{2})/(\d{4})")

# Mapping des mots-clés vers les statuts normalisés
_STATUTS_MAP: dict[str, str] = {
    "en production": "En production",
    "en cours de livraison": "En cours de livraison",
    "en cours": "En cours",
    "annul": "Annulée",
    "livr": "Livrée",
    "pay": "Payée",
    "bloqu": "Bloquée",
}

# Mapping normalisation Lot/Vrac (False = booléen Excel pour "aucun lot")
_LOT_MAP: dict = {
    "Lot": "Lot",
    "Vrac": "Vrac",
    False: "Unitaire",
    "False": "Unitaire",
}


def parse_statut_commande(texte: str) -> tuple[str, Optional[str]]:
    """
    Parse le champ libre 'Etat de la commande' vers un statut normalisé + date ISO.

    Exemples :
        'Livrée le 18/09/2025' → ('Livrée', '2025-09-18')
        'En production'        → ('En production', None)
        'Annulée'              → ('Annulée', None)

    Args:
        texte: Valeur brute du champ Excel.
    Returns:
        Tuple (statut_enum, date_iso_ou_none).
    """
    if not isinstance(texte, str):
        return ("Inconnu", None)

    texte_lower = texte.lower().strip()
    statut = "Inconnu"
    for cle, valeur in _STATUTS_MAP.items():
        if cle in texte_lower:
            statut = valeur
            break

    match = _DATE_PATTERN.search(texte)
    date_iso = (
        f"{match.group(3)}-{match.group(2)}-{match.group(1)}" if match else None
    )
    return (statut, date_iso)


def _to_date_or_none(val: object) -> Optional[str]:
    """Convertit une valeur Excel (datetime ou NaT) en date ISO, sinon None."""
    try:
        ts = pd.Timestamp(val)  # type: ignore[arg-type]
        if pd.isna(ts):
            return None
        return ts.date().isoformat()
    except Exception:
        return None


def _to_numeric_or_none(val: object) -> Optional[float]:
    """Convertit en float, retourne None si non numérique."""
    try:
        result = float(val)  # type: ignore[arg-type]
        return None if pd.isna(result) else result
    except (TypeError, ValueError):
        return None


def transform_produit(
    df_matrice: pd.DataFrame, df_dimensions: pd.DataFrame
) -> pd.DataFrame:
    """
    Construit la table produit en fusionnant Matrice + Dimensions.

    Opérations :
    - Dédoublonnage sur Référence (garder première occurrence)
    - Normalisation type_lot
    - Fusion avec dimensions logistiques (LEFT JOIN sur Référence)
    - Sélection et renommage des colonnes cibles

    Args:
        df_matrice: Résultat de extract_matrice()
        df_dimensions: Résultat de extract_dimensions()
    Returns:
        DataFrame prêt pour load_produit().
    """
    logger.info("Transformation produit...")

    # Dédoublonner sur Référence
    df = df_matrice.drop_duplicates(subset=["Référence"], keep="first").copy()

    # Normaliser Lot/Vrac
    df["type_lot"] = df["Lot/Vrac"].map(_LOT_MAP).fillna("Unitaire")

    # Fusionner avec dimensions logistiques
    df_dim = df_dimensions.rename(columns={"Référence": "ref_dim"}).copy()
    df_dim["ref_dim"] = df_dim["ref_dim"].astype(str)
    df["Référence"] = df["Référence"].astype(str)

    df = df.merge(
        df_dim[["ref_dim", "Longueur PCB (cm)", "Largeur PCB (cm)",
                "Hauteur PCB (cm)", "Poids PCB (kg)", "Volume (m3)",
                "PCB", "SPCB", "EAN 13", "EAN 14 PCB", "EAN 14 SPCB"]],
        left_on="Référence",
        right_on="ref_dim",
        how="left",
    )

    # Construire le DataFrame cible
    result = pd.DataFrame({
        "code_article":    df["Référence"],
        "ean13":           df.get("EAN 13_y", df.get("EAN 13")),
        "ean14_pcb":       df.get("EAN 14 PCB_y", df.get("EAN 14 PCB")),
        "ean14_spcb":      df.get("EAN 14 SPCB_y", df.get("EAN 14 SPCB")),
        "designation_fr":  df.get("Description FR"),
        "designation_en":  df.get("Description ENG"),
        "fournisseur":     df.get("Fournisseur"),
        "gamme":           df.get("Gamme"),
        "type_lot":        df["type_lot"],
        "nomenclature":    df.get("Nomenclature"),
        "matiere_lame":    df.get("Matière lame/\nhaut de couvert"),
        "matiere_manche":  df.get("Matière manche/\nproduit"),
        "finition":        df.get("Finition"),
        "poids_uvc_g":     df.get("Poids \n(g)"),
        "longueur_mm":     df.get("Longueur \n(mm)"),
        "epaisseur_mm":    df.get("Epaisseur\n(mm)"),
        "pcb":             df.get("PCB_y", df.get("PCB")),
        "spcb":            df.get("SPCB_y", df.get("SPCB")),
        "longueur_pcb_cm": df.get("Longueur PCB (cm)"),
        "largeur_pcb_cm":  df.get("Largeur PCB (cm)"),
        "hauteur_pcb_cm":  df.get("Hauteur PCB (cm)"),
        "poids_pcb_kg":    df.get("Poids PCB (kg)"),
        "volume_m3":       df.get("Volume (m3)"),
        "date_creation":   df.get("Date céation", df.get("Date de création")),
    })

    # Forcer les types numériques (certaines cellules Excel contiennent du texte ex: "2CR14")
    numeric_cols = [
        "poids_uvc_g", "longueur_mm", "epaisseur_mm",
        "longueur_pcb_cm", "largeur_pcb_cm", "hauteur_pcb_cm",
        "poids_pcb_kg", "volume_m3", "pcb", "spcb",
    ]
    for col in numeric_cols:
        result[col] = pd.to_numeric(result[col], errors="coerce")

    result["date_creation"] = pd.to_datetime(
        result["date_creation"], errors="coerce"
    ).dt.date

    logger.info("Produits transformés : %d articles", len(result))
    return result


def transform_commande(df_import: pd.DataFrame) -> pd.DataFrame:
    """
    Nettoie et normalise le DataFrame IMPORT 2026 vers la table commande.

    Opérations clés :
    - Parse 'Etat de la commande' → statut + date_statut
    - Nettoyage des noms de colonnes (espaces, newlines)
    - Conversion des types (dates, numériques)

    Args:
        df_import: Résultat de extract_import()
    Returns:
        DataFrame prêt pour load_commande().
    """
    logger.info("Transformation commande...")
    df = df_import.copy()

    # Normaliser les noms de colonnes (supprimer espaces trailing et newlines)
    df.columns = [str(c).strip().replace("\n", " ") for c in df.columns]

    # Parser le statut
    statuts = df["Etat de la commande"].apply(parse_statut_commande)
    df["statut"] = statuts.apply(lambda x: x[0])
    df["date_statut"] = statuts.apply(lambda x: x[1])

    # Colonnes date — 'Payé ?' peut contenir une date ou un booléen
    def safe_date(col: str) -> pd.Series:
        return df[col].apply(_to_date_or_none) if col in df.columns else pd.Series(None, index=df.index)

    result = pd.DataFrame({
        "po_number":       df["PO#"].astype(str),
        "men_number":      df["MEN#"].astype(str),
        "n_lot":           df.get("N° Lot"),
        "intermediaire":   df.get("Intermédiaire"),
        "fournisseur":     df.get("Fournisseur"),
        "code_article":    df.get("REF"),
        "designation":     df.get("Désignation"),
        "quantite":        pd.to_numeric(df.get("Quantité"), errors="coerce"),
        "prix_unitaire":   pd.to_numeric(df.get("PU"), errors="coerce"),
        "total_prix":      pd.to_numeric(df.get("Total prix commande"), errors="coerce"),
        "frais_supp":      pd.to_numeric(df.get("Frais supp"), errors="coerce"),
        "volume_m3_cmd":   pd.to_numeric(df.get("Volume m3 commande"), errors="coerce"),
        "statut":          df["statut"],
        "date_statut":     df["date_statut"],
        "date_commande":   safe_date("Date envoi de la commande"),
        "date_paiement":   safe_date("Payé ?"),
        "etd_confirme":    safe_date("ETD confirmé"),
        "etd_reel":        safe_date("ETD réel"),
        "eta":             safe_date("ETA"),
        "date_livraison":  safe_date("Date de livraison"),
        "lieu_livraison":  df.get("Lieu de livraison"),
        "n_bl":            df.get("N° BL"),
        "n_conteneur":     df.get("N° Conteneur"),
        "n_facture":       df.get("N° Facture"),
        "transitaire":     df.get("Transport"),
        "non_conformite":  df.get("Non-conformité (NCR)"),
        "retard_jours":    pd.to_numeric(df.get("Retard  (jours)"), errors="coerce"),
        "colis_manquants": df.get("Colis/pièces manquantes"),
    })

    # Convertir code_article en str propre
    result["code_article"] = result["code_article"].apply(
        lambda x: str(int(x)) if pd.notna(x) and str(x).replace(".0", "").isdigit() else str(x) if pd.notna(x) else None
    )

    # Forcer les colonnes DATE en datetime.date (pas en str ISO)
    date_cols = [
        "date_statut", "date_commande", "date_paiement",
        "etd_confirme", "etd_reel", "eta", "date_livraison",
    ]
    for col in date_cols:
        result[col] = pd.to_datetime(result[col], errors="coerce").dt.date

    logger.info("Commandes transformées : %d lignes", len(result))
    return result
