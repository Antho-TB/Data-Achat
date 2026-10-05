# -*- coding: utf-8 -*-
"""
[TEST]
Normalisation des statuts qualite par stade (BUG-007, lot 1).

L'IMPORT ne connait que Conforme / Non recu / Non conforme ; le metier lit
"en cours", "conforme", "FAIL". Un stade non applicable (Aucune, "/", vide) ne
doit jamais s'afficher comme un statut.
"""
import pytest

from app.main import (
    STATUT_CONFORME,
    STATUT_EN_COURS,
    STATUT_FAIL,
    STATUT_RECU,
    statut_stade,
)


@pytest.mark.parametrize("valeur, attendu", [
    ("Conforme", STATUT_CONFORME),
    ("Conforme couteau", STATUT_CONFORME),
    ("Validé", STATUT_CONFORME),
    ("OK", STATUT_CONFORME),
    ("Oui", STATUT_CONFORME),
    ("Non reçu", STATUT_EN_COURS),
    ("Analyse", STATUT_EN_COURS),
    ("Non conforme", STATUT_FAIL),
    ("FAIL", STATUT_FAIL),
    ("Receptionne Sylob", STATUT_RECU),
])
def test_valeurs_import(valeur, attendu):
    assert statut_stade(valeur) == attendu


@pytest.mark.parametrize("valeur", [None, "", "Aucune", "/", "-", "29105"])
def test_non_applicable_ne_devient_pas_un_statut(valeur):
    assert statut_stade(valeur) is None


def test_decision_mail_comble_un_import_vide():
    assert statut_stade(None, "non_conforme") == STATUT_FAIL
    assert statut_stade("Aucune", "conforme") == STATUT_CONFORME


def test_import_renseigne_prime_sur_la_decision_mail():
    """La decision mail s'affiche en infobulle, elle ne reecrit pas l'IMPORT."""
    assert statut_stade("Non reçu", "conforme") == STATUT_EN_COURS
