# [PREFLIGHT] Verification d'environnement avant le pipeline Gmail (poste Marlene)
"""Diagnostic de pre-vol : verifie en quelques secondes que le poste est pret a
lancer l'ingestion Gmail (PJ fournisseurs vers achat.ot_transport).

Strategie metier : la session sur le poste de Marlene est courte et le pipeline
depend de plusieurs briques externes (VPN, token Gmail, OCR, DWH). Plutot que de
decouvrir un blocage au milieu du run, on controle tout d'un coup en tete de
session. Chaque verification est isolee : une brique KO n'empeche pas de voir
l'etat des autres.

Junior Tip : un "preflight" c'est la check-list du pilote avant decollage. On ne
repare rien ici, on constate. Le code de sortie vaut 0 si tout est vert, 1 s'il
manque une brique critique (pour pouvoir enchainer ou s'arreter en connaissance
de cause).
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s -- %(message)s",
)
logger = logging.getLogger("preflight_gmail")

ROOT = Path(__file__).resolve().parents[3]
TOKEN_PATH = ROOT / "config" / "token.json"
CREDENTIALS_PATH = ROOT / "config" / "credentials.json"

# Scopes minimaux attendus dans le token (Gmail lecture + Drive lecture).
EXPECTED_SCOPES = (
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
)


def check_python_version() -> bool:
    """Le poste doit tourner en Python 3.11 (3.13 cassait sqlalchemy)."""
    major, minor = sys.version_info[:2]
    ok = (major, minor) == (3, 11)
    if ok:
        logger.info("[SUCCES] Python %d.%d (3.11 attendu).", major, minor)
    else:
        logger.warning("[ATTENTION] Python %d.%d != 3.11 attendu (venv 3.11 requis).", major, minor)
    return ok


def check_binary(name: str, cmd: list[str]) -> bool:
    """Verifie qu'un binaire systeme est installe et repond (OCR : tesseract, poppler)."""
    if shutil.which(cmd[0]) is None:
        logger.error("[ECHEC] %s absent du PATH (binaire '%s' introuvable).", name, cmd[0])
        return False
    try:
        subprocess.run(cmd, capture_output=True, check=True, timeout=15)
        logger.info("[SUCCES] %s disponible.", name)
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        logger.error("[ECHEC] %s present mais ne repond pas : %s", name, exc)
        return False


def check_gmail_token() -> bool:
    """Controle la presence du token Gmail et la couverture des scopes attendus.

    On ne fait PAS d'appel reseau ici (pour ne pas declencher un consentement
    interactif) : on lit juste le token en cache. Si les scopes manquent, il
    faudra re-consentir une fois au premier fetch.
    """
    if not CREDENTIALS_PATH.exists():
        logger.error("[ECHEC] credentials.json manquant (%s).", CREDENTIALS_PATH)
        return False
    if not TOKEN_PATH.exists():
        logger.warning("[ATTENTION] token.json absent : un consentement Gmail sera demande au 1er run.")
        return False
    try:
        data = json.loads(TOKEN_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.error("[ECHEC] token.json illisible : %s", exc)
        return False
    scopes = set(data.get("scopes", []))
    manquants = [s for s in EXPECTED_SCOPES if s not in scopes]
    if manquants:
        logger.warning("[ATTENTION] scopes manquants dans le token : %s (re-consentement requis).", manquants)
        return False
    logger.info("[SUCCES] token Gmail present, scopes Gmail + Drive couverts.")
    return True


def check_git_sync() -> bool:
    """Verifie que le code local est bien a jour avec origin/main (evite de tourner sur du vieux code)."""
    try:
        subprocess.run(["git", "fetch", "origin"], cwd=ROOT, capture_output=True, timeout=30, check=True)
        local = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
        remote = subprocess.run(["git", "rev-parse", "origin/main"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        logger.warning("[ATTENTION] impossible de verifier la synchro git : %s", exc)
        return False
    if local == remote:
        logger.info("[SUCCES] code a jour avec origin/main (%s).", local[:8])
        return True
    logger.warning("[ATTENTION] HEAD (%s) != origin/main (%s) : lancer 'git pull'.", local[:8], remote[:8])
    return False


def check_dwh() -> bool:
    """Teste la connexion au DWH Azure (VPN actif + credentials valides)."""
    try:
        from app.database import get_engine
        from sqlalchemy import text
    except ImportError as exc:
        logger.error("[ECHEC] import du moteur DWH impossible : %s", exc)
        return False
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("[SUCCES] DWH Azure joignable (VPN + credentials OK).")
        return True
    except Exception as exc:  # noqa: BLE001 -- on veut afficher toute erreur reseau/auth
        logger.error("[ECHEC] DWH injoignable (VPN tombe ? ETIMEDOUT ?) : %s", type(exc).__name__)
        return False


def main() -> int:
    """Lance toutes les verifications et resume l'etat du poste.

    Junior Tip : les binaires OCR, le token et le DWH sont critiques pour le run.
    La version Python et la synchro git sont des avertissements (le run peut
    demarrer mais on prend un risque). Le code de sortie ne bloque que sur le
    critique.
    """
    logger.info("=== Pre-vol pipeline Gmail (poste Marlene) ===")

    critiques = {
        "OCR Tesseract": check_binary("Tesseract", ["tesseract", "--version"]),
        "OCR Poppler": check_binary("Poppler (pdftoppm)", ["pdftoppm", "-v"]),
        "Token Gmail": check_gmail_token(),
        "DWH Azure": check_dwh(),
    }
    avertissements = {
        "Python 3.11": check_python_version(),
        "Synchro git": check_git_sync(),
    }

    logger.info("=== Resume ===")
    for nom, ok in {**critiques, **avertissements}.items():
        logger.info("  %s : %s", nom, "OK" if ok else "A CORRIGER")

    if all(critiques.values()):
        logger.info("[SUCCES] Poste pret : le pipeline Gmail peut demarrer.")
        return 0
    logger.error("[ECHEC] Au moins une brique critique manque, corriger avant de lancer le pipeline.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
