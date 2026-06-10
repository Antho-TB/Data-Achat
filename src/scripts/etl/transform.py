# -*- coding: utf-8 -*-
"""
[DATA ENGINEERING]
Transformations métier du pipeline ETL Data-Achat TB Groupe.

Stratégie : ce module est le coeur du pipeline -- il normalise les données
brutes issues des fichiers Excel vers un format cohérent et typé, prêt pour
l'insertion PostgreSQL. Les deux fonctions principales (transform_produit,
transform_commande) constituent la couche "T" du pattern ETL et ne doivent
jamais effectuer d'I/O (lecture fichier ou écriture DB).
"""
import logging
import re
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Regex pour extraire une date au format JJ/MM/AAAA depuis un champ texte libre
# Utilisé pour parser "Livrée le 18/09/2025" et en extraire la date
_DATE_PATTERN = re.compile(r"(\d{2})/(\d{2})/(\d{4})")

# Mapping des mots-clés vers les statuts normalisés
# Clés en minuscules car on applique .lower() avant la recherche
_STATUTS_MAP: dict[str, str] = {
    "en production": "En production",
    "en cours de livraison": "En cours de livraison",
    "en cours": "En cours",
    "annul": "Annulée",
    "livr": "Livrée",
    "pay": "Payée",
    "bloqu": "Bloquée",
}

# Mapping normalisation Lot/Vrac
# False (booléen) provient d'Excel qui interprète une cellule vide comme False
# dans certaines versions d'openpyxl -- on le traite comme "Unitaire"
_LOT_MAP: dict = {
    "Lot": "Lot",
    "Vrac": "Vrac",
    False: "Unitaire",
    "False": "Unitaire",
}


