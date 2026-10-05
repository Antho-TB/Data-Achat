# [PREFLIGHT] Verification d'environnement avant le pipeline Gmail (poste Marlene)
"""Diagnostic de pre-vol : verifie en quelques secondes que le poste est pret a
lancer l'ingestion Gmail (PJ fournisseurs vers achat.ot_transport).

Strategie metier : la session sur le poste de Marlene est courte et le pipeline
depend de plusieurs briques externes (VPN, token Gmail, OCR, DWH). Plutot que de
decouvrir un blocage au milieu du run, on controle tout d'un coup en tete de
session. Chaque verification est isolee : une brique KO n'empeche pas de voir
l'etat des autres.

Junior Tip : un "preflight" c'est la check-list du pilote avant decollage. On ne
repare rien ici, on constate. Le code de sortie vaut 0 si tout est vert, 3 si le
token Google exige un reconsentement manuel (scopes insuffisants ou token
absent), 1 s'il manque une autre brique critique (pour pouvoir enchainer ou
s'arreter en connaissance de cause).
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from pathlib import Path

from src.utils.google_auth import (
    COMMANDE_RECONSENTEMENT,
    ScopesInsuffisantsError,
    verifier_scopes_token,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s -- %(message)s",
)
logger = logging.getLogger("preflight_gmail")

ROOT = Path(__file__).resolve().parents[3]
TOKEN_PATH = ROOT / "config" / "token.json"
CREDENTIALS_PATH = ROOT / "config" / "credentials.json"

# Les scopes attendus ne sont plus dupliques ici : la liste locale n'en portait
# que 2 quand google_auth.SCOPES en demandait 3, et le preflight passait au vert
# sur un token incapable de se rafraichir. Source unique : google_auth.SCOPES.

# Statuts du controle token (cf. check_gmail_token).
STATUT_OK = "ok"
STATUT_KO = "ko"
STATUT_CONSENTEMENT = "consentement"

# Codes de sortie lus par deploy/run_gmail_etl.ps1.
EXIT_OK = 0
EXIT_CRITIQUE = 1  # VPN/DWH/OCR : skip propre cote tache planifiee
EXIT_CONSENTEMENT = 3  # reconsentement OAuth manuel requis : echec visible


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


def check_gmail_token(
    token_path: Path = TOKEN_PATH, credentials_path: Path = CREDENTIALS_PATH
) -> str:
    """Controle la presence du token Gmail et la couverture des scopes attendus.

    On ne fait PAS d'appel reseau ici (pour ne pas declencher un consentement
    interactif) : on lit juste le token en cache et on le compare a SCOPES via
    le garde-fou partage de google_auth.

    Junior Tip : on renvoie un statut a 3 valeurs et pas un booleen, car le
    remede n'est pas le meme. Un VPN tombe se resout tout seul au prochain run
    (skip propre) ; un scope manquant ne se resout JAMAIS sans un humain devant
    le navigateur, donc la tache planifiee doit apparaitre en echec.

    Returns:
        STATUT_OK, STATUT_KO (brique absente/illisible) ou STATUT_CONSENTEMENT
        (token absent ou scopes insuffisants : reconsentement manuel requis).
    """
    if not credentials_path.exists():
        logger.error("[ECHEC] credentials.json manquant (%s).", credentials_path)
        return STATUT_KO
    if not token_path.exists():
        logger.error(
            "[ECHEC] token.json absent (%s) : consentement manuel requis, a lancer "
            "depuis la racine du depot : %s", token_path, COMMANDE_RECONSENTEMENT)
        return STATUT_CONSENTEMENT
    try:
        verifier_scopes_token(token_path)
    except ScopesInsuffisantsError:
        # Le detail (scopes manquants + commande) est deja logue en [ECHEC].
        return STATUT_CONSENTEMENT
    except (OSError, ValueError) as exc:
        logger.error("[ECHEC] token.json illisible : %s", exc)
        return STATUT_KO
    logger.info("[SUCCES] token Google present, scopes Gmail + Drive + Sheets couverts.")
    return STATUT_OK


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
    critique, et distingue le cas "reconsentement OAuth" (EXIT_CONSENTEMENT) qui
    ne se resoudra jamais tout seul.

    Returns:
        EXIT_OK, EXIT_CONSENTEMENT (prioritaire) ou EXIT_CRITIQUE.
    """
    logger.info("=== Pre-vol pipeline Gmail (poste Marlene) ===")

    statut_token = check_gmail_token()
    critiques = {
        "OCR Tesseract": check_binary("Tesseract", ["tesseract", "--version"]),
        "OCR Poppler": check_binary("Poppler (pdftoppm)", ["pdftoppm", "-v"]),
        "Token Gmail": statut_token == STATUT_OK,
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
        return EXIT_OK
    if statut_token == STATUT_CONSENTEMENT:
        logger.error(
            "[ECHEC] Reconsentement OAuth Google requis (exit %d). A lancer A LA MAIN "
            "depuis la racine du depot, navigateur ouvert : %s",
            EXIT_CONSENTEMENT, COMMANDE_RECONSENTEMENT)
        return EXIT_CONSENTEMENT
    logger.error("[ECHEC] Au moins une brique critique manque, corriger avant de lancer le pipeline.")
    return EXIT_CRITIQUE


if __name__ == "__main__":
    raise SystemExit(main())
