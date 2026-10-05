# -*- coding: utf-8 -*-
"""
[ETL]
=============================================================================
RAPPROCHEMENT DES RECEPTIONS PHYSIQUES SYLOB, AU GRAIN LIGNE DE COMMANDE
=============================================================================

Sylob enregistre la date a laquelle la marchandise est physiquement entree au
depot. Le fichier IMPORT d'Andrea, lui, ne contient qu'une date de livraison
previsionnelle saisie a la main. Rapprocher les deux donne aux Achats la vraie
date d'arrivee, sans ressaisie.

Source (regle TB : l'ERP est la source de verite des que la donnee existe) :
  1. DWH Sylob, vue_reception_detail des 3 societes (GDD, SE, Cie). C'est la
     donnee ERP elle-meme, lue en direct depuis le poste qui fait tourner l'ETL.
  2. Repli si le DWH est injoignable : la copie MyReport
     public.receptions_detaillees4 dans dtpf_sylob_prod. Meme structure, meme
     volume (213 183 lignes contre 213 183 dans Sylob le 05/10/2026).

Historique : jusqu'au 05/10/2026 le module lisait public.receptions_detaillees2,
figee depuis le 04/08 par la refonte MyReport. Aucune erreur, juste des dates de
reception arretees deux mois en arriere. D'ou la lecture directe de Sylob, et le
garde-fou de fraicheur sur le repli.

Grain : (PO, code article). L'ancienne version agregeait par PO et marquait
"Livree" toutes les lignes d'une commande des qu'un seul article etait recu.
Les lignes PO-level ('' en code_article) deposees par l'ancienne version sont
neutralisees par sql/20261005_reception_grain_article.sql.

Strategie d'ecriture : on N'ECRIT PAS dans achat.commande, rechargee en
full-refresh (TRUNCATE + INSERT) chaque nuit. On depose l'information dans
achat.commande_enrichissement, et apply_enrichissement.py la reprojette sur
achat.commande et achat.qualite apres chaque chargement.

Junior Tip : les numeros de PO ne sont pas uniques entre les 3 societes Sylob
(le 18130 de GDD peut exister chez Cie), et achat.commande ne porte pas la
societe. On rapproche donc sur (PO, code article), puis on garde la commande
Sylob dont la date de creation est la plus proche de la date de commande du
fichier IMPORT. Au-dela de MAX_ECART_JOURS, c'est une homonymie : on rejette.

Usage :
    python -m src.scripts.etl.enrich_reception_sylob [--dry-run]
"""
from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from datetime import date

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection

from app.database import get_engine
from src.utils.config_manager import Config
from src.utils.logging_setup import setup_logging

logger = logging.getLogger(__name__)

SCHEMA = "achat"
SOURCE = "enrich_reception_sylob"

SCHEMAS_SYLOB: dict[str, str] = {
    "GDD": "TARRERIAS_GENERALE_DE_DECOUPAGE_Achat",
    "SE": "TARRERIAS_SE_TARRERIAS_BONJEAN_Achat",
    "CIE": "TARRERIAS_TARRERIAS_BONJEAN_ET_CIE_Achat",
}

# Ecart maximal tolere entre la creation de la commande dans Sylob et la date de
# commande du fichier IMPORT. Les saisies IMPORT decalent de quelques jours a
# quelques semaines ; une homonymie entre societes tombe a plusieurs annees.
MAX_ECART_JOURS = 180

# Au-dela, la copie MyReport est consideree figee : on refuse de s'en servir
# plutot que de reprojeter des receptions arretees (cas reel du 04/08 au 05/10).
MAX_AGE_REPLI_JOURS = 3

SQL_LIGNES_COMMANDE = f"""
    SELECT LTRIM(TRIM(po_number::text), '0') AS po,
           TRIM(code_article)                AS code_article,
           MIN(date_commande)                AS date_commande
    FROM {SCHEMA}.commande
    WHERE po_number IS NOT NULL AND code_article IS NOT NULL
    GROUP BY 1, 2
"""

