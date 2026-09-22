# -*- coding: utf-8 -*-
"""
[OPS]
=============================================================================
APPLICATION DU COMPTE DE SERVICE DE L'API FUSEAU
=============================================================================

Cree (ou met a jour) le role PostgreSQL dedie a l'API FUSEAU hebergee et lui
pose les droits au moindre privilege decrits dans
`sql/20260903_role_api_fuseau.sql`.

Pourquoi un script plutot que psql : les instructions ont besoin du mot de passe
du compte de service, et un mot de passe ne doit jamais transiter par un fichier
SQL, un argument de ligne de commande ni la sortie console. Ici il est lu au Key
Vault et passe directement au serveur, sans jamais etre affiche.

Le role est cree par le compte administrateur PostgreSQL (seul porteur de
l'attribut CREATEROLE) : les tables de `achat` appartiennent pour partie au
compte nominal d'Antho, pour partie a platform_team, et seul l'administrateur
peut accorder des droits sur les deux lots.

Idempotent, non destructif : aucun DROP, aucun DELETE, aucune donnee touchee.

Usage : python -m deploy.appliquer_role_api_fuseau [--dry-run]
"""
from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass

from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

from src.utils.logging_setup import setup_logging

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Config:
    """Centralise les cibles et noms de secrets du deploiement du role API."""

    key_vault_app: str = "kv-dtpf-prod"
    key_vault_admin: str = "kv-platform-vault-prod"
    secret_role_password: str = "psql-prod-fuseau-api-password"
    secret_admin_user: str = "dtpf-psql-admin-username-prod"
    secret_admin_password: str = "dtpf-psql-admin-password-prod"
    pg_host: str = "psql-dtpf-psql-prod.postgres.database.azure.com"
    pg_database: str = "dtpf_sylob_prod"
    role: str = "dtpf_fuseau_api_prod"
    tables_ecriture: tuple[str, ...] = ("commande_annotation", "artwork_statut")


def _secret(client: SecretClient, nom: str) -> str:
    """
    Lit un secret Key Vault et refuse explicitement une valeur vide.

    Junior Tip : une valeur vide ne doit jamais produire un compte de service
    inutilisable. On arrete avant toute transaction PostgreSQL, donc aucun droit
    partiel n'est applique.
    """
    valeur = client.get_secret(nom).value
    if not valeur:
        raise RuntimeError(f"Secret Key Vault vide : {nom}")
    return valeur


