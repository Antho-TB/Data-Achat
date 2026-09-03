# -*- coding: utf-8 -*-
"""
[ETL]
=============================================================================
HISTORIQUE PRIX SYLOB - REPLI SANS LIMITE DE DATE
=============================================================================

Alimente achat.historique_prix_sylob depuis le DWH Sylob (tarrerias_production_dwh).

Besoin metier (mail Marlene MONTBRIZON du 03/09/2026) : l'onglet Article ne sort
les 3 derniers prix que depuis achat.commande, alimente par IMPORT 2026.xlsx, qui
ne couvre que juin 2024 a aujourd'hui. Sur 1 199 articles du referentiel, 788
n'ont aucun prix. Les commandes fournisseur Sylob couvrent 2013 a aujourd'hui et
retrouvent un prix pour environ 566 de ces articles : c'est le repli demande,
"les 3 derniers prix quelle que soit la date".

Perimetre : les 3 societes (GDD, SE, Cie), tous fournisseurs confondus, un
classement global par article (le plus recent gagne, la societe n'entre pas dans
le tri). Lecture seule cote Sylob.

Politique de chargement : full-refresh. La table est purement derivee, aucune
saisie utilisateur n'y vit, donc rien a reprojeter (contrairement a
achat.commande_enrichissement). Un garde-fou de volume refuse le rechargement si
la moisson est anormalement maigre, pour ne pas remplacer un historique complet
par le resultat d'un DWH a moitie repondu.

Usage : python -m src.scripts.etl.enrich_historique_prix_sylob [--dry-run]
"""
from __future__ import annotations

import argparse
import logging
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from src.utils.config_manager import Config

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

SCHEMAS: dict[str, str] = {
    "GDD": "TARRERIAS_GENERALE_DE_DECOUPAGE_Achat",
    "SE": "TARRERIAS_SE_TARRERIAS_BONJEAN_Achat",
    "Cie": "TARRERIAS_TARRERIAS_BONJEAN_ET_CIE_Achat",
}

# Prix conserves par article et par societe cote Sylob. On en tire plus que les 3
# finaux : le classement definitif est global, il faut donc de la marge avant de
# fusionner les societes.
PRIX_PAR_SOCIETE = 5

# Prix finalement exposes par article, toutes societes confondues (demande metier).
PRIX_PAR_ARTICLE = 3

# Plancher de volume : sous cette fraction du contenu actuel, on refuse d'ecraser.
SEUIL_VOLUME_MIN = 0.5

SQL_SYLOB = """
    SELECT code_article, designation, fournisseur, po_number, date_commande,
           prix_unitaire, prix_unitaire_eur, quantite, unite
    FROM (
        SELECT article_code_article                     AS code_article,
               article_designation                      AS designation,
               frn_raison_sociale                       AS fournisseur,
               commande_numero_de_la_commande           AS po_number,
               commande_creee_le                        AS date_commande,
               ligne_prix_unitaire_ht                   AS prix_unitaire,
               ligne_prix_unitaire_ht_devise_societe    AS prix_unitaire_eur,
               ligne_quantite                           AS quantite,
               ligne_unite_quantite                     AS unite,
               ROW_NUMBER() OVER (
                   PARTITION BY article_code_article
                   ORDER BY commande_creee_le DESC NULLS LAST
               )                                        AS rn
        FROM "{schema}".vue_commande_achat_detail
        WHERE ligne_prix_unitaire_ht > 0
          AND article_code_article IS NOT NULL
          -- Le schema SE porte des commandes datees jusqu'en 2027 : une date de
          -- creation dans le futur est une anomalie de saisie, et elle prendrait
          -- la tete du classement "dernier prix". On l'ecarte.
          AND commande_creee_le <= CURRENT_DATE
    ) t
    WHERE rn <= :n
"""


def _fetch_societe(conn: Any, societe: str, schema: str) -> list[dict[str, Any]]:
    """
    Lit les derniers prix d'achat d'une societe Sylob.

    Junior Tip : le classement se fait cote serveur avec ROW_NUMBER plutot qu'en
    ramenant les 40 000 lignes de la vue pour trier en Python. La vue
    vue_commande_achat_detail fait 559 colonnes, on n'en projette que neuf.

    Args:
        conn: Connexion SQLAlchemy ouverte sur tarrerias_production_dwh.
        societe: Code court de la societe (GDD, SE, Cie).
        schema: Nom du schema Sylob correspondant.
    Returns:
        Liste de lignes de prix, societe renseignee.
    """
    rows = conn.execute(
        text(SQL_SYLOB.format(schema=schema)), {"n": PRIX_PAR_SOCIETE}
    ).mappings().all()
    logger.info("[INFO] %s : %d lignes de prix candidates", societe, len(rows))
    return [{**dict(r), "societe": societe} for r in rows]


