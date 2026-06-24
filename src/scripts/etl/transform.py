# -*- coding: utf-8 -*-
"""
=============================================================================
ETL ACHATS - TRANSFORMATION (nettoyage & normalisation)
=============================================================================

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


def transform_artwork(df_import: pd.DataFrame) -> pd.DataFrame:
    """
    Suivi artwork depuis IMPORT 2026, colonne N 'Artwork' (source de verite
    confirmee par Antho le 2026-06-10 -- la colonne Artwork de la Matrice est
    quasi vide et ne reflete pas le workflow reel).

    C'est un workflow d'ENVOI d'artwork au fournisseur, suivi par ligne de
    commande (po_number, code_article). Statuts natifs observes :
    Aucun / Envoyé / Attente Clarisse / A envoyer / Attente Carrefour.
    On conserve les libelles natifs ('A envoyé' normalise en 'A envoyer').

    La table cible est editee par le metier via l'ERP : chargement insert-only
    (voir load_artwork), jamais d'ecrasement des statuts saisis.

    Args:
        df_import: Resultat de extract_import() (IMPORT 2026.xlsx).
    Returns:
        DataFrame (po_number, code_article, designation, statut_artwork, date_demande).
    """
    logger.info("[INFO] Transformation artwork (IMPORT col N)...")
    df = df_import.copy()
    df.columns = [str(c).strip().replace("\n", " ") for c in df.columns]

    _NORMALISATION = {"a envoyé": "A envoyer", "a envoyer": "A envoyer"}

    def map_statut(val: object) -> str:
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return "Aucun"
        s = str(val).strip()
        return _NORMALISATION.get(s.lower(), s) if s else "Aucun"

    result = pd.DataFrame({
        "po_number":      df["PO#"].apply(_clean_ref),
        "code_article":   df.get("REF").apply(_clean_ref),
        "designation":    df.get("Désignation"),
        "statut_artwork": df.get("Artwork").apply(map_statut),
        "date_demande":   df.get("Date envoi de la commande").apply(_to_date_or_none),
    })
    result["date_demande"] = pd.to_datetime(result["date_demande"], errors="coerce").dt.date
    result = result.dropna(subset=["po_number", "code_article"])
    result = result.drop_duplicates(subset=["po_number", "code_article"], keep="last")

    logger.info("[SUCCÈS] Artwork transformés : %d lignes de commande", len(result))
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

    # Écarter uniquement les lignes sans PO# (sous-totaux, séparations Excel).
    # Règle Circuit B : le code article peut être ABSENT sur les lignes de frais
    # (molding fee, etc. -- valeur "/" dans le fichier) -> on les CONSERVE avec
    # code_article NULL, leurs montants font partie du coût des commandes.
    avant = len(result)
    result = result.dropna(subset=["po_number"])
    if avant - len(result):
        logger.warning("[ATTENTION] %d lignes écartées (PO# manquant)", avant - len(result))

    # Dédoublonner sur la clé métier (po_number, code_article) -- décision plan
    # d'action 2026-06 : on garde la dernière occurrence (la plus récente dans
    # le fichier). Prérequis de la contrainte UNIQUE uq_commande_po_article.
    # Les lignes de frais (code_article NULL) sont exclues du dédoublonnage :
    # drop_duplicates considérerait NaN == NaN et fusionnerait des frais distincts.
    avant = len(result)
    has_article = result["code_article"].notna()
    dedup = result[has_article].drop_duplicates(
        subset=["po_number", "code_article"], keep="last"
    )
    result = pd.concat([dedup, result[~has_article]], ignore_index=True)
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


def transform_ot_transport(
    df_commande: pd.DataFrame,
    df_maritime: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Construit la table achat.ot_transport (suivi maritime, grain par conteneur).

    Deux sources possibles (priorite au fichier transitaire) :
      - df_maritime fourni  -> source de verite (2026 SUIVI MARITIME, CONTENEUR PLEIN) ;
      - sinon (mode degrade) -> bootstrap depuis df_commande : on deduplique sur
        n_conteneur et on prend la derniere occurrence (valeurs ETD/ETA en cache).

    Junior Tip : tant que le dossier TRANSITAIRE n'est pas accessible, df_maritime
    est None et la table se peuple avec ce que l'IMPORT a deja mis en cache via ses
    VLOOKUP. Le jour ou l'extracteur transitaire fournit df_maritime, ce meme load
    (UPSERT par conteneur) rafraichit les lignes sans rien perdre.

    Args:
        df_commande: DataFrame issu de transform_commande() (colonnes maritimes incluses).
        df_maritime: DataFrame optionnel issu de extract_suivi_maritime().
    Returns:
        DataFrame pret pour load_ot_transport() (colonnes = DDL_OT_TRANSPORT).
    """
    logger.info("[INFO] Transformation ot_transport...")

    if df_maritime is not None and not df_maritime.empty:
        # Mode nominal : le fichier transitaire fait foi. Mapping a finaliser une
        # fois les en-tetes reels de CONTENEUR PLEIN connus (acces dossier requis).
        logger.info("[INFO] Source = fichier transitaire (%d lignes)", len(df_maritime))
        df = df_maritime.copy()
        df.columns = [str(c).strip().replace("\n", " ") for c in df.columns]
        result = pd.DataFrame({
            "n_conteneur":    df.get("N° Conteneur"),
            "etd_reel":       df.get("ETD réel"),
            "eta":            df.get("ETA"),
            "date_livraison": df.get("Date de livraison"),
            "transport":      df.get("Transport"),
            "transitaire":    df.get("Transitaire"),
            "n_bl":           df.get("N° BL"),
            "n_facture":      df.get("N° Facture"),
            "lieu_livraison": df.get("Lieu de livraison"),
        })
        result["source_fichier"] = "2026 SUIVI MARITIME.xlsx"
    else:
        # Mode degrade : bootstrap depuis les commandes (valeurs en cache).
        logger.warning("[ATTENTION] Fichier transitaire absent -- bootstrap depuis achat.commande")
        result = pd.DataFrame({
            "n_conteneur":    df_commande.get("n_conteneur"),
            "etd_reel":       df_commande.get("etd_reel"),
            "eta":            df_commande.get("eta"),
            "date_livraison": df_commande.get("date_livraison"),
            "transport":      df_commande.get("transitaire"),  # col AR "Transport" dans commande
            "transitaire":    pd.Series([None] * len(df_commande)),
            "n_bl":           df_commande.get("n_bl"),
            "n_facture":      df_commande.get("n_facture"),
            "lieu_livraison": df_commande.get("lieu_livraison"),
        })
        result["source_fichier"] = "bootstrap:achat.commande"

    # Ne garder que les lignes avec un N° Conteneur exploitable (PK obligatoire).
    result["n_conteneur"] = result["n_conteneur"].apply(_clean_ref)
    avant = len(result)
    result = result.dropna(subset=["n_conteneur"])
    result = result.drop_duplicates(subset=["n_conteneur"], keep="last")
    logger.info("[INFO] ot_transport : %d conteneur(s) retenus (sur %d lignes)", len(result), avant)

    # Forcer les colonnes date au bon type pour psycopg2.
    for col in ("etd_reel", "eta"):
        result[col] = pd.to_datetime(result[col], errors="coerce").dt.date
    result["date_livraison"] = pd.to_datetime(result["date_livraison"], errors="coerce")

    logger.info("[SUCCÈS] ot_transport transforme : %d conteneur(s)", len(result))
    return result