def parse_statut_commande(texte: str) -> tuple[str, Optional[str]]:
    """
    Parse le champ libre 'Etat de la commande' vers un statut normalisé + date ISO.

    Ce champ est rempli manuellement par les acheteurs avec des formulations
    variables. La stratégie est une recherche par sous-chaîne (et non regex
    exacte) pour absorber les variations orthographiques courantes.

    Junior Tip : On utilise .lower() avant la comparaison pour ignorer la casse,
    et des mots-clés tronqués (ex: "livr" capture "Livrée", "livré", "livraison")
    pour couvrir les variantes sans multiplier les entrées du dictionnaire.

    Exemples :
        'Livrée le 18/09/2025' -> ('Livrée', '2025-09-18')
        'En production'        -> ('En production', None)
        'Annulée'              -> ('Annulée', None)

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
    """
    Convertit une valeur Excel (datetime, NaT, str) en date ISO, sinon None.

    Junior Tip : pandas lit les colonnes date Excel comme des objets datetime64
    ou NaT (Not a Time). pd.Timestamp() unifie tous ces formats, et pd.isna()
    détecte les valeurs manquantes (NaN, NaT, None) de façon robuste.

    Args:
        val: Valeur brute issue d'un DataFrame pandas (any type).
    Returns:
        Date au format 'YYYY-MM-DD' ou None si non convertible.
    """
    try:
        ts = pd.Timestamp(val)  # type: ignore[arg-type]
        if pd.isna(ts):
            return None
        return ts.date().isoformat()
    except Exception as exc:  # noqa: BLE001
        logger.warning("[ATTENTION] _to_date_or_none: valeur non convertible %r -- %s", val, exc)
        return None


def _clean_ref(val: object) -> Optional[str]:
    """
    Nettoie une référence (PO#, MEN#, code article) lue depuis Excel.

    Excel stocke les identifiants numériques en float : "150073" devient 150073.0.
    Sans nettoyage, astype(str) produit "150073.0" en base, ce qui casse les
    jointures et crée de faux doublons (bug constaté en base le 2026-06-10).

    Junior Tip : on teste float(val).is_integer() plutôt qu'un replace(".0")
    naïf, car "150073.05" contient aussi ".0" et serait corrompu par replace.

    Args:
        val: Valeur brute Excel (float, int, str ou NaN).
    Returns:
        Référence nettoyée en str, ou None si vide/invalide.
    """
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    s = str(val).strip()
    if not s or s in ("/", "-", "nan", "None", "NaT"):
        return None
    try:
        f = float(s)
        if pd.isna(f):
            return None
        if f.is_integer():
            return str(int(f))
    except ValueError:
        pass
    return s


def _to_numeric_or_none(val: object) -> Optional[float]:
    """
    Convertit en float, retourne None si non numérique ou NaN.

    Args:
        val: Valeur brute (peut être str, float, int ou None).
    Returns:
        float si convertible, None sinon.
    """
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

    La Matrice contient la fiche produit complète (désignation, fournisseur,
    gamme, matières...) et les Dimensions apportent les données logistiques
    (poids, volume, EAN). La jointure se fait sur Référence article.

    Junior Tip : pd.merge() avec how='left' garantit qu'un produit présent
    dans la Matrice mais absent de la base Dimensions sera quand même inclus
    dans le résultat (avec des NaN pour les colonnes logistiques manquantes),
    ce qui est préférable à un INNER JOIN qui l'exclurait silencieusement.

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
    logger.info("[INFO] Transformation produit...")

    # Dédoublonner sur Référence : la Matrice peut contenir plusieurs lignes
    # pour un même article (variantes couleur/taille) -- on garde la première
    # qui contient la fiche produit principale
    df = df_matrice.drop_duplicates(subset=["Référence"], keep="first").copy()

    # Normaliser Lot/Vrac via le dictionnaire de mapping défini en tête de module
    df["type_lot"] = df["Lot/Vrac"].map(_LOT_MAP).fillna("Unitaire")

    # Fusionner avec dimensions logistiques -- renommage préventif pour éviter
    # une collision de colonnes "Référence" après le merge (pandas suffixerait _x/_y)
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

    # Construire le DataFrame cible avec les noms de colonnes PostgreSQL
    # (snake_case, sans accents) -- mapping explicite Matrice -> achat.produit
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

    # Forcer les types numériques -- certaines cellules Excel contiennent du texte
    # (ex: référence acier "2CR14") que pandas lit comme str au lieu de float ;
    # errors='coerce' transforme ces valeurs non convertibles en NaN proprement
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

    logger.info("[SUCCÈS] Produits transformés : %d articles", len(result))
    return result


def transform_commande(df_import: pd.DataFrame) -> pd.DataFrame:
    """
    Nettoie et normalise le DataFrame IMPORT 2026 vers la table commande.

    Le fichier IMPORT est la source de vérité pour le suivi des commandes
    fournisseurs import Chine (Circuit A2). Ce pipeline normalise les champs
    libres (statut, dates) et uniformise les types pour garantir la cohérence
    dans PostgreSQL.

    Junior Tip : Les colonnes d'un DataFrame chargé depuis Excel peuvent
    contenir des espaces ou des retours à la ligne (\n) dans leur nom si le
    header Excel était multi-ligne. Le strip().replace() ci-dessous assainit
    ces noms avant toute opération sur les colonnes.

    Opérations clés :
    - Parse 'Etat de la commande' -> statut + date_statut
    - Nettoyage des noms de colonnes (espaces, newlines)
    - Conversion des types (dates, numériques)

    Args:
        df_import: Résultat de extract_import()
    Returns:
        DataFrame prêt pour load_commande().
    """
    logger.info("[INFO] Transformation commande...")
    df = df_import.copy()

    # Normaliser les noms de colonnes -- supprimer les espaces en fin de chaîne
    # et les retours à la ligne présents dans les en-têtes Excel multi-lignes
    df.columns = [str(c).strip().replace("\n", " ") for c in df.columns]

    # Parser le statut depuis le champ libre -- deux valeurs extraites en une passe
    statuts = df["Etat de la commande"].apply(parse_statut_commande)
    df["statut"] = statuts.apply(lambda x: x[0])
    df["date_statut"] = statuts.apply(lambda x: x[1])

    # Colonnes date -- 'Payé ?' peut contenir une date ISO ou un booléen Excel
    # selon que la commande est payée avec ou sans date confirmée
    def safe_date(col: str) -> pd.Series:
        return df[col].apply(_to_date_or_none) if col in df.columns else pd.Series(None, index=df.index)

    result = pd.DataFrame({
        "po_number":       df["PO#"].apply(_clean_ref),
        "men_number":      df["MEN#"].apply(_clean_ref),
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

    # Convertir code_article en str propre -- même nettoyage que PO#/MEN#
    # (float Excel 12345.0 -> "12345", valeurs poubelle "/" -> None)
    result["code_article"] = result["code_article"].apply(_clean_ref)

    # Écarter les lignes sans clé métier exploitable (PO# ou article manquant) --
    # typiquement des lignes de sous-totaux ou de séparation dans le fichier Excel
    avant = len(result)
    result = result.dropna(subset=["po_number", "code_article"])
    if avant - len(result):
        logger.warning("[ATTENTION] %d lignes écartées (PO# ou code article manquant)", avant - len(result))

    # Dédoublonner sur la clé métier (po_number, code_article) -- décision plan
    # d'action 2026-06 : on garde la dernière occurrence (la plus récente dans
    # le fichier). Prérequis de la contrainte UNIQUE uq_commande_po_article.
    avant = len(result)
    result = result.drop_duplicates(subset=["po_number", "code_article"], keep="last")
    if avant - len(result):
        logger.warning("[ATTENTION] %d doublons (po_number, code_article) dédoublonnés", avant - len(result))

    # Forcer les colonnes DATE en datetime.date (pas en str ISO) pour que
    # psycopg2 les insère comme type DATE PostgreSQL sans conversion manuelle
    date_cols = [
        "date_statut", "date_commande", "date_paiement",
        "etd_confirme", "etd_reel", "eta", "date_livraison",
    ]
    for col in date_cols:
        result[col] = pd.to_datetime(result[col], errors="coerce").dt.date

    logger.info("[SUCCÈS] Commandes transformées : %d lignes", len(result))
    return result
