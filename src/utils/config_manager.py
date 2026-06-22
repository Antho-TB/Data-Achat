# -*- coding: utf-8 -*-
"""
[ARCHITECTURE]
Configuration centralisée du projet Data-Achat TB Groupe.

Stratégie : deux niveaux de credentials selon l'environnement d'exécution.
En production (KEY_VAULT_NAME défini), les secrets sont lus depuis Azure Key Vault
via DefaultAzureCredential (Managed Identity ou az login). En développement local,
le fichier config/.env sert de fallback. Ce pattern garantit qu'aucun secret
n'est jamais hardcodé dans le code source ni dans le dépôt Git.
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
    """
    Retourne la racine du projet, compatible PyInstaller et exécution directe.

    Junior Tip : PyInstaller compile le script Python en exécutable .exe et
    définit sys.frozen = True. Dans ce mode, __file__ n'existe plus -- il faut
    utiliser sys.executable (chemin vers le .exe) pour remonter à la racine.
    Ce double comportement est indispensable pour distribuer le pipeline en
    production sans Python installé sur la machine cible.

    Returns:
        Path vers la racine du projet Data-Achat.
    """
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

    # Fichier transitaire (suivi maritime) -- source des ETD réel/ETA/livraison.
    # Vide = mode dégradé (ot_transport bootstrappé depuis achat.commande).
    # Prod : \\Srv-files-pom\partage\ADA\METIER\SUIVI CDES IMPORT\2026\TRANSITAIRE\2026 SUIVI MARITIME.xlsx
    SUIVI_MARITIME_PATH: str = os.getenv("SUIVI_MARITIME_PATH", "")

    # API FastAPI (ERP Achat)
    API_HOST: str = os.getenv("API_HOST", "127.0.0.1")
    API_PORT: int = int(os.getenv("API_PORT", "5050"))
    # Clé exigée sur les endpoints d'écriture (header X-API-Key).
    # Vide = écriture refusée (fail-closed) : la définir dans config/.env.
    API_KEY: str = os.getenv("API_KEY", "")
    # Hot-reload uvicorn (dev uniquement). Désactivé par défaut : WatchFiles
    # s'est montré non fiable sous Windows (workers orphelins, reloads manqués).
    API_RELOAD: bool = os.getenv("API_RELOAD", "0") == "1"
    # Origines CORS autorisées (liste séparée par virgules). Le frontend est
    # servi par FastAPI (même origine) : seuls les accès cross-origin explicites
    # sont listés ici.
    CORS_ORIGINS: list[str] = [
        o.strip()
        for o in os.getenv(
            "CORS_ORIGINS", "http://127.0.0.1:5050,http://localhost:5050"
        ).split(",")
        if o.strip()
    ]

    @classmethod
    def get_pg_url(cls) -> "URL":
        """
        Construit l'URL de connexion PostgreSQL via sqlalchemy.engine.URL.create().

        Utilise URL.create() (et non un f-string) pour gérer correctement les
        caractères spéciaux dans le mot de passe (@, #, ?, etc.) sans encoding
        manuel -- URL.create() gère le percent-encoding automatiquement.
        Tente Key Vault en priorité, repli sur variables d'environnement.

        Junior Tip : DefaultAzureCredential essaie plusieurs méthodes d'authentification
        Azure dans l'ordre (Managed Identity, Visual Studio Code, az login, etc.).
        En CI/CD sur Azure, la Managed Identity prend le dessus sans configuration.

        Returns:
            URL SQLAlchemy prête pour create_engine().
        Raises:
            ValueError: Si les credentials PostgreSQL sont manquants (ni KV ni .env).
        """
        from sqlalchemy.engine import URL

        if cls.KEY_VAULT_NAME:
            try:
                return cls._get_pg_url_from_keyvault()
            except Exception as exc:
                logger.warning("[ATTENTION] Key Vault inaccessible (%s), fallback .env", exc)

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
        Construit l'URL de connexion au DWH Sylob On-Premise (tarrerias_production_dwh).

        Le serveur Sylob est une instance PostgreSQL sur le réseau bureau TB Groupe
        (192.168.102.21:5433), accessible uniquement via VPN Stormshield.
        L'accès est en lecture seule avec l'utilisateur dataviz-admin pour garantir
        qu'aucune écriture accidentelle ne modifie les données de production ERP.

        Junior Tip : sslmode='prefer' (et non 'require') car le serveur Sylob interne
        n'a pas de certificat SSL configuré -- 'prefer' tente SSL mais accepte le plain.
        Sur le DWH Azure (bitb-2025), on utilise 'require' pour forcer le chiffrement.

        Returns:
            URL SQLAlchemy pour tarrerias_production_dwh.
        Raises:
            ValueError: Si SYLOB_USER est manquant dans .env.
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
        """
        Récupère les credentials PostgreSQL depuis Azure Key Vault.

        Utilise DefaultAzureCredential qui s'adapte automatiquement à l'environnement :
        Managed Identity en prod Azure, az login en dev local. Les noms des secrets
        Key Vault suivent la convention du projet (psql-prod-sylob-*-login/password).

        Junior Tip : SecretClient.get_secret() est une opération réseau -- c'est
        pourquoi get_pg_url() l'encapsule dans un try/except avec fallback .env.
        Si le Key Vault est inaccessible (réseau, permissions), le pipeline
        continue en mode dégradé grâce aux variables d'environnement locales.

        Returns:
            URL SQLAlchemy avec credentials issus du Key Vault.
        """
        from azure.identity import DefaultAzureCredential
        from azure.keyvault.secrets import SecretClient
        from sqlalchemy.engine import URL

        vault_url = f"https://{cls.KEY_VAULT_NAME}.vault.azure.net/"
        client = SecretClient(vault_url=vault_url, credential=DefaultAzureCredential())

        user = client.get_secret("psql-prod-sylob-anthony-bezille-login").value
        password = client