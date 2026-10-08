# -*- coding: utf-8 -*-
"""
[TEST]
Facturation intersite des analyses qualite (SE <-> CIE).

Processus de Maxence BRUN (08/10/2026) : le BL qualite de CIE est compare a la
commande SE ; montants identiques = "a facturer" ; factures editees sur les deux
societes = "facturation faite". Son probleme reel : des BL CIE non remontes.
"""
from datetime import date

import pytest

from app.facturation_intersite import (
    STATUT_A_FACTURER,
    STATUT_ATTENTE_BL,
    STATUT_BL_MANQUANT,
    STATUT_ECART,
    STATUT_FACTUREE,
    decouper_reference,
    enrichir,
    sql_facturation,
    statut_facturation,
)

AUJOURDHUI = date(2026, 10, 8)


def _ca(**kw):
    base = {"ca": "00190050", "date_ca": date(2026, 9, 29), "reference": "00187132/BAT",
            "montant_ca": 68.36, "etat_facturation_se": "Non commencée",
            "bl": "00007441", "montant_bl": 68.36, "bl_factures": False}
    base.update(kw)
    return base


@pytest.mark.parametrize("reference, po, stade", [
    ("00187132/BAT", "187132", "BAT"),
    ("00176529/MAT", "176529", "MAT"),
    ("00183424/RECEPTION", "183424", "RECEP"),
    ("SEMI PROD 00187132", "187132", "SP"),
    ("173654-177438 BAT", "173654", "BAT"),
    ("PLUSIEURS PO", None, None),
    (None, None, None),
])
def test_decouper_reference(reference, po, stade):
    assert decouper_reference(reference) == (po, stade)


def test_bl_recent_absent_est_en_attente():
    assert statut_facturation(_ca(bl=None, montant_bl=None), AUJOURDHUI) == STATUT_ATTENTE_BL


def test_bl_absent_depuis_plus_de_30_jours_est_signale():
    ligne = _ca(bl=None, montant_bl=None, date_ca=date(2026, 8, 1))
    assert statut_facturation(ligne, AUJOURDHUI) == STATUT_BL_MANQUANT


def test_ecart_de_montant():
    """Cas reel du 08/10 : CA POLYFLAME a 32,25, BL a 53,56."""
    assert statut_facturation(_ca(montant_ca=32.25, montant_bl=53.56), AUJOURDHUI) == STATUT_ECART


def test_arrondi_tolere():
    assert statut_facturation(_ca(montant_bl=68.359999), AUJOURDHUI) == STATUT_A_FACTURER


def test_facturee_seulement_si_les_deux_societes_ont_facture():
    assert statut_facturation(_ca(etat_facturation_se="Terminée", bl_factures=False),
                              AUJOURDHUI) == STATUT_A_FACTURER
    assert statut_facturation(_ca(etat_facturation_se="Terminée", bl_factures=True),
                              AUJOURDHUI) == STATUT_FACTUREE


def test_enrichir_ajoute_po_stade_statut_et_ecart():
    ligne = enrichir([_ca(montant_bl=70.0)], AUJOURDHUI)[0]
    assert (ligne["po_number"], ligne["stade"], ligne["statut"]) == ("187132", "BAT", STATUT_ECART)
    assert ligne["ecart_montant"] == 1.64


def test_rapprochement_par_ligne_et_non_par_montant():
    """Une reference PO/STADE porte plusieurs CA et plusieurs BL : seule la
    chaine des lignes de vente relie un BL a sa CA."""
    sql = sql_facturation()
    assert "ligne_id_lignecommandevente" in sql
    assert "commande_identifiant_edi" in sql
    assert ":depuis" in sql
