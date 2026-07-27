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
import uvicorn

from src.utils.config_manager import Config

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s -- %(message)s")
logger = logging.getLogger("run_api")


def auto_pull_git() -> None:
    """Tente une mise à jour automatique depuis GitHub avant le démarrage de l'API."""
    try:
        logger.info("[GIT] Vérification des mises à jour GitHub (git pull origin main)...")
        res = subprocess.run(
            ["git", "pull", "origin", "main", "--quiet"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if res.returncode == 0:
            logger.info("[GIT] Code à jour avec GitHub.")
        else:
            logger.warning("[GIT] Warning git pull (ex: hors-ligne/modifs locales) : %s", res.stderr.strip())
    except Exception as e:
        logger.warning("[GIT] Impossible d'effectuer la maj git automatique : %s", e)


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
