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
