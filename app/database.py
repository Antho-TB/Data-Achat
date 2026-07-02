# -*- coding: utf-8 -*-
"""
[API]
=============================================================================
CONNEXION POSTGRESQL - MOTEUR & SANTE
=============================================================================

Connexion PostgreSQL Azure -- SQLAlchemy Core
Pattern obligatoire TB Groupe : URL.create() (jamais f-string).
Config unifiée : src/utils/config_manager.py (source unique API + ETL).
"""
import logging

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from src.utils.config_manager import Config

logger = logging.getLogger(__name__)

_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(
            Config.get_pg_url(), pool_pre_ping=True, pool_size=5, max_overflow=10
        )
        logger.info("[SUCCES] Connexion PostgreSQL etablie : %s", Config.PG_HOST)
    return _engine


def check_connection() -> bool:
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.error("[ECHEC] Connexion PostgreSQL : %s", exc)
        return False
