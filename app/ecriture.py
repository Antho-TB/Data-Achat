# -*- coding: utf-8 -*-
"""
[API]
=============================================================================
SOCLE D'ECRITURE FUSEAU : CREATION, MODIFICATION VERSIONNEE, JOURNAL
=============================================================================

Phase d'ecriture (cadrage docs/20261008_FUSEAU_Cadrage_PhaseEcriture_v1.md) :
FUSEAU devient la source des donnees hors ERP aujourd'hui tenues dans des
gsheets. Ce module porte les regles communes a tous les domaines :

- chaque ecriture est tracee dans achat.journal_modification (qui, quand,
  valeurs avant et apres) ;
- une modification envoie la version qu'elle a lue ; si quelqu'un a enregistre
  entre-temps, elle est refusee (ConflitVersion, HTTP 409) au lieu d'ecraser le
  travail de l'autre en silence ;
- pas de suppression : on archive.

Les noms de tables et de colonnes viennent du code, jamais de la requete HTTP :
ils sont verifies contre une liste blanche avant d'entrer dans le SQL.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date
from typing import Any, Iterable, Optional

from sqlalchemy import text
from sqlalchemy.engine import Connection

from src.utils.config_manager import Config

logger = logging.getLogger(__name__)

SCHEMA = Config.PG_SCHEMA
TABLES_ECRITURE = frozenset({"artwork_fuseau", "analyse_suivi", "facturation_intersite_suivi"})
_RE_IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")


class ConflitVersion(Exception):
    """La ligne a ete modifiee par quelqu'un d'autre depuis sa lecture."""

    def __init__(self, actuelle: dict[str, Any]) -> None:
        super().__init__("Ligne modifiee entre-temps")
        self.actuelle = actuelle


class LigneIntrouvable(Exception):
    """La ligne visee n'existe pas."""


def _ident(nom: str) -> str:
    """Valide un nom de colonne ou de table avant de l'inserer dans le SQL."""
    if not _RE_IDENT.match(nom):
        raise ValueError(f"Identifiant SQL refuse : {nom!r}")
    return nom


def _table(nom: str) -> str:
    if nom not in TABLES_ECRITURE:
        raise ValueError(f"Table non ouverte a l'ecriture : {nom!r}")
    return f"{SCHEMA}.{_ident(nom)}"


def _json(valeur: Optional[dict[str, Any]]) -> Optional[str]:
    return None if valeur is None else json.dumps(valeur, default=str, ensure_ascii=False)


def identifiant_artwork(code_article: Optional[str], jour: date, existants: Iterable[str]) -> str:
    """
    Identifiant lisible d'un artwork : n° d'article et date de creation
    concatenes, valide par Clarisse le 08/10/2026.

    Junior Tip : la date est celle de la CREATION et l'identifiant ne change
    plus jamais ensuite, meme si une date est corrigee : un identifiant qui
    bouge casse tous les liens qui le citent. Deux artworks du meme article
    crees le meme jour sont departages par un suffixe -2, -3...

    Args:
        code_article: reference de l'article, None tant qu'elle n'existe pas
            (artwork "PAS DE REF" : prefixe NOUVEAU).
        jour: date de creation de l'artwork.
        existants: identifiants deja attribues, pour eviter les doublons.

    Returns:
        Identifiant unique, par exemple 32030006-20261008 ou 32030006-20261008-2.
    """
    base = f"{(code_article or 'NOUVEAU').strip().upper()}-{jour:%Y%m%d}"
    pris = set(existants)
    if base not in pris:
        return base
    rang = 2
    while f"{base}-{rang}" in pris:
        rang += 1
    return f"{base}-{rang}"


def journaliser(conn: Connection, table: str, cle: str, action: str,
                avant: Optional[dict[str, Any]], apres: Optional[dict[str, Any]], auteur: str) -> None:
    """Ajoute une ligne au journal des modifications, dans la meme transaction."""
    conn.execute(text(f"""
        INSERT INTO {SCHEMA}.journal_modification (table_cible, cle, action, avant, apres, auteur)
        VALUES (:table, :cle, :action, CAST(:avant AS jsonb), CAST(:apres AS jsonb), :auteur)
    """), {"table": table, "cle": cle, "action": action,
           "avant": _json(avant), "apres": _json(apres), "auteur": auteur})


