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

from src.utils.config_manager import Config
from src.utils.google_auth import get_credentials

logger = logging.getLogger("gsheets")


def get_sheets_service(
    credentials_path: Optional[Path] = None,
    token_path: Optional[Path] = None,
):
    """Initialise le client API Google Sheets v4."""
    from googleapiclient.discovery import build

    c_path = credentials_path or (Config.BASE_DIR / "config" / "credentials.json")
    t_path = token_path or (Config.BASE_DIR / "config" / "token.json")

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
        logger.warning("[GSHEETS] Erreur lors de la lecture du gsheet %s (%s) : %s", spreadsheet_id, range_name, e)
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


def read_sheet_as_dicts(
    spreadsheet_id: str,
    range_name: str,
    credentials_path: Optional[Path] = None,
    token_path: Optional[Path] = None,
) -> list[dict[str, Any]]:
    """Lit un onglet Google Sheet et renvoie directement la liste de dicts (header en 1re ligne)."""
    values = read_sheet_values(spreadsheet_id, range_name, credentials_path, token_path)
    return grid_to_dicts(values)
