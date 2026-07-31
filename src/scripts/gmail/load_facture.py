# -*- coding: utf-8 -*-
"""
[GMAIL]
=============================================================================
INGESTION DES MONTANTS DE FACTURE FOURNISSEUR -> achat.facture_fournisseur
=============================================================================

Charge en base les pieces comptables extraites des pieces jointes Gmail par
parse_facture.py, et rapproche chaque montant de celui du fichier IMPORT.

POURQUOI CE MODULE
Marlene a paye le 29/07 sur un montant que FUSEAU presentait comme venant de la
facture recue par mail alors qu'il venait du fichier IMPORT. Ce module apporte
enfin le chiffre du document. Il ne remplace PAS celui de l'IMPORT : les deux
cohabitent, et c'est l'ECART entre eux qui a une valeur metier. Un ecart
signifie qu'une des deux sources se trompe, et c'est a l'acheteuse de trancher,
pas au code.

STRATEGIE D'ECRITURE
Table dediee achat.facture_fournisseur, jamais achat.commande : celle-ci est
rechargee en full-refresh chaque nuit (TRUNCATE + INSERT), un montant ecrit
dedans serait detruit. Le grain est la piece comptable, pas la ligne article :
une facture couvre souvent plusieurs PO et une note de credit n'appartient a
aucune ligne en particulier.

IDEMPOTENCE
Cle (n_facture, source_fichier). Relire deux fois la meme PJ met la ligne a
jour, n'en cree pas une seconde. Le fichier source fait partie de la cle parce
que deux fournisseurs peuvent emettre le meme numero de facture, et qu'une
facture corrigee arrive dans une autre piece jointe.

Usage :
    python -m src.scripts.gmail.load_facture --folder data/PJ [--dry-run]
    python -m src.scripts.gmail.load_facture --file data/_factures.json
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

from sqlalchemy import text

from app.database import get_engine
from src.scripts.gmail.parse_facture import parse_dossier
from src.utils.config_manager import Config
from src.utils.logging_setup import setup_logging

logger = logging.getLogger(__name__)

SCHEMA = "achat"

# Une piece dont le numero n'a pas pu etre lu garde quand meme son montant : le
# fichier source suffit a la retrouver et a la dedoublonner. Une reference
# explicitement marquee vaut mieux qu'une chaine vide, qui se lirait comme un
# numero reel dans l'interface.
REF_ABSENTE = "REF-ILLISIBLE"

SQL_UPSERT = f"""
    INSERT INTO {SCHEMA}.facture_fournisseur
        (n_facture, fournisseur, type_piece, date_piece, montant, montant_ht,
         devise, po_numbers, n_conteneur, n_bl, source_fichier,
         methode_extraction, confiance, texte_source, charge_le)
    VALUES
        (:n_facture, :fournisseur, :type_piece, :date_piece, :montant,
         :montant_ht, :devise, :po_numbers, :n_conteneur, :n_bl,
         :source_fichier, :methode_extraction, :confiance, :texte_source, NOW())
    ON CONFLICT (n_facture, source_fichier) DO UPDATE
    SET fournisseur        = COALESCE(EXCLUDED.fournisseur, {SCHEMA}.facture_fournisseur.fournisseur),
        type_piece         = EXCLUDED.type_piece,
        date_piece         = COALESCE(EXCLUDED.date_piece, {SCHEMA}.facture_fournisseur.date_piece),
        montant            = EXCLUDED.montant,
        montant_ht         = EXCLUDED.montant_ht,
        devise             = COALESCE(EXCLUDED.devise, {SCHEMA}.facture_fournisseur.devise),
        po_numbers         = COALESCE(EXCLUDED.po_numbers, {SCHEMA}.facture_fournisseur.po_numbers),
        n_conteneur        = COALESCE(EXCLUDED.n_conteneur, {SCHEMA}.facture_fournisseur.n_conteneur),
        n_bl               = COALESCE(EXCLUDED.n_bl, {SCHEMA}.facture_fournisseur.n_bl),
        methode_extraction = EXCLUDED.methode_extraction,
        confiance          = EXCLUDED.confiance,
        texte_source       = EXCLUDED.texte_source,
        charge_le          = NOW()
    WHERE {SCHEMA}.facture_fournisseur.valide_par IS NULL
"""

# Montant du fichier IMPORT pour les PO cites par la piece, afin de mesurer
# l'ecart. Meme formule que partout ailleurs dans le projet : le total par PO
# quand la ligne n'a pas de code article, sinon prix unitaire x quantite.
SQL_MONTANT_IMPORT = f"""
    SELECT ROUND(SUM(CASE WHEN code_article IS NULL THEN COALESCE(total_prix, 0)
                          ELSE COALESCE(prix_unitaire * quantite, 0) END), 2) AS montant
    FROM {SCHEMA}.commande
    WHERE po_number = ANY(:pos) AND statut <> 'Annulée'