def creer(conn: Connection, table: str, valeurs: dict[str, Any], auteur: str,
          cle_col: str, action: str = "creation") -> dict[str, Any]:
    """
    Insere une ligne, renseigne auteur et dates, et la trace dans le journal.

    Returns:
        La ligne creee, telle que relue en base.
    """
    cols = {_ident(k): v for k, v in valeurs.items()}
    noms = list(cols)
    ligne = conn.execute(text(f"""
        INSERT INTO {_table(table)} ({", ".join(noms)})
        VALUES ({", ".join(":" + n for n in noms)})
        RETURNING *
    """), cols).mappings().one()
    ligne = dict(ligne)
    journaliser(conn, table, str(ligne[_ident(cle_col)]), action, None, ligne, auteur)
    logger.info("[SUCCES] %s.%s cree par %s", table, ligne[cle_col], auteur)
    return ligne


def modifier(conn: Connection, table: str, cle_col: str, cle: Any,
             changements: dict[str, Any], version_attendue: int, auteur: str,
             champs_autorises: Iterable[str], action: str = "modification") -> dict[str, Any]:
    """
    Modifie une ligne si personne ne l'a changee depuis sa lecture.

    Junior Tip : la ligne est verrouillee (FOR UPDATE) le temps de comparer sa
    version et de l'ecrire. Sans verrou, deux enregistrements simultanes
    liraient la meme version et le second ecraserait le premier.

    Args:
        changements: champs a modifier ; ceux hors de champs_autorises sont
            refuses, ceux dont la valeur ne change pas sont ignores.
        version_attendue: version lue par l'utilisateur avant modification.

    Returns:
        La ligne apres modification (inchangee si aucun champ ne bouge).

    Raises:
        LigneIntrouvable: la cle n'existe pas.
        ConflitVersion: la ligne a ete modifiee entre-temps.
        ValueError: champ non autorise.
    """
    autorises = set(champs_autorises)
    refuses = set(changements) - autorises
    if refuses:
        raise ValueError(f"Champs non modifiables : {', '.join(sorted(refuses))}")

    actuelle = conn.execute(text(f"""
        SELECT * FROM {_table(table)} WHERE {_ident(cle_col)} = :cle FOR UPDATE
    """), {"cle": cle}).mappings().first()
    if actuelle is None:
        raise LigneIntrouvable(f"{table} {cle}")
    actuelle = dict(actuelle)
    if int(actuelle["version"]) != int(version_attendue):
        raise ConflitVersion(actuelle)

    utiles = {_ident(k): v for k, v in changements.items() if actuelle.get(k) != v}
    if not utiles:
        return actuelle

    sets = ", ".join(f"{k} = :{k}" for k in utiles)
    nouvelle = dict(conn.execute(text(f"""
        UPDATE {_table(table)}
        SET {sets}, maj_le = now(), maj_par = :_auteur, version = version + 1
        WHERE {_ident(cle_col)} = :_cle
        RETURNING *
    """), {**utiles, "_auteur": auteur, "_cle": cle}).mappings().one())

    journaliser(conn, table, str(cle), action,
                {k: actuelle.get(k) for k in utiles}, {k: nouvelle.get(k) for k in utiles}, auteur)
    logger.info("[SUCCES] %s.%s %s par %s (%s)", table, cle, action, auteur, ", ".join(utiles))
    return nouvelle


def historique(conn: Connection, table: str, cle: str, limite: int = 100) -> list[dict[str, Any]]:
    """Journal d'une ligne, du plus recent au plus ancien."""
    _table(table)
    return [dict(r) for r in conn.execute(text(f"""
        SELECT action, avant, apres, auteur, fait_le
        FROM {SCHEMA}.journal_modification
        WHERE table_cible = :table AND cle = :cle
        ORDER BY fait_le DESC, id DESC
        LIMIT :limite
    """), {"table": table, "cle": cle, "limite": limite}).mappings()]
