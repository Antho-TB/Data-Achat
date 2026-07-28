# -*- coding: utf-8 -*-
"""
[UTIL]
=============================================================================
CONFIGURATION DE LOGGING COMMUNE AUX SCRIPTS FUSEAU
=============================================================================

Chaque script batch redefinissait son propre logging.basicConfig, avec des
formats differents et sans museler le SDK Azure. Resultat : le log utile
(3 lignes) noye sous 80 lignes de trace HTTP Key Vault, illisible quand on
diagnostique une tache planifiee qui a echoue a 2h du matin.

Junior Tip : basicConfig ne fait effet qu'au PREMIER appel du processus. Si
une bibliotheque importee configure le logging avant nous, notre format est
ignore, d'ou le force=True.

Usage :
    from src.utils.logging_setup import setup_logging
    setup_logging()
"""
from __future__ import annotations

import logging

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s -- %(message)s"

# Loggers bavards qui n'apportent rien en exploitation courante.
NOISY_LOGGERS = (
    "azure.core.pipeline",
    "azure.core.pipeline.policies.http_logging_policy",
    "azure.identity",
    "urllib3",
    "sqlalchemy.engine",
    "googleapiclient.discovery_cache",
)


def setup_logging(level: int = logging.INFO) -> None:
    """
    Applique le format de log standard FUSEAU et coupe le bruit des SDK.

    Args:
        level: niveau de log des modules du projet (INFO par defaut).
    """
    logging.basicConfig(level=level, format=LOG_FORMAT, force=True)
    for name in NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