def _clean_checkpoint(value) -> str | None:
    """
    Normalise un statut de checkpoint qualite Excel (MAT/SP/BAT/Reception...).

    Junior Tip : dans l'IMPORT, une cellule vide, ' / ' ou 'Aucune' signifie "pas
    de checkpoint applicable" -- on les ramene a None pour ne pas polluer les
    agregats (un 'Aucune' ne doit pas compter comme un controle realise).

    Args:
        value: Valeur brute de la cellule Excel.
    Returns:
        Le statut nettoye, ou None si non applicable.
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value).strip()
    if s in ("", "/", "Aucune", "Aucun"):
        return None
    return s


def _parse_rapport_inspection(value) -> tuple[str | None, str | None]:
    """
    Eclate le champ 'Rapport d'inspection' en (resultat, reference).

    Format observe : 'OK 4945056.00-28' ou 'FAIL 4935210.00-20'. Le premier token
    porte le verdict (OK/FAIL), le reste est la reference du rapport DEKRA.

    Junior Tip : on isole le verdict pour pouvoir calculer un taux d'echec
    d'inspection par fournisseur, mesure cle de l'evaluation qualite.

    Args:
        value: Valeur brute de la cellule Excel.
    Returns:
        Tuple (resultat OK/FAIL/None, reference rapport ou None).
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None, None
    s = str(value).strip()
    if s in ("", "/", "Aucune", "Aucun"):
        return None, None
    upper = s.upper()
    if upper.startswith("OK"):
        return "OK", s[2:].strip() or None
    if upper.startswith("FAIL"):
        return "FAIL", s[4:].strip() or None
    return None, s