def _classer(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Fusionne les societes et garde les N derniers prix par code article.

    Junior Tip : un meme code article est achete dans plusieurs societes, avec
    des numeros de commande independants. Le tri doit donc etre global (date
    decroissante toutes societes confondues), sinon on afficherait le dernier
    prix de chaque societe au lieu des derniers prix reels.

    Args:
        rows: Lignes brutes des trois societes.
    Returns:
        Lignes retenues, champ `rang` renseigne (1 = le plus recent).
    """
    par_article: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        par_article.setdefault(str(r["code_article"]).strip(), []).append(r)

    retenues: list[dict[str, Any]] = []
    for code, lignes in par_article.items():
        lignes.sort(key=lambda x: (x["date_commande"] is not None, x["date_commande"]), reverse=True)
        for rang, ligne in enumerate(lignes[:PRIX_PAR_ARTICLE], start=1):
            prix = ligne["prix_unitaire"]
            prix_eur = ligne["prix_unitaire_eur"]
            retenues.append({
                "code_article": code,
                "designation": ligne["designation"],
                "fournisseur": ligne["fournisseur"],
                "po_number": str(ligne["po_number"]).strip() if ligne["po_number"] else None,
                "societe": ligne["societe"],
                "date_commande": ligne["date_commande"],
                "prix_unitaire": prix,
                "prix_unitaire_eur": prix_eur,
                # Sylob n'expose pas le code devise dans cette vue. Un ecart entre
                # prix document et prix societe signe un achat en devise etrangere :
                # l'interface doit alors s'abstenir d'afficher un symbole euro.
                "devise_etrangere": bool(
                    prix is not None and prix_eur is not None and prix != prix_eur
                ),
                "quantite": ligne["quantite"],
                "unite": ligne["unite"],
                "rang": rang,
            })
    logger.info(
        "[INFO] %d articles distincts, %d lignes retenues (max %d par article)",
        len(par_article), len(retenues), PRIX_PAR_ARTICLE,
    )
    return retenues


def _charger(pg: Engine, rows: list[dict[str, Any]]) -> int:
    """
    Recharge achat.historique_prix_sylob en full-refresh, garde-fou de volume inclus.

    Junior Tip : le staging passe par une table `_tmp_` dans le schema achat et non
    par une table TEMP, le compte applicatif n'ayant pas le droit CREATE TEMP en
    production (meme contrainte que enrich_acompte).

    Args:
        pg: Moteur PostgreSQL Azure (schema achat).
        rows: Lignes a charger.
    Returns:
        Nombre de lignes chargees.
    """
    import pandas as pd

    with pg.connect() as c:
        actuel = c.execute(text("SELECT COUNT(*) FROM achat.historique_prix_sylob")).scalar() or 0

    if actuel and len(rows) < actuel * SEUIL_VOLUME_MIN:
        raise RuntimeError(
            f"Moisson anormalement maigre : {len(rows)} lignes contre {actuel} en base "
            f"(plancher {SEUIL_VOLUME_MIN:.0%}). Rechargement refuse, verifier l'acces au DWH Sylob."
        )

    df = pd.DataFrame(rows)
    with pg.begin() as c:
        df.to_sql("_tmp_historique_prix_sylob", c, schema="achat",
                  if_exists="replace", index=False, method="multi", chunksize=1000)
        c.execute(text("TRUNCATE TABLE achat.historique_prix_sylob;"))
        c.execute(text("""
            INSERT INTO achat.historique_prix_sylob
                (code_article, designation, fournisseur, po_number, societe, date_commande,
                 prix_unitaire, prix_unitaire_eur, devise_etrangere, quantite, unite, rang)
            SELECT code_article, designation, fournisseur, po_number, societe,
                   NULLIF(date_commande::text, '')::date,
                   NULLIF(prix_unitaire::text, '')::numeric,
                   NULLIF(prix_unitaire_eur::text, '')::numeric,
                   COALESCE(devise_etrangere, FALSE),
                   NULLIF(quantite::text, '')::numeric,
                   unite, rang::smallint
            FROM achat._tmp_historique_prix_sylob;
        """))
        c.execute(text("DROP TABLE IF EXISTS achat._tmp_historique_prix_sylob;"))
    return len(rows)


def enrich_historique_prix_sylob(dry_run: bool = False) -> dict[str, int]:
    """
    Reconstruit le repli prix hors perimetre Import depuis les 3 societes Sylob.

    Args:
        dry_run: True pour mesurer sans ecrire en base.
    Returns:
        Statistiques {lignes_sylob, lignes_retenues, lignes_chargees}.
    """
    sy = create_engine(Config.get_sylob_url())
    brutes: list[dict[str, Any]] = []
    with sy.connect() as c:
        for societe, schema in SCHEMAS.items():
            brutes.extend(_fetch_societe(c, societe, schema))

    if not brutes:
        # Une source tierce muette n'est pas un resultat vide : sans cette levee,
        # le full-refresh viderait la table de repli sans que personne ne le voie.
        raise RuntimeError(
            "Aucune ligne de prix remontee par le DWH Sylob : acces reseau ou vue indisponible."
        )

    retenues = _classer(brutes)

    if dry_run:
        logger.info("[INFO] DRY-RUN : %d lignes pretes, aucune ecriture", len(retenues))
        return {"lignes_sylob": len(brutes), "lignes_retenues": len(retenues), "lignes_chargees": 0}

    pg = create_engine(Config.get_pg_url())
    charges = _charger(pg, retenues)
    logger.info("[SUCCES] achat.historique_prix_sylob recharge : %d lignes", charges)
    return {"lignes_sylob": len(brutes), "lignes_retenues": len(retenues), "lignes_chargees": charges}


def main() -> None:
    """Point d'entree CLI."""
    parser = argparse.ArgumentParser(description="Repli prix d'achat depuis le DWH Sylob")
    parser.add_argument("--dry-run", action="store_true", help="Mesurer sans ecrire en base")
    args = parser.parse_args()
    try:
        enrich_historique_prix_sylob(dry_run=args.dry_run)
    except Exception as exc:
        logger.error("[ECHEC] Enrichissement historique prix Sylob : %s", exc, exc_info=True)
        raise


if __name__ == "__main__":
    main()