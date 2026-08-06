# -*- coding: utf-8 -*-
"""
[UTIL]
=============================================================================
CONNECTEUR GOOGLE SHEETS API (Lecture Seule)
=============================================================================

Permet la lecture directe des Google Sheets natives (ex: Artworks LIS-CON-28-0,
Suivi des analyses qualite) via l'API Google Sheets v4 en reutilisant l'authentification
partagee OAuth (src/utils/google_auth.py).

Usage :
    from src.utils.gsheets import read_sheet_as_dicts
    rows = read_sheet_as_dicts("1w...spreadsheet_id...", "Onglet1!A1:Z100")
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from src.utils.config_manager import get_base_path
from src.utils.google_auth import get_credentials

logger = logging.getLogger(__name__)


def get_sheets_service(
    credentials_path: Optional[Path] = None,
    token_path: Optional[Path] = None,
):
    """
    Initialise le client API Google Sheets v4.

    Ce module referencait Config.BASE_DIR, attribut qui n'existe pas : l'appel
    levait un AttributeError, avale par le except de read_sheet_values, qui
    renvoyait donc toujours une liste vide. Le connecteur n'avait jamais pu
    fonctionner. On passe par get_base_path(), la fonction reellement exposee.
    """
    from googleapiclient.discovery import build

    racine = get_base_path()
    c_path = credentials_path or (racine / "config" / "credentials.json")
    t_path = token_path or (racine / "config" / "token.json")

    creds = get_credentials(c_path, t_path)
    return build("sheets", "v4", credentials=creds)


def read_sheet_values(
    spreadsheet_id: str,
    range_name: str,
    credentials_path: Optional[Path] = None,
    token_path: Optional[Path] = None,
) -> list[list[Any]]:
    """Lit une plage de cellules brute et renvoie une grille 2D."""
    try:
        service = get_sheets_service(credentials_path, token_path)
        sheet = service.spreadsheets()
        result = sheet.values().get(spreadsheetId=spreadsheet_id, range=range_name).execute()
        return result.get("values", [])
    except Exception as e:
        # Une liste vide est indiscernable d'un onglet reellement vide : le log
        # en ATTENTION est le seul moyen de voir passer une panne d'auth Google.
        logger.warning("[ATTENTION] Lecture du gsheet %s (%s) impossible : %s",
                       spreadsheet_id, range_name, e)
        return []


def grid_to_dicts(values: list[list[Any]]) -> list[dict[str, Any]]:
    """Convertit une grille 2D (ligne 0 = en-tetes) en liste de dictionnaires."""
    if not values or len(values) < 2:
        return []
    headers = [str(h).strip() for h in values[0]]
    result: list[dict[str, Any]] = []
    for row in values[1:]:
        d: dict[str, Any] = {}
        for idx, h in enumerate(headers):
            if idx < len(row):
                d[h] = row[idx]
            else:
                d[h] = None
        result.append(d)
    return result


def list_tabs(
    spreadsheet_id: str,
    credentials_path: Optional[Path] = None,
    token_path: Optional[Path] = None,
) -> list[str]:
    """
    Liste les noms d'onglets d'un classeur Google Sheets.

    Args:
        spreadsheet_id: identifiant du classeur (portion de l'URL).
    Returns:
        Noms des onglets, dans l'ordre du classeur.
    """
    service = get_sheets_service(credentials_path, token_path)
    meta = service.spreadsheets().get(
        spreadsheetId=spreadsheet_id, fields="sheets.properties.title").execute()
    return [s["properties"]["title"] for s in meta.get("sheets", [])]


def read_all_tabs(
    spreadsheet_id: str,
    credentials_path: Optional[Path] = None,
    token_path: Optional[Path] = None,
) -> list[tuple[str, list[list[Any]]]]:
    """
    Lit tous les onglets d'un classeur et renvoie leur grille brute.

    Sert a remplacer un export XLSX manuel par une lecture directe : le suivi
    des artworks de Clarisse est un classeur a plusieurs onglets, et le
    transformateur a besoin de savoir de quel onglet vient chaque ligne.

    Junior Tip : contrairement au reste du module, cette fonction LEVE en cas
    d'echec au lieu de renvoyer une liste vide. Elle est destinee a une tache
    planifiee : un classeur vide et une panne d'authentification doivent se
    distinguer, sinon la tache se termine en succes en ayant tout efface.

    Args:
        spreadsheet_id: identifiant du classeur.
    Returns:
        Liste de couples (nom d'onglet, grille de cellules).
    Raises:
        RuntimeError: si le classeur est inaccessible ou ne contient aucun onglet.
    """
    try:
        onglets = list_tabs(spreadsheet_id, credentials_path, token_path)
    except Exception as e:
        raise RuntimeError(
            f"Classeur {spreadsheet_id} inaccessible : {e}. "
            "Verifier le partage du fichier et le scope spreadsheets.readonly "
            "du token (supprimer config/token.json pour reconsentir)."
        ) from e

    if not onglets:
        raise RuntimeError(f"Classeur {spreadsheet_id} sans onglet exploitable.")

    service = get_sheets_service(credentials_path, token_path)
    resultat: list[tuple[str, list[list[Any]]]] = []
    for onglet in onglets:
        valeurs = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id, range=onglet).execute().get("values", [])
        logger.info("[INFO] Onglet '%s' : %d ligne(s).", onglet, len(valeurs))
        resultat.append((onglet, valeurs))
    return resultat


def read_sheet_as_dicts(
    spreadsheet_id: str,
    range_name: str,
    credentials_path: Optional[Path] = None,
    token_path: Optional[Path] = None,
) -> list[dict[str, Any]]:
    """Lit un onglet Google Sheet et renvoie directement la liste de dicts (header en 1re ligne)."""
    values = read_sheet_values(spreadsheet_id, range_name, credentials_path, token_path)
    return grid_to_dicts(values)


# ===========================================================================
# CLASSEURS OFFICE STOCKES DANS DRIVE
# ===========================================================================
# L'API Sheets ne sait lire QUE des Google Sheets natifs. Sur un fichier Office
# elle refuse net : "This operation is not supported for this document. The
# document must not be an Office file."
#
# Or le suivi maritime du transitaire est un .xlsx depose dans Drive
# (SUIVI MARITIME TARRERIAS 2026.xlsx, proprietaire lbonnet@qualitairsea.com),
# pas un Google Sheet. Constate le 06/08/2026 : ce n'etait ni un probleme de
# scope ni un probleme de partage, les deux avaient ete regles le matin meme.
# C'etait la mauvaise API.
#
# Convertir le fichier en Google Sheet est ecarte volontairement : il appartient
# au transitaire, qui l'alimente quotidiennement. La conversion creerait un
# doublon fige, et FUSEAU lirait une copie morte pendant que QUALITAIR
# continuerait de mettre a jour l'original.

MIME_GOOGLE_SHEET = "application/vnd.google-apps.spreadsheet"


def _service_drive(
    credentials_path: Optional[Path] = None,
    token_path: Optional[Path] = None,
):
    """Client Drive v3, meme authentification partagee que le client Sheets."""
    from googleapiclient.discovery import build

    racine = get_base_path()
    creds = get_credentials(
        credentials_path or (racine / "config" / "credentials.json"),
        token_path or (racine / "config" / "token.json"))
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def metadonnees_drive(
    file_id: str,
    credentials_path: Optional[Path] = None,
    token_path: Optional[Path] = None,
) -> dict[str, Any]:
    """
    Nom, type MIME et date de modification d'un objet Drive.

    modifiedTime est la date a laquelle le TRANSITAIRE a modifie le classeur.
    C'est une meilleure date de transmission que le mtime d'une copie locale, qui
    ne dit que la date du telechargement.

    Raises:
        RuntimeError: si l'objet est inaccessible (partage revoque, scope absent).
    """
    try:
        return _service_drive(credentials_path, token_path).files().get(
            fileId=file_id, fields="name, mimeType, modifiedTime, size").execute()
    except Exception as e:
        raise RuntimeError(
            f"Objet Drive {file_id} inaccessible : {e}. Verifier le partage du "
            "fichier et le scope drive.readonly du token (supprimer "
            "config/token.json pour reconsentir)."
        ) from e


def lire_xlsx_drive(
    file_id: str,
    credentials_path: Optional[Path] = None,
    token_path: Optional[Path] = None,
) -> list[tuple[str, list[list[Any]]]]:
    """
    Telecharge un classeur Office depuis Drive et rend ses onglets en grilles.

    Junior Tip : les cellules sont lues en dtype=str puis les vides remplacees
    par une chaine vide, exactement comme _read_rows du transformateur maritime le
    fait sur le fichier serveur. Ce n'est pas un detail de style : les dates
    Excel, selon la facon dont on les lit, ressortent en texte, en horodatage ou
    en numero de serie. Aligner les deux chemins de lecture garantit que le
    parseur de dates voit la meme chose, quelle que soit la source.

    Args:
        file_id: identifiant Drive du fichier.
    Returns:
        Liste de couples (nom d'onglet, grille de cellules), meme forme que
        read_all_tabs, pour que les appelants ne voient pas la difference.
    Raises:
        RuntimeError: si le telechargement ou le parsing echoue. On leve au lieu
            de renvoyer une liste vide : cette fonction sert une tache planifiee,
            et un classeur vide doit se distinguer d'une panne d'acces.
    """
    import io

    import pandas as pd
    from googleapiclient.http import MediaIoBaseDownload

    try:
        drive = _service_drive(credentials_path, token_path)
        tampon = io.BytesIO()
        telechargement = MediaIoBaseDownload(
            tampon, drive.files().get_media(fileId=file_id))
        termine = False
        while not termine:
            _, termine = telechargement.next_chunk()
        tampon.seek(0)
    except Exception as e:
        raise RuntimeError(
            f"Telechargement du classeur Drive {file_id} impossible : {e}") from e

    try:
        classeur = pd.ExcelFile(tampon)
        resultat: list[tuple[str, list[list[Any]]]] = []
        for nom in classeur.sheet_names:
            df = classeur.parse(nom, header=None, dtype=str)
            grille = df.fillna("").astype(str).values.tolist()
            logger.info("[INFO] Onglet '%s' : %d ligne(s).", nom, len(grille))
            resultat.append((nom, grille))
        return resultat
    except Exception as e:
        raise RuntimeError(
            f"Classeur Drive {file_id} telecharge mais illisible : {e}") from e


def lire_classeur(
    file_id: str,
    credentials_path: Optional[Path] = None,
    token_path: Optional[Path] = None,
) -> list[tuple[str, list[list[Any]]]]:
    """
    Lit un classeur Drive, qu'il soit un Google Sheet natif ou un fichier Office.

    Le type est determine par une lecture des metadonnees Drive, et non en
    rattrapant le message d'erreur de l'API Sheets. Un test sur le libelle
    "Office file" fonctionnerait aujourd'hui et casserait le jour ou Google
    reformule sa phrase, sans que rien ne le signale.

    Args:
        file_id: identifiant du classeur.
    Returns:
        Liste de couples (nom d'onglet, grille de cellules).
    Raises:
        RuntimeError: classeur inaccessible ou illisible.
    """
    meta = metadonnees_drive(file_id, credentials_path, token_path)
    mime = meta.get("mimeType", "")
    if mime == MIME_GOOGLE_SHEET:
        logger.info("[INFO] '%s' est un Google Sheet natif, lecture via l'API Sheets.",
                    meta.get("name", file_id))
        return read_all_tabs(file_id, credentials_path, token_path)

    logger.info("[INFO] '%s' est un fichier Office (%s), lecture via Drive. "
                "Derniere modification par le proprietaire : %s.",
                meta.get("name", file_id), mime, meta.get("modifiedTime", "inconnue"))
    return lire_xlsx_drive(file_id, credentials_path, token_path)