def transform_qualite(df_import: pd.DataFrame) -> pd.DataFrame:
    """
    Construit la table achat.qualite a partir des colonnes qualite de l'IMPORT.

    Agrege les donnees DEJA presentes dans le fichier (checkpoints MAT/SP/echantillon/
    BAT, date et rapport d'inspection, reception, NCR), au grain (po_number,
    code_article). C'est le socle de l'onglet Qualite : evaluation fournisseurs et
    suivi des analyses, sans ressaisie. Le futur Excel "Suivi des analyses" (alimente
    par mail) viendra l'enrichir, comme ot_transport avec SUIVI MARITIME.

    Args:
        df_import: Resultat de extract_import().
    Returns:
        DataFrame pret pour load_qualite().
    """
    logger.info("[INFO] Transformation qualite...")
    df = df_import.copy()
    df.columns = [str(c).strip().replace("\n", " ") for c in df.columns]

    rapport = df.get("Rapport d'inspection")
    if rapport is None:
        rapport = pd.Series([None] * len(df), index=df.index)
    parsed = rapport.apply(_parse_rapport_inspection)

    result = pd.DataFrame({
        "po_number":            df["PO#"].apply(_clean_ref),
        "code_article":         df.get("REF").apply(_clean_ref) if "REF" in df else None,
        "fournisseur":          df.get("Fournisseur"),
        "designation":          df.get("Désignation"),
        "matiere":              df.get("Matière (MAT)").apply(_clean_checkpoint) if "Matière (MAT)" in df else None,
        "semi_production":      df.get("Semi-production (SP)").apply(_clean_checkpoint) if "Semi-production (SP)" in df else None,
        "echantillon_conformite": df.get("Echantillon de conformité").apply(_clean_checkpoint) if "Echantillon de conformité" in df else None,
        "production_bat":       df.get("Production (BAT)").apply(_clean_checkpoint) if "Production (BAT)" in df else None,
        "date_inspection":      df.get("Date inspection").apply(_to_date_or_none) if "Date inspection" in df else None,
        "resultat_inspection":  parsed.apply(lambda x: x[0]),
        "ref_rapport":          parsed.apply(lambda x: x[1]),
        "reception":            df.get("Réception (RECEP)").apply(_clean_checkpoint) if "Réception (RECEP)" in df else None,
        "ncr":                  df.get("Non-conformité (NCR)").apply(_clean_checkpoint) if "Non-conformité (NCR)" in df else None,
    })

    # La qualite est un fait PRODUIT : on ne garde que les lignes avec un code article
    # (les lignes de frais, code_article NULL, n'ont pas de checkpoint qualite).
    result = result[result["code_article"].notna()]
    result = result.drop_duplicates(subset=["po_number", "code_article"], keep="last")

    result["date_inspection"] = pd.to_datetime(result["date_inspection"], errors="coerce").dt.date
    logger.info("[SUCCÈS] Qualite transforme : %d lignes produit", len(result))
    return result


def transform_acompte(df_import: pd.DataFrame) -> pd.DataFrame:
    """
    Extrait l'acompte verse par commande depuis IMPORT 2026 (colonne 'Acompte', col I).

    Source officielle (confirmee metier 25/06) : Marlene saisit les virements d'acompte
    dans l'IMPORT ; Sylob ne porte pas le montant. La colonne est majoritairement un
    MONTANT (USD) ; quelques cellules contiennent un TAUX (valeur <= 1, ex. 0.3 = 30%).

    Junior Tip : on distingue montant vs taux par la magnitude (<= 1 => taux). On
    deduplique par PO (l'acompte est un fait commande, pas ligne-article) en gardant
    le montant le plus eleve rencontre.

    Args:
        df_import: Resultat de extract_import().
    Returns:
        DataFrame [po_number, montant_acompte, pourcentage_acompte] pret pour load_acompte().
    """
    logger.info("[INFO] Transformation acompte (IMPORT col Acompte)...")
    df = df_import.copy()
    df.columns = [str(c).strip().replace("\n", " ") for c in df.columns]
    if "Acompte" not in df.columns:
        logger.warning("[ATTENTION] Colonne 'Acompte' absente -- acompte vide.")
        return pd.DataFrame(columns=["po_number", "montant_acompte", "pourcentage_acompte"])

    val = pd.to_numeric(df["Acompte"], errors="coerce")
    out = pd.DataFrame({
        "po_number": df["PO#"].apply(_clean_ref),
        "montant_acompte": val.where(val > 1),                 # > 1 => montant
        "pourcentage_acompte": (val.where((val > 0) & (val <= 1)) * 100),  # <= 1 => taux %
    })
    out = out[out["po_number"].notna()]
    # Un acompte par PO : on garde la ligne au montant le plus parlant.
    out = (out.sort_values("montant_acompte", ascending=False, na_position="last")
              .drop_duplicates(subset=["po_number"], keep="first"))
    logger.info("[SUCCÈS] Acompte transforme : %d PO (dont %d avec montant)",
                len(out), int(out["montant_acompte"].notna().sum()))
    return out
