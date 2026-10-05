# -*- coding: utf-8 -*-
"""
[UTIL]
=============================================================================
AUTHENTIFICATION GOOGLE PARTAGEE (Gmail + Drive + Sheets)
=============================================================================
Un seul client OAuth "Application de bureau" (Google Cloud Console, ecran de
consentement Internal TB Groupe -- meme projet que le Plan A Gmail, cf.
docs/20260622_FUSEAU_RunbookOAuthGmail_v1.md) peut porter plusieurs scopes.

Ce module centralise la liste des scopes et le flow OAuth pour que
fetch_attachments.py (Gmail), crawl_drive_qualite.py (Drive) et gsheets.py
(Sheets) partagent le MEME token.json -- un seul consentement utilisateur
(Marlene) au lieu de trois.

Junior Tip : un refresh token ne vaut QUE pour les scopes consentis au moment
de sa creation. Si tu ajoutes un scope a SCOPES apres qu'un token.json existe
deja, Google refuse tout rafraichissement par un "RefreshError: invalid_scope"
(cause de l'ETL Gmail mort du 22/07 au 06/08/2026 : token a 2 scopes, SCOPES a 3).
Ce module detecte desormais l'ecart AVANT le refresh et leve
ScopesInsuffisantsError avec la marche a suivre (cf. COMMANDE_RECONSENTEMENT).

Prerequis (fait une fois, projet GCP existant du Plan A Gmail) :
  1. Console Google Cloud > APIs & Services > Library > activer "Google Drive API"
     et "Google Sheets API" (le projet et le client OAuth desktop existent deja).
  2. Mettre de cote config/token.json si un token a perimetre reduit existe deja.
  3. Lancer COMMANDE_RECONSENTEMENT : le navigateur s'ouvre, consentement sur
     les 3 scopes (gmail.readonly + drive.readonly + spreadsheets.readonly),
     token.json regenere.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Sequence

if TYPE_CHECKING:
    from google.oauth2.credentials import Credentials

logger = logging.getLogger(__name__)

# Perimetre le plus restreint possible : lecture seule sur les trois APIs.
# On ne demande jamais l'ecriture -- ni sur Gmail, ni sur Drive, ni sur Sheets.
SCOPES: list[str] = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/spreadsheets.readonly",
]

# Manipulation operateur, a lancer A LA MAIN depuis la racine du depot sur le
# poste qui porte le token (navigateur requis : impossible en tache planifiee).
# fetch_attachments --dry-run ouvre le flow OAuth sans telecharger ni ecrire
# autre chose que token.json.
COMMANDE_RECONSENTEMENT: str = (
    "Move-Item config\\token.json config\\token.json.bak -Force ; "
    ".\\.venv311\\Scripts\\python.exe -m src.scripts.gmail.fetch_attachments --dry-run"
)


class ScopesInsuffisantsError(RuntimeError):
    """
    Le token.json en cache ne couvre pas tous les scopes de SCOPES.

    Junior Tip : on herite de RuntimeError pour rester attrapable par le code
    existant, mais on donne un type dedie pour que les appelants (preflight,
    gsheets) puissent le distinguer d'une panne reseau et le laisser remonter
    au lieu de l'avaler.

    Attributes:
        manquants: Scopes requis absents du token.
        token_path: Chemin du token incrimine.
    """

    def __init__(self, manquants: Sequence[str], token_path: Path) -> None:
        self.manquants: list[str] = list(manquants)
        self.token_path: Path = token_path
        super().__init__(
            f"Le token OAuth {token_path} ne couvre pas les scopes requis. "
            f"Scopes manquants ou refuses par Google : {', '.join(self.manquants)}. "
            "Google refuse tout rafraichissement dont le perimetre depasse celui "
            "accorde au consentement (RefreshError: invalid_scope). "
            "A faire UNE FOIS, A LA MAIN, sur le poste avec navigateur (impossible "
            "en tache planifiee), depuis la racine du depot : "
            f"{COMMANDE_RECONSENTEMENT} "
            "puis valider dans le navigateur le consentement sur les 3 scopes "
            "(gmail.readonly, drive.readonly, spreadsheets.readonly)."
        )


def lire_scopes_token(token_path: Path) -> list[str] | None:
    """
    Lit les scopes enregistres dans token.json, sans appel reseau.

    Junior Tip : on lit le JSON brut et pas Credentials.scopes, car
    Credentials.from_authorized_user_file(path, SCOPES) remplace les scopes du
    fichier par ceux qu'on lui passe : l'objet charge "croit" avoir les 3 scopes
    meme si le token n'en porte que 2.

    Args:
        token_path: Chemin vers token.json.
    Returns:
        Liste des scopes du token, ou None si le champ est absent (format inconnu).
    Raises:
        OSError, ValueError: si le fichier est illisible ou n'est pas du JSON.
    """
    data = json.loads(token_path.read_text(encoding="utf-8"))
    brut = data.get("scopes")
    if brut is None:
        return None
    if isinstance(brut, str):
        return brut.split()
    return [str(s) for s in brut]


def scopes_manquants(
    scopes_token: Sequence[str] | None, requis: Sequence[str] = SCOPES
) -> list[str]:
    """
    Renvoie les scopes requis absents du token, dans l'ordre de `requis`.

    Args:
        scopes_token: Scopes portes par le token (None = inconnus).
        requis: Scopes attendus (SCOPES par defaut).
    Returns:
        Liste des scopes manquants (vide si tout est couvert ou si inconnu).
    """
    if scopes_token is None:
        return []
    presents = set(scopes_token)
    return [s for s in requis if s not in presents]


def verifier_scopes_token(token_path: Path, requis: Sequence[str] = SCOPES) -> None:
    """
    Garde-fou : leve ScopesInsuffisantsError si token.json ne couvre pas `requis`.

    Args:
        token_path: Chemin vers token.json (doit exister).
        requis: Scopes attendus (SCOPES par defaut).
    Raises:
        ScopesInsuffisantsError: si au moins un scope requis manque.
        OSError, ValueError: si le fichier est illisible.
    """
    scopes_token = lire_scopes_token(token_path)
    if scopes_token is None:
        logger.warning(
            "[ATTENTION] token.json sans champ 'scopes' (%s) : couverture non "
            "verifiable avant le refresh.", token_path)
        return
    manquants = scopes_manquants(scopes_token, requis)
    if manquants:
        erreur = ScopesInsuffisantsError(manquants, token_path)
        logger.error("[ECHEC] %s", erreur)
        raise erreur


def _est_invalid_scope(exc: BaseException) -> bool:
    """Vrai si l'erreur de refresh Google est un refus de perimetre."""
    return "invalid_scope" in str(exc)


