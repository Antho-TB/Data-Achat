"""
Configuration centralisée  -- Data-Achat
Charge les paramètres depuis Azure Key Vault (prod) ou .env (dev local).
"""
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

# Charger config/.env (relatif à la racine du projet)
_env_path = Path(__file__).resolve().parent.parent.parent / "config" / ".env"
load_dotenv(dotenv_path=_env_path)

logger = logging.getLogger(__name__)


def get_base_path() -> Path:
    """Retourne la racine du projet (compatible PyInstaller et exécution directe)."""
    import sys
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent.parent


class Config:
    # Azure Key Vault (prod)
    KEY_VAULT_NAME: str = os.getenv("KEY_VAULT_NAME", "")

    # PostgreSQL  -- valeurs fallback pour dev local (.env)
    PG_HOST: str = os.getenv("PG_HOST", "")
    PG_PORT: int = int(os.getenv("PG_PORT", "5432"))
    PG_DB: str = os.getenv("PG_DB", "dtpf_sylob_prod")
    PG_USER: str = os.getenv("PG_USER", "")
    PG_PASSWORD: str = os.getenv("PG_PASSWORD", "")
    PG_SCHEMA: str = "achat"

    # DWH Sylob On-Premise (tarrerias_production_dwh)
    SYLOB_HOST: str = os.getenv("SYLOB_HOST", "192.168.102.21")
    SYLOB_PORT: int = int(os.getenv("SYLOB_PORT", "5433"))
    SYLOB_DB: str = os.getenv("SYLOB_DB", "tarrerias_production_dwh")
    SYLOB_USER: str = os.getenv("SYLOB_USER", "")
    SYLOB_PASSWORD: str = os.getenv("SYLOB_PASSWORD", "")
    # Schéma société principale
    SYLOB_SCHEMA: str = "TARRERIAS_GENERALE_DE_DECOUPAGE"

    # Répertoire des fichiers sources Excel
    DATA_DIR: str = os.getenv("DATA_DIR", "Service_Achat")

    @classmethod
    def get_pg_url(cls) -> "URL":
        """
        Construit l'URL de connexion PostgreSQL via sqlalchemy.engine.URL.create().
        Utilise URL.create() pour gérer correctement les caractères spéciaux
        dans le mot de passe (ex: @, #, ?, etc.) sans encoding manuel.
        Tente Key Vault en priorité, repli sur variables d'environnement.
        """
        from sqlalchemy.engine import URL

        if cls.KEY_VAULT_NAME:
            try:
                return cls._get_pg_url_from_keyvault()
            except Exception as exc:
                logger.warning("Key Vault inaccessible (%s), fallback .env", exc)

        if not cls.PG_HOST or not cls.PG_USER:
            raise ValueError(
                "Credentials PostgreSQL manquants. "
                "Définir PG_HOST, PG_USER, PG_PASSWORD dans .env ou Key Vault."
            )
        return URL.create(
            drivername="postgresql+psycopg2",
            username=cls.PG_USER,
            password=cls.PG_PASSWORD,
            host=cls.PG_HOST,
            port=cls.PG_PORT,
            database=cls.PG_DB,
            query={"sslmode": "require"},
        )

    @classmethod
    def get_sylob_url(cls) -> "URL":
        """
        Connexion au DWH Sylob On-Premise (tarrerias_production_dwh).
        Serveur local réseau bureau : 192.168.102.21:5433
        Accessible uniquement via VPN Stormshield.
        Accès lecture seule avec user dataviz-admin.
        """
        from sqlalchemy.engine import URL
        if not cls.SYLOB_USER:
            raise ValueError("SYLOB_USER manquant dans .env")
        return URL.create(
            drivername="postgresql+psycopg2",
            username=cls.SYLOB_USER,
            password=cls.SYLOB_PASSWORD,
            host=cls.SYLOB_HOST,
            port=cls.SYLOB_PORT,
            database=cls.SYLOB_DB,
            query={"sslmode": "prefer"},
        )

    @classmethod
    def _get_pg_url_from_keyvault(cls) -> "URL":
        """Récupère les credentials PostgreSQL depuis Azure Key Vault."""
        from azure.identity import DefaultAzureCredential
        from azure.keyvault.secrets import SecretClient
        from sqlalchemy.engine import URL

        vault_url = f"https://{cls.KEY_VAULT_NAME}.vault.azure.net/"
        client = SecretClient(vault_url=vault_url, credential=DefaultAzureCredential())

        user = client.get_secret("psql-prod-sylob-anthony-bezille-login").value
        password = client.get_secret("psql-prod-sylob-anthony-bezille-password").value

        return URL.create(
            drivername="postgresql+psycopg2",
            username=user,
            password=password,
            host=cls.PG_HOST,
            port=cls.PG_PORT,
            database=cls.PG_DB,
            query={"sslmode": "require"},
        )
