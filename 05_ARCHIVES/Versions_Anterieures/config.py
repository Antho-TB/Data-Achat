"""
Configuration centralisée — ERP Achat TB Groupe
Pattern : .env POC / Key Vault prod (KEY_VAULT_NAME non vide)
"""
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Charger .env depuis config/ (POC) ou à la racine
_env_path = Path(__file__).parent.parent / "config" / ".env"
if not _env_path.exists():
    _env_path = Path(__file__).parent.parent / ".env"
load_dotenv(_env_path)


@dataclass(frozen=True)
class Config:
    pg_host: str
    pg_port: int
    pg_db: str
    pg_user: str
    pg_password: str
    pg_schema: str
    key_vault_name: str
    api_host: str
    api_port: int

    @classmethod
    def from_env(cls) -> "Config":
        kv_name = os.getenv("KEY_VAULT_NAME", "")

        if kv_name:
            # Mode prod : récupérer depuis Key Vault
            from azure.identity import DefaultAzureCredential
            from azure.keyvault.secrets import SecretClient

            kv_client = SecretClient(
                vault_url=f"https://{kv_name}.vault.azure.net/",
                credential=DefaultAzureCredential(),
            )
            # Compte POC Achat (isolation Nubo : jamais le compte MyReport ici)
            pg_user = kv_client.get_secret("psql-prod-sylob-anthony-bezille-login").value
            pg_password = kv_client.get_secret("psql-prod-sylob-anthony-bezille-password").value
        else:
            # Mode POC : .env direct
            pg_user = os.environ["PG_USER"]
            pg_password = os.environ["PG_PASSWORD"]

        return cls(
            pg_host=os.getenv("PG_HOST", "psql-dtpf-psql-prod.postgres.database.azure.com"),
            pg_port=int(os.getenv("PG_PORT", "5432")),
            pg_db=os.getenv("PG_DB", "dtpf_sylob_prod"),
            pg_user=pg_user,
            pg_password=pg_password,
            pg_schema=os.getenv("PG_SCHEMA", "achat"),
            key_vault_name=kv_name,
            api_host=os.getenv("API_HOST", "127.0.0.1"),
            api_port=int(os.getenv("API_PORT", "8000")),
        )


# Singleton chargé une seule fois au démarrage
settings = Config.from_env()