# Les dates de reception posterieures a aujourd'hui existent dans Sylob (jusqu'en
# 2029 le 05/10/2026) : ce sont des erreurs de saisie, pas des receptions.
SQL_RECEPTIONS_SYLOB = """
    SELECT LTRIM(TRIM(commande_numero_de_la_commande), '0') AS po,
           TRIM(article_code_article)                       AS code_article,
           commande_creee_le                                AS creee_le,
           MAX(ligne_receptionnee_le)                       AS date_reception
    FROM "{schema}".vue_reception_detail
    WHERE ligne_receptionnee_le IS NOT NULL
      AND ligne_receptionnee_le <= CURRENT_DATE
      AND article_code_article IS NOT NULL
      AND LTRIM(TRIM(commande_numero_de_la_commande), '0') = ANY(:pos)
    GROUP BY 1, 2, 3
"""

SQL_RECEPTIONS_REPLI = """
    SELECT LTRIM(TRIM(commande_numero_de_la_commande), '0') AS po,
           TRIM(article_code_article)                       AS code_article,
           commande_creee_le                                AS creee_le,
           MAX(ligne_receptionnee_le)                       AS date_reception
    FROM public.receptions_detaillees4
    WHERE ligne_receptionnee_le IS NOT NULL
      AND ligne_receptionnee_le <= CURRENT_DATE
      AND article_code_article IS NOT NULL
      AND LTRIM(TRIM(commande_numero_de_la_commande), '0') = ANY(:pos)
    GROUP BY 1, 2, 3
"""

SQL_FRAICHEUR_REPLI = """
    SELECT CURRENT_DATE - MAX(ligne_date_modification_systeme)::date
    FROM public.receptions_detaillees4
"""

SQL_UPSERT = f"""
    INSERT INTO {SCHEMA}.commande_enrichissement
        (po_number, code_article, date_reception_sylob, source, maj_le)
    VALUES (:po_number, :code_article, :date_reception_sylob, :source, NOW())
    ON CONFLICT (po_number, code_article) DO UPDATE
    SET date_reception_sylob = EXCLUDED.date_reception_sylob,
        source              = EXCLUDED.source,
        maj_le              = NOW()
    WHERE {SCHEMA}.commande_enrichissement.date_reception_sylob
          IS DISTINCT FROM EXCLUDED.date_reception_sylob
"""


class RepliIndisponibleError(RuntimeError):
    """Sylob injoignable ET copie MyReport figee : aucune source fiable."""


@dataclass(frozen=True)
class Reception:
    """Une reception Sylob agregee au grain (PO, article, commande Sylob)."""

    po: str
    code_article: str
    creee_le: date | None
    date_reception: date


def _lire(conn: Connection, sql: str, pos: list[str]) -> list[Reception]:
    """Execute une requete de reception et la convertit en objets types."""
    return [Reception(**dict(r)) for r in conn.execute(text(sql), {"pos": pos}).mappings()]


def lire_receptions_sylob(pos: list[str]) -> list[Reception]:
    """
    Lit les receptions des 3 societes dans le DWH Sylob.

    Junior Tip : une societe qui echoue fait echouer l'ensemble. Rendre deux
    societes sur trois sans le dire laisserait des lignes "non recues" qui le
    sont en realite, ce qui est pire qu'un repli annonce.

    Raises:
        Exception: toute erreur de connexion ou de requete, captee par l'appelant.
    """
    engine = create_engine(Config.get_sylob_url(), connect_args={"connect_timeout": 15})
    receptions: list[Reception] = []
    with engine.connect() as conn:
        for societe, schema in SCHEMAS_SYLOB.items():
            lot = _lire(conn, SQL_RECEPTIONS_SYLOB.format(schema=schema), pos)
            logger.info("[INFO] Sylob %s : %d receptions (PO, article).", societe, len(lot))
            receptions.extend(lot)
    return receptions


def lire_receptions_repli(conn: Connection, pos: list[str]) -> list[Reception]:
    """
    Lit la copie MyReport, apres avoir verifie qu'elle n'est pas figee.

    Raises:
        RepliIndisponibleError: si la copie n'a pas bouge depuis MAX_AGE_REPLI_JOURS.
    """
    age = conn.execute(text(SQL_FRAICHEUR_REPLI)).scalar()
    if age is None or age > MAX_AGE_REPLI_JOURS:
        raise RepliIndisponibleError(
            f"public.receptions_detaillees4 non mise a jour depuis {age} jours "
            f"(seuil {MAX_AGE_REPLI_JOURS}). Table figee ou schema MyReport bascule.")
    return _lire(conn, SQL_RECEPTIONS_REPLI, pos)