"""


def _ecart_relatif(montant_piece: float, montant_import: float) -> float:
    """Ecart relatif entre les deux sources, 0 si l'IMPORT ne dit rien."""
    if not montant_import:
        return 0.0
    return abs(abs(montant_piece) - abs(montant_import)) / abs(montant_import)


def _controler_ecart(conn: Any, piece: dict[str, Any]) -> None:
    """
    Compare le montant de la piece a celui du fichier IMPORT et loggue l'ecart.

    Junior Tip : on ne corrige rien ici, et surtout on n'ecarte pas la piece.
    Un ecart n'est pas une erreur d'extraction, c'est une information metier :
    c'est exactement ce que Marlene cherchait le 29/07 quand elle a vu 6 403,20
    EUR sur sa facture HONGXING et autre chose a l'ecran. Le role du code est de
    le rendre visible, pas de choisir un gagnant.
    """
    montant = piece.get("montant")
    pos = piece.get("po_numbers")
    if montant is None or not pos:
        return
    ligne = conn.execute(text(SQL_MONTANT_IMPORT), {"pos": list(pos)}).mappings().first()
    montant_import = float(ligne["montant"]) if ligne and ligne["montant"] else 0.0
    if not montant_import:
        logger.warning("[ATTENTION] %s : aucun montant IMPORT pour les PO %s, "
                       "le chiffre de la piece n'est corrobore par rien.",
                       piece["source_fichier"], ",".join(pos))
        return
    ecart = _ecart_relatif(float(montant), montant_import)
    if ecart > Config.SEUIL_ECART_FACTURE:
        logger.warning("[ATTENTION] %s : ecart de %.1f %% entre la piece "
                       "(%.2f %s) et le fichier IMPORT (%.2f). A trancher par "
                       "les Achats avant paiement.",
                       piece["source_fichier"], ecart * 100, float(montant),
                       piece.get("devise") or "?", montant_import)
    else:
        logger.info("[INFO] %s : piece et IMPORT concordent (ecart %.2f %%).",
                    piece["source_fichier"], ecart * 100)


def charger(pieces: list[dict[str, Any]], dry_run: bool = False) -> int:
    """
    Insere ou met a jour les pieces comptables en base.

    Une piece deja validee par un humain (valide_par renseigne) n'est jamais
    ecrasee par une relecture automatique : la validation est le dernier mot.

    Args:
        pieces: sorties de parse_facture, deja normalisees.
        dry_run: n'ecrit rien, se contente de journaliser.
    Returns:
        Nombre de pieces ecrites.
    """
    if not pieces:
        logger.info("[INFO] Aucune piece comptable a charger.")
        return 0

    engine = get_engine()
    ecrites = 0
    with engine.begin() as conn:
        for piece in pieces:
            if piece.get("montant") is None:
                logger.warning("[ATTENTION] %s : aucun montant lisible, piece "
                               "chargee pour memoire mais inexploitable en paiement.",
                               piece["source_fichier"])
            if not piece.get("n_facture"):
                logger.warning("[ATTENTION] %s : numero de piece illisible, "
                               "reference forcee a %s.",
                               piece["source_fichier"], REF_ABSENTE)
                piece["n_facture"] = REF_ABSENTE
            if piece.get("confiance", 0) < Config.SEUIL_CONFIANCE_FACTURE:
                logger.warning("[ATTENTION] %s : confiance %.2f, la piece devra "
                               "etre validee a la main avant tout paiement.",
                               piece["source_fichier"], piece.get("confiance", 0))

            _controler_ecart(conn, piece)

            if dry_run:
                logger.info("[INFO] (dry-run) %s : %s %s %s",
                            piece["source_fichier"], piece["type_piece"],
                            piece["montant"], piece.get("devise"))
                continue

            parametres = {cle: piece.get(cle) for cle in (
                "n_facture", "fournisseur", "type_piece", "date_piece", "montant",
                "montant_ht", "devise", "po_numbers", "n_conteneur", "n_bl",
                "source_fichier", "methode_extraction", "confiance", "texte_source")}
            conn.execute(text(SQL_UPSERT), parametres)
            ecrites += 1

    logger.info("[SUCCES] %d piece(s) comptable(s) %s.", ecrites,
                "analysee(s) en dry-run" if dry_run else "chargee(s) en base")
    return ecrites


def main() -> int:
    setup_logging()
    ap = argparse.ArgumentParser(
        description="Charge les montants de facture dans achat.facture_fournisseur.")
    ap.add_argument("--folder", type=str,
                    help="Dossier de pieces jointes a analyser puis charger.")
    ap.add_argument("--file", type=str,
                    help="JSON deja produit par parse_facture (--out).")
    ap.add_argument("--dry-run", action="store_true",
                    help="Analyse et journalise sans ecrire en base.")
    args = ap.parse_args()

    if args.folder:
        pieces = parse_dossier(Path(args.folder))
    elif args.file:
        pieces = json.loads(Path(args.file).read_text(encoding="utf-8"))
    else:
        ap.error("Fournir --folder ou --file.")
        return 2

    charger(pieces, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