def get_credentials(credentials_path: Path, token_path: Path) -> Credentials:
    """
    Charge ou obtient des credentials Google valides pour SCOPES (Gmail + Drive + Sheets).

    Le perimetre du token en cache est controle AVANT tout refresh : un token a
    perimetre reduit leve ScopesInsuffisantsError au lieu d'un RefreshError opaque.
    Jamais de repli silencieux : l'appelant doit laisser l'erreur remonter.

    Junior Tip : le controle est fait meme si le token n'est pas expire. Un
    access token encore valide mais sans spreadsheets.readonly passerait le
    chargement puis echouerait plus loin en "insufficient scope", loin de la
    cause reelle.

    Args:
        credentials_path: Chemin vers credentials.json (client OAuth desktop).
        token_path: Chemin vers token.json (cache du refresh token).
    Returns:
        google.oauth2.credentials.Credentials valide.
    Raises:
        FileNotFoundError: Si credentials.json est absent.
        ScopesInsuffisantsError: Si token.json ne couvre pas SCOPES (avant ou
            pendant le refresh).
    """
    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds: Credentials | None = None
    if token_path.exists():
        verifier_scopes_token(token_path)
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info("[INFO] Token expiré -- rafraîchissement silencieux")
            try:
                creds.refresh(Request())
            except RefreshError as exc:
                if not _est_invalid_scope(exc):
                    raise
                # Ceinture et bretelles : le token annonçait les bons scopes mais
                # Google les refuse (consentement revoque partiellement, etc.).
                erreur = ScopesInsuffisantsError(list(SCOPES), token_path)
                logger.error("[ECHEC] Refresh refusé (invalid_scope) : %s", erreur)
                raise erreur from exc
        else:
            if not credentials_path.exists():
                raise FileNotFoundError(
                    f"credentials.json introuvable : {credentials_path}. "
                    "Voir les prérequis OAuth en tête de module."
                )
            logger.info(
                "[INFO] Consentement OAuth requis "
                "(gmail.readonly + drive.readonly + spreadsheets.readonly)")
            flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
            creds = flow.run_local_server(port=0)
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json(), encoding="utf-8")
        logger.info("[SUCCÈS] Token mis en cache : %s", token_path)

    return creds
