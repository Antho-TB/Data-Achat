# -*- coding: utf-8 -*-
"""
[API]
=============================================================================
SONDES DE FRAICHEUR DES SOURCES ET DE DROITS MYREPORT
=============================================================================

Le defaut le plus couteux du projet n'a jamais ete une erreur : c'est une table
qui cesse d'etre alimentee sans rien dire. public.receptions_detaillees2 est
restee figee du 04/08 au 05/10, achat.commande du 28/07 au 22/09, et l'API a
perdu chaque nuit son droit sur public.articles3 jusqu'au 06/10. Chaque fois,
l'interface affichait des chiffres plausibles et faux.

Ce module mesure, pour chaque source lue par FUSEAU, la date de derniere
alimentation et la compare a un seuil propre a son rythme (nocturne,
evenementiel). Il verifie aussi que le role applicatif garde son SELECT sur
les tables MyReport qu'il lit.

Junior Tip : on n'expose pas ce detail sur /api/health. Cette sonde est
publique (exclue de l'authentification Entra, pour le controle de deploiement)
et App Service l'interroge chaque minute : elle doit rester legere et ne rien
devoir reveler du modele de donnees. Le detail passe par /api/sante/sources,
derriere l'authentification.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import text

from src.utils.config_manager import Config

logger = logging.getLogger(__name__)

# Rythme nocturne : l'ETL du poste tourne a 02h et 07h. 48 h laissent passer
# un run rate isole sans alerter, pas deux.
SEUIL_NOCTURNE_HEURES = 48
# Rythme evenementiel : alimente par les mails (tache Cowork, lun-ven). Un
# week-end prolonge ne doit pas alerter, une semaine sans rien si.
SEUIL_EVENEMENTIEL_HEURES = 7 * 24


@dataclass(frozen=True)
class SondeFraicheur:
    """Une source a surveiller et la facon de dater sa derniere alimentation."""

    libelle: str
    table: str
    sql_derniere_maj: str
    seuil_heures: int


def _sonde_achat(libelle: str, table: str, colonne: str, seuil: int) -> SondeFraicheur:
    return SondeFraicheur(libelle, f"achat.{table}",
                          f"SELECT MAX({colonne}) FROM achat.{table}", seuil)


def _sonde_myreport(libelle: str, table: str) -> SondeFraicheur:
    """
    Les tables MyReport n'ont aucune colonne d'horodatage : l'ETL MyReport les
    supprime et les recree chaque nuit. On date donc la derniere analyse
    statistique, que PostgreSQL declenche apres chaque rechargement. Une table
    que MyReport n'alimente plus garde une date d'analyse ancienne : c'est
    exactement le cas de receptions_detaillees2 qu'on veut voir.
    """
    schema = Config.MYREPORT_SCHEMA
    sql = ("SELECT GREATEST(last_analyze, last_autoanalyze) FROM pg_stat_user_tables "
           f"WHERE schemaname = '{schema}' AND relname = '{table}'")
    return SondeFraicheur(libelle, f"{schema}.{table}", sql, SEUIL_NOCTURNE_HEURES)


# achat.commande_enrichissement n'est pas sondee : maj_le ne bouge que quand une
# date de reception change (ecriture protegee par IS DISTINCT FROM), sa date ne
# dit donc rien du dernier run. Sa source, receptions_detaillees4, l'est.
# achat.facture_fournisseur l'ajoutera une fois l'extraction des factures activee.
SONDES: tuple[SondeFraicheur, ...] = (
    _sonde_achat("Commandes (fichier IMPORT)", "commande", "updated_at", SEUIL_NOCTURNE_HEURES),
    _sonde_achat("Suivi maritime", "ot_transport", "charge_le", SEUIL_NOCTURNE_HEURES),
    _sonde_achat("BL du suivi maritime", "ot_transport_bl", "charge_le", SEUIL_NOCTURNE_HEURES),
    _sonde_achat("Qualite (fichier)", "qualite", "charge_le", SEUIL_NOCTURNE_HEURES),
    _sonde_achat("Historique de prix Sylob", "historique_prix_sylob", "charge_le",
                 SEUIL_NOCTURNE_HEURES),
    _sonde_achat("Artwork (gsheet Clarisse)", "artwork_statut", "charge_le", SEUIL_NOCTURNE_HEURES),
    _sonde_achat("Evenements transport (mails)", "transport_evenement", "created_at",
                 SEUIL_EVENEMENTIEL_HEURES),
    _sonde_achat("Decisions qualite (mails)", "qualite_decision", "created_at",
                 SEUIL_EVENEMENTIEL_HEURES),
    _sonde_myreport("Articles Sylob (MyReport)", "articles3"),
    _sonde_myreport("Commandes Sylob (MyReport)", Config.MYREPORT_TABLE_COMMANDES),
    _sonde_myreport("Receptions Sylob (MyReport)", "receptions_detaillees4"),
)

# Tables MyReport lues par l'API elle-meme : sans SELECT, la recherche article,
# les intitules de commande et les fiches NC basculent sur leurs replis.
TABLES_MYREPORT_LUES: tuple[str, ...] = (
    "articles3",
    Config.MYREPORT_TABLE_COMMANDES,
    Config.MYREPORT_TABLE_NCR,
)


def statut_fraicheur(derniere_maj: Optional[datetime], seuil_heures: int,
                     maintenant: datetime) -> tuple[str, Optional[float]]:
    """
    Classe une source selon l'age de sa derniere alimentation.

    Junior Tip : "vide" et "en_retard" sont distingues. Une table jamais
    alimentee n'appelle pas la meme action qu'une table qui s'est arretee.

    Returns:
        (statut parmi "ok", "en_retard", "vide" ; age en heures ou None).
    """
    if derniere_maj is None:
        return "vide", None
    if derniere_maj.tzinfo is None:
        # Colonnes "timestamp without time zone" : l'ETL ecrit en UTC.
        derniere_maj = derniere_maj.replace(tzinfo=timezone.utc)
    age = (maintenant - derniere_maj).total_seconds() / 3600
    return ("ok" if age <= seuil_heures else "en_retard"), round(age, 1)


def mesurer_sources(conn: Any) -> list[dict[str, Any]]:
    """
    Mesure la fraicheur de chaque source. Une sonde illisible n'empeche pas
    les autres : elle remonte en statut "illisible", jamais en "ok".
    """
    maintenant = datetime.now(timezone.utc)
    resultats: list[dict[str, Any]] = []
    for sonde in SONDES:
        try:
            with conn.begin_nested():
                derniere = conn.execute(text(sonde.sql_derniere_maj)).scalar()
            statut, age = statut_fraicheur(derniere, sonde.seuil_heures, maintenant)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[ATTENTION] Sonde %s illisible (%s)", sonde.table,
                           str(exc).splitlines()[0])
            derniere, statut, age = None, "illisible", None
        resultats.append({
            "source": sonde.libelle,
            "table": sonde.table,
            "derniere_maj": derniere.isoformat() if derniere else None,
            "age_heures": age,
            "seuil_heures": sonde.seuil_heures,
            "statut": statut,
        })
    return resultats


def verifier_droits_myreport(conn: Any) -> dict[str, bool]:
    """
    Verifie que le role connecte peut lire chaque table MyReport utilisee.

    Une table absente (renommee par MyReport, schema bascule) compte comme un
    droit manquant : dans les deux cas l'API passe sur ses replis.
    """
    schema = Config.MYREPORT_SCHEMA
    droits: dict[str, bool] = {}
    for table in TABLES_MYREPORT_LUES:
        nom = f"{schema}.{table}"
        try:
            with conn.begin_nested():
                droits[nom] = bool(conn.execute(
                    text("SELECT to_regclass(:t) IS NOT NULL "
                         "AND has_table_privilege(to_regclass(:t), 'SELECT')"),
                    {"t": nom}).scalar())
        except Exception as exc:  # noqa: BLE001
            logger.warning("[ATTENTION] Droit sur %s illisible (%s)", nom, str(exc).splitlines()[0])
            droits[nom] = False
    return droits


def journaliser_droits(droits: dict[str, bool]) -> None:
    """Log de demarrage : un droit manquant sort en ERROR pour etre vu."""
    manquants = [t for t, ok in droits.items() if not ok]
    if manquants:
        logger.error("[ECHEC] Le role applicatif ne lit pas %s : replis actifs "
                     "(recherche article, intitules, fiches NC).", ", ".join(manquants))
    else:
        logger.info("[SUCCES] Droits MyReport verifies : %s", ", ".join(droits))