def appliquer(dry_run: bool = False) -> None:
    """
    Cree le role de service et pose les droits.

    Junior Tip : le mot de passe ne peut pas etre passe en parametre bind d'un
    CREATE ROLE (PostgreSQL n'accepte pas de parametre a cet endroit). On utilise
    donc le quoting serveur via `quote_literal` d'une chaine passee, elle, en
    parametre bind : la valeur ne traverse jamais le SQL en clair cote client.
    """
    config = Config()
    credential = DefaultAzureCredential()
    client_app = SecretClient(
        vault_url=f"https://{config.key_vault_app}.vault.azure.net/",
        credential=credential,
    )
    client_admin = SecretClient(
        vault_url=f"https://{config.key_vault_admin}.vault.azure.net/",
        credential=credential,
    )
    mot_de_passe = _secret(client_app, config.secret_role_password)
    admin_user = _secret(client_admin, config.secret_admin_user)
    admin_pass = _secret(client_admin, config.secret_admin_password)

    url = URL.create(
        drivername="postgresql+psycopg2",
        username=admin_user,
        password=admin_pass,
        host=config.pg_host,
        port=5432,
        database=config.pg_database,
        query={"sslmode": "require"},
    )
    engine = create_engine(url)

    with engine.begin() as conn:
        existe = conn.execute(
            text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": config.role}
        ).scalar()

        if dry_run:
            logger.info(
                "[INFO] DRY-RUN : role %s %s",
                config.role,
                "deja present" if existe else "a creer",
            )
            return

        # CREATE/ALTER ROLE ... PASSWORD n'accepte pas de parametre bind : on
        # fabrique l'instruction cote serveur avec quote_literal, qui echappe la
        # valeur. Pas de format() ici : ses marqueurs %s entrent en conflit avec
        # le paramstyle de psycopg2 et le SQL part en erreur de syntaxe.
        prefixe = (
            f"ALTER ROLE {config.role} PASSWORD "
            if existe
            else f"CREATE ROLE {config.role} LOGIN PASSWORD "
        )
        instruction = conn.execute(
            text("SELECT :prefixe || quote_literal(:pwd)"),
            {"prefixe": prefixe, "pwd": mot_de_passe},
        ).scalar()
        conn.execute(text(instruction))
        logger.info(
            "[SUCCES] Role %s %s.",
            config.role,
            "mis a jour" if existe else "cree",
        )

        # Sans CONNECT, le role existe mais la connexion est refusee au niveau
        # de la base : erreur "permission denied for database", constatee le
        # 03/09 sur le premier essai.
        conn.execute(text(f'GRANT CONNECT ON DATABASE "{config.pg_database}" TO {config.role}'))
        conn.execute(text(f"GRANT USAGE ON SCHEMA achat TO {config.role}"))
        conn.execute(text(f"GRANT USAGE ON SCHEMA public TO {config.role}"))
        conn.execute(text(f"GRANT SELECT ON ALL TABLES IN SCHEMA achat TO {config.role}"))
        conn.execute(text(f"GRANT SELECT ON TABLE public.articles3 TO {config.role}"))
        conn.execute(
            text(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA achat TO {config.role}")
        )
        logger.info("[SUCCES] Lecture accordee sur achat.* et public.articles3.")

        for table in config.tables_ecriture:
            conn.execute(
                text(f"GRANT SELECT, INSERT, UPDATE ON TABLE achat.{table} TO {config.role}")
            )
        logger.info(
            "[SUCCES] Ecriture accordee sur %s.",
            ", ".join(config.tables_ecriture),
        )

        # Les tables creees plus tard par l'ETL doivent etre lisibles elles aussi,
        # sinon une nouvelle table casse l'application sans que personne ne le voie.
        for proprietaire in conn.execute(
            text("SELECT DISTINCT tableowner FROM pg_tables WHERE schemaname = 'achat'")
        ).scalars():
            conn.execute(
                text(f'ALTER DEFAULT PRIVILEGES FOR ROLE "{proprietaire}" IN SCHEMA achat '
                     f"GRANT SELECT ON TABLES TO {config.role}")
            )
        logger.info("[SUCCES] Droits par defaut poses pour les futures tables.")

    with engine.connect() as conn:
        droits = conn.execute(text("""
            SELECT table_name, string_agg(privilege_type, ', ' ORDER BY privilege_type)
            FROM information_schema.table_privileges
            WHERE grantee = :r AND privilege_type IN ('INSERT', 'UPDATE', 'DELETE')
            GROUP BY table_name ORDER BY table_name
        """), {"r": config.role}).fetchall()
        lisibles = conn.execute(text("""
            SELECT count(DISTINCT table_name) FROM information_schema.table_privileges
            WHERE grantee = :r AND privilege_type = 'SELECT'
        """), {"r": config.role}).scalar()

    logger.info("[INFO] Tables lisibles : %s", lisibles)
    for table, privileges in droits:
        logger.info("[INFO] Ecriture : %-24s %s", table, privileges)


def main() -> None:
    """Point d'entree CLI."""
    setup_logging()
    parser = argparse.ArgumentParser(description="Compte de service PostgreSQL de l'API FUSEAU")
    parser.add_argument("--dry-run", action="store_true", help="Ne rien ecrire, verifier l'etat")
    args = parser.parse_args()
    appliquer(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
