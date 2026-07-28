# -*- coding: utf-8 -*-
"""
[SCRIPT]
=============================================================================
LANCEMENT LOCAL - ERP ACHAT FUSEAU (uvicorn)
=============================================================================

Lancement local POC -- ERP Achat TB Groupe
Usage : python run_api.py
Host/port configures dans config/.env (API_HOST, API_PORT) -- defaut 127.0.0.1:5050.
Auto-sync GitHub : tente un 'git pull origin main' au lancement pour s'assurer que
le poste local (ex. Marlène) dispose toujours du code le plus récent.
"""
import logging
import subprocess
from pathlib import Path

import uvicorn

from src.utils.config_manager import Config
from src.utils.logging_setup import setup_logging

setup_logging()
logger = logging.getLogger("run_api")

# Racine du dépôt, déduite de l'emplacement de ce fichier et jamais du
# répertoire courant : lancée en service Windows, la commande git partait
# de C:\Windows\system32.
RACINE_PROJET = Path(__file__).resolve().parent


def auto_pull_git() -> None:
    """
    Met le poste à jour depuis GitHub avant le démarrage de l'API.

    Trois garde-fous par rapport à la version initiale :

    1. Le pull s'exécute dans le répertoire du dépôt (RACINE_PROJET) et non
       dans le répertoire courant. Lancée en service Windows, la commande
       partait de C:\\Windows\\system32 et mettait à jour un dépôt arbitraire,
       ou échouait sans que personne ne le voie.
    2. La cible est BRANCHE_DEPLOIEMENT, configurable dans config/.env. En
       pointant une branche ou un tag de release plutôt que main, un commit
       cassé poussé en cours de journée ne casse plus l'application de Marlène
       à son prochain lancement.
    3. Un dépôt local modifié ou un pull en échec est signalé en ERREUR
       explicite, pas en warning noyé : l'utilisateur doit savoir qu'il tourne
       sur une version qui n'est pas celle attendue.
    """
    if not Config.API_AUTO_PULL:
        logger.info("[GIT] Auto-sync désactivé (API_AUTO_PULL=0).")
        return

    branche = Config.BRANCHE_DEPLOIEMENT
    try:
        modifs = subprocess.run(
            ["git", "-C", str(RACINE_PROJET), "status", "--porcelain"],
            capture_output=True, text=True, timeout=10,
        )
        if modifs.stdout.strip():
            logger.error("[GIT] [ECHEC] Modifications locales non commitées, pull annulé. "
                         "L'application démarre sur le code local, pas sur %s.", branche)
            return

        logger.info("[GIT] Synchronisation sur %s...", branche)
        res = subprocess.run(
            ["git", "-C", str(RACINE_PROJET), "pull", "origin", branche, "--ff-only", "--quiet"],
            capture_output=True, text=True, timeout=30,
        )
        if res.returncode == 0:
            logger.info("[GIT] [SUCCES] Code à jour sur %s.", branche)
        else:
            logger.error("[GIT] [ECHEC] Pull impossible, démarrage sur le code local : %s",
                         res.stderr.strip() or res.stdout.strip())
    except (OSError, subprocess.SubprocessError) as e:
        logger.error("[GIT] [ECHEC] Synchronisation impossible, démarrage sur le code local : %s", e)


if __name__ == "__main__":
    auto_pull_git()
    uvicorn.run(
        "app.main:app",
        host=Config.API_HOST,
        port=Config.API_PORT,
        reload=Config.API_RELOAD,  # API_RELOAD=1 dans .env pour le dev uniquement
        reload_dirs=["app", "frontend"] if Config.API_RELOAD else None,
        log_level="info",
    )
