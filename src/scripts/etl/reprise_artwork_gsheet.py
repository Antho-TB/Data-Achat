# -*- coding: utf-8 -*-
"""
[ETL]
=============================================================================
REPRISE UNIQUE DES ARTWORKS DU GSHEET VERS achat.artwork
=============================================================================

Phase d'ecriture (docs/20261008_FUSEAU_Cadrage_PhaseEcriture_v1.md) : FUSEAU
devient la source des artworks. Ce script copie UNE FOIS le miroir du gsheet de
Clarisse (achat.artwork_statut, dernier chargement uniquement) dans la table
achat.artwork, saisie ensuite dans FUSEAU. Le gsheet passe alors en lecture
seule : pas de synchronisation dans les deux sens.

Regles de reprise :
- "En attente" devient en_attente, "Valide" devient valide ;
- identifiant : n° d'article + date (demande, sinon derniere version, sinon
  validation, sinon jour de la reprise), suffixe -2 si doublon ; les lignes
  sans reference ("NOUVEAU-...") prennent le prefixe NOUVEAU ;
- commentaires : acheteur (ex-Andrea, puis Maxence), design (Clarisse /
  Thomas), version (onglet Liste) ;
- chaque ligne reprise est tracee dans le journal (action "reprise").

Garde-fous : dry-run par defaut (tout est annule a la fin) ; refus si
achat.artwork contient deja des lignes, la reprise etant unique ; refus si le
miroir ne contient aucun artwork en attente (chargement du gsheet incomplet).

Usage :
    python -m src.scripts.etl.reprise_artwork_gsheet            # dry-run
    python -m src.scripts.etl.reprise_artwork_gsheet --commit   # reprise reelle
"""
from __future__ import annotations

import argparse
import logging
from collections import Counter
from datetime import date
from typing import Any, Optional

from sqlalchemy import text

from app.database import get_engine
from app.ecriture import creer, identifiant_artwork
from src.utils.logging_setup import setup_logging

logger = logging.getLogger(__name__)

AUTEUR = "reprise_gsheet"
STATUTS = {"en attente": "en_attente", "validé": "valide", "valide": "valide"}

SQL_SOURCE = """
    SELECT * FROM achat.artwork_statut
    WHERE charge_le >= (SELECT MAX(charge_le) FROM achat.artwork_statut) - INTERVAL '12 hours'
    ORDER BY code_article
"""


def convertir(ligne: dict[str, Any], identifiants: set[str], aujourdhui: date) -> dict[str, Any]:
    """
    Transforme une ligne du miroir du gsheet en artwork FUSEAU.

    Junior Tip : `identifiants` est mis a jour au fil de l'eau, pour que deux
    lignes du meme article et de la meme date recoivent bien -2, -3.
    """
    code = ligne.get("code_article") or ""
    sans_reference = code.upper().startswith("NOUVEAU-")
    code_article: Optional[str] = None if sans_reference else code
    jour = (ligne.get("date_demande") or ligne.get("derniere_version")
            or ligne.get("date_validation") or aujourdhui)
    identifiant = identifiant_artwork(code_article, jour, identifiants)
    identifiants.add(identifiant)
    statut = STATUTS.get(str(ligne.get("statut_artwork") or "").strip().lower(), "en_attente")
    return {
        "identifiant": identifiant,
        "code_article": code_article,
        "designation": ligne.get("designation") or code,
        "statut": statut,
        "priorite": ligne.get("priorite"),
        "valideur": ligne.get("valideur"),
        "commentaire_acheteur": ligne.get("commentaire_andrea"),
        "commentaire_design": ligne.get("commentaire_clarisse_thomas"),
        "commentaire_version": ligne.get("commentaire"),
        "date_demande": ligne.get("date_demande"),
        "date_derniere_version": ligne.get("derniere_version"),
        "valide_le": ligne.get("date_validation") if statut == "valide" else None,
        "valide_par": ligne.get("valideur") if statut == "valide" else None,
        "cree_par": AUTEUR,
        "maj_par": AUTEUR,
        "origine": "reprise_gsheet",
    }


def reprendre(commit: bool, accepter_sans_attente: bool = False) -> dict[str, int]:
    """
    Reprend le miroir du gsheet dans achat.artwork.

    Returns:
        Compteurs {"lues", "reprises", "en_attente", "valide"}.

    Raises:
        RuntimeError: si achat.artwork n'est pas vide (reprise deja faite).
    """
    engine = get_engine()
    with engine.begin() as conn:
        deja = conn.execute(text("SELECT COUNT(*) FROM achat.artwork")).scalar() or 0
        if deja:
            raise RuntimeError(
                f"achat.artwork contient deja {deja} artwork(s) : la reprise est unique. "
                "Rien n'a ete ecrit.")
        source = [dict(r) for r in conn.execute(text(SQL_SOURCE)).mappings()]
        nb_attente = sum(1 for l in source
                         if str(l.get("statut_artwork") or "").strip().lower() == "en attente")
        if nb_attente == 0 and not accepter_sans_attente:
            # Constate le 08/10/2026 : le poste chargeait encore le gsheet avec un
            # parseur qui ignorait l'onglet "en attente". Reprendre a ce moment-la
            # aurait perdu les artworks en cours, alors que le gsheet est ensuite fige.
            raise RuntimeError(
                "Le miroir du gsheet ne contient aucun artwork en attente : chargement "
                "incomplet probable. Relancer FUSEAU_Daily_ETL sur le poste, puis reprendre. "
                "Option --accepter-sans-attente pour passer outre. Rien n'a ete ecrit.")
        aujourdhui = date.today()
        identifiants: set[str] = set()
        artworks = [convertir(l, identifiants, aujourdhui) for l in source]
        for artwork in artworks:
            creer(conn, "artwork", artwork, AUTEUR, cle_col="identifiant", action="reprise")
        compte = Counter(a["statut"] for a in artworks)
        stats = {"lues": len(source), "reprises": len(artworks),
                 "en_attente": compte["en_attente"], "valide": compte["valide"]}
        for a in artworks[:5]:
            logger.info("[INFO] exemple : %s | %s | %s", a["identifiant"], a["statut"], a["designation"])
        if not commit:
            logger.info("[INFO] [DRY-RUN] %s : rien n'est ecrit (ROLLBACK).", stats)
            conn.rollback()
            return stats
    logger.info("[SUCCES] Reprise des artworks : %s", stats)
    return stats


def main() -> None:
    setup_logging()
    ap = argparse.ArgumentParser(description="Reprise unique des artworks du gsheet vers achat.artwork")
    ap.add_argument("--commit", action="store_true", help="Ecrit reellement (sinon dry-run).")
    ap.add_argument("--accepter-sans-attente", action="store_true",
                    help="Reprendre meme si aucun artwork en attente n'est present.")
    args = ap.parse_args()
    reprendre(commit=args.commit, accepter_sans_attente=args.accepter_sans_attente)


if __name__ == "__main__":
    main()