def rapprocher(lignes: list[dict], receptions: list[Reception]) -> tuple[list[dict], int]:
    """
    Associe a chaque ligne de commande la reception Sylob de la bonne societe.

    Args:
        lignes: dicts {po, code_article, date_commande} issus d'achat.commande.
        receptions: receptions Sylob, toutes societes confondues.

    Returns:
        (enrichissements a ecrire, nombre d'homonymies rejetees).
    """
    par_cle: dict[tuple[str, str], list[Reception]] = {}
    for rec in receptions:
        par_cle.setdefault((rec.po, rec.code_article), []).append(rec)

    resultats: list[dict] = []
    rejets = 0
    for ligne in lignes:
        candidats = par_cle.get((ligne["po"], ligne["code_article"]), [])
        if not candidats:
            continue
        date_cmd: date | None = ligne.get("date_commande")
        if date_cmd is None:
            # Sans date de commande on ne peut pas departager : on n'accepte que
            # le cas sans ambiguite.
            retenu = candidats[0] if len({c.creee_le for c in candidats}) == 1 else None
        else:
            dates = [c for c in candidats if c.creee_le is not None]
            retenu = min(dates, key=lambda c: abs((c.creee_le - date_cmd).days), default=None)
            if retenu is not None and abs((retenu.creee_le - date_cmd).days) > MAX_ECART_JOURS:
                retenu = None
        if retenu is None:
            rejets += 1
            continue
        resultats.append({
            "po_number": ligne["po"],
            "code_article": ligne["code_article"],
            "date_reception_sylob": retenu.date_reception,
        })
    return resultats, rejets


def enrich_receptions_sylob(dry_run: bool = False) -> dict[str, int]:
    """
    Depose les dates de reception physique Sylob dans la table d'enrichissement.

    Args:
        dry_run: si True, compte les lignes sans rien ecrire en base.

    Returns:
        Compteurs {"receptions_lues", "lignes_rapprochees", "homonymies_rejetees",
        "enrichissements_ecrits"}.
    """
    engine = get_engine()
    with engine.begin() as conn:
        lignes = [dict(r) for r in conn.execute(text(SQL_LIGNES_COMMANDE)).mappings()]
        pos = sorted({ligne["po"] for ligne in lignes})
        logger.info("[INFO] %d lignes de commande (%d PO) a rapprocher.", len(lignes), len(pos))

        try:
            receptions = lire_receptions_sylob(pos)
            origine = "sylob"
        except RepliIndisponibleError:
            raise
        except Exception as exc:
            logger.warning("[ATTENTION] DWH Sylob injoignable (%s), repli sur la copie MyReport.",
                           str(exc).splitlines()[0])
            receptions = lire_receptions_repli(conn, pos)
            origine = "myreport"

        enrichissements, rejets = rapprocher(lignes, receptions)
        if rejets:
            logger.warning("[ATTENTION] %d ligne(s) ecartee(s) : PO homonyme dans une autre "
                           "societe Sylob (ecart de creation > %d j).", rejets, MAX_ECART_JOURS)
        stats = {
            "receptions_lues": len(receptions),
            "lignes_rapprochees": len(enrichissements),
            "homonymies_rejetees": rejets,
            "enrichissements_ecrits": 0,
        }
        if dry_run:
            logger.info("[INFO] [DRY-RUN] source=%s, %d lignes rapprochees, aucune ecriture.",
                        origine, len(enrichissements))
            return stats

        for enr in enrichissements:
            res = conn.execute(text(SQL_UPSERT), {**enr, "source": SOURCE})
            stats["enrichissements_ecrits"] += res.rowcount

    logger.info("[SUCCES] Receptions (%s) : %d lues, %d lignes rapprochees, %d ecritures.",
                origine, stats["receptions_lues"], stats["lignes_rapprochees"],
                stats["enrichissements_ecrits"])
    return stats


def main() -> None:
    setup_logging()
    ap = argparse.ArgumentParser(description="Rapproche les receptions physiques Sylob")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    enrich_receptions_sylob(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
