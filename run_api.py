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
from pathlib import Path

import uvicorn

from src.utils.config_manager import Config
from src.utils.git_sync import synchroniser
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

    Garde-fous par rapport à la version initiale :

    1. Le pull s'exécute dans le répertoire du dépôt (RACINE_PROJET) et non
       dans le répertoire courant. Lancée en service Windows, la commande
       partait de C:\\Windows\\system32 et mettait à jour un dépôt arbitraire,
       ou échouait sans que personne ne le voie.
    2. La cible est BRANCHE_DEPLOIEMENT, configurable dans config/.env. En
       pointant une branche ou un tag de release plutôt que main, un commit
       cassé poussé en cours de journée ne casse plus l'application de Marlène
       à son prochain lancement.
    3. Seuls les fichiers SUIVIS modifiés bloquent le pull. Les fichiers non
       suivis (un .log.err, une sauvegarde .env, un .docx déposé) l'avaient
       annulé trois fois alors qu'ils ne gênent pas une avance rapide.
    4. Un pull bloqué ou en échec est signalé en ERREUR avec la liste des
       fichiers, et laisse un marqueur deploy/logs/PULL_BLOQUE.txt. La logique
       vit dans src.utils.git_sync, couverte par src/tests/test_git_sync.py.
    """
    if not Config.API_AUTO_PULL:
        logger.info("[GIT] Auto-sync désactivé (API_AUTO_PULL=0).")
        return

    resultat = synchroniser(RACINE_PROJET, Config.BRANCHE_DEPLOIEMENT)
    if not resultat.ok:
        logger.error("[GIT] [ECHEC] L'application démarre sur le code local (%s), pas sur %s.",
                     resultat.head_avant, resultat.branche)


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
