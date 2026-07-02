# -*- coding: utf-8 -*-
"""
[UTIL]
=============================================================================
AUTHENTIFICATION GOOGLE PARTAGEE (Gmail + Drive)
=============================================================================
Un seul client OAuth "Application de bureau" (Google Cloud Console, ecran de
consentement Internal TB Groupe -- meme projet que le Plan A Gmail, cf.
docs/20260622_FUSEAU_RunbookOAuthGmail_v1.md) peut porter plusieurs scopes.

Ce module centralise la liste des scopes et le flow OAuth pour que
fetch_attachments.py (Gmail) et crawl_drive_qualite.py (Drive) partagent le
MEME token.json -- un seul consentement utilisateur (Marlene) au lieu de deux.

Junior Tip : si tu ajoutes un scope apres qu'un token.json existe deja, Google
renverra une erreur "insufficient scope" a la premiere requete concernee, pas
au chargement du credential. Toujours supprimer config/token.json et relancer
un script pour redeclencher un consentement complet quand SCOPES change.

Prerequis (fait une fois, projet GCP existant du Plan A Gmail) :
  1. Console Google Cloud > APIs & Services > Library > activer "Google Drive API"
     (le projet et le client OAuth desktop existent deja pour Gmail -- reutiliser).
  2. Supprimer config/token.json si un token Gmail-only existe deja.
  3. Relancer un script (Gmail ou Drive) : le navigateur s'ouvre, consentement
     sur les 2 scopes (gmail.readonly + drive.readonly), token.json regenere.
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Perimetre le plus restreint possible : lecture seule sur les deux APIs.
# On ne demande jamais l'ecriture -- ni sur Gmail ni sur Drive.
SCOPES: list[str] = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]


def get_credentials(credentials_path: Path, token_path: Path):
    """
    Charge ou obtient des credentials Google valides pour SCOPES (Gmail + Drive).

    Args:
        credentials_path: Chemin vers credentials.json (client OAuth desktop).
        token_path: Chemin vers token.json (cache du refresh token).
    Returns:
        google.oauth2.credentials.Credentials valide.
    Raises:
        FileNotFoundError: Si credentials.json est absent.
    """
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds: Credentials | None = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info("[INFO] Token expiré -- rafraîchissement silencieux")
            creds.refresh(Request())
        else:
            if not credentials_path.exists():
                raise FileNotFoundError(
                    f"credentials.json introuvable : {credentials_path}. "
                    "Voir les prérequis OAuth en tête de module."
                )
            logger.info("[INFO] Consentement OAuth requis (gmail.readonly + drive.readonly)")
            flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
            creds = flow.run_local_server(port=0)
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json(), encoding="utf-8")
        logger.info("[SUCCÈS] Token mis en cache : %s", token_path)

    return creds
