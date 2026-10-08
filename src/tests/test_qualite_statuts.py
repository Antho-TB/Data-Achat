# -*- coding: utf-8 -*-
"""
[TEST]
Normalisation des statuts qualite par stade (BUG-007).

Regles de Maxence BRUN (08/10/2026) : "Non recu" = echantillons attendus du
fournisseur ; un echec est "non conforme" ; les decisions mail ne font pas foi
et ne doivent jamais fabriquer un statut. Un stade non applicable (Aucune, "/",
vide) ne doit jamais s'afficher comme un statut.
"""
import inspect

import pytest

from app.main import (
    STADES_QUALITE,
    STATUT_CONFORME,
    STATUT_EN_ANALYSE,
    STATUT_FAIL,
    STATUT_NON_RECU,
    STATUT_RECU,
    statut_stade,
)


@pytest.mark.parametrize("valeur, attendu", [
    ("Conforme", STATUT_CONFORME),
    ("Conforme couteau", STATUT_CONFORME),
    ("Validé", STATUT_CONFORME),
    ("OK", STATUT_CONFORME),
    ("Oui", STATUT_CONFORME),
    ("Non reçu", STATUT_NON_RECU),
    ("Analyse", STATUT_EN_ANALYSE),
    ("Non conforme", STATUT_FAIL),
    ("FAIL", STATUT_FAIL),
    ("No OK", STATUT_FAIL),
    ("Receptionne Sylob", STATUT_RECU),
])
def test_valeurs_import(valeur, attendu):
    assert statut_stade(valeur) == attendu


@pytest.mark.parametrize("valeur", [None, "", "Aucune", "/", "-", "29105"])
def test_non_applicable_ne_devient_pas_un_statut(valeur):
    assert statut_stade(valeur) is None


def test_decision_mail_ne_fabrique_plus_de_statut():
    """Maxence, 08/10 : les decisions mail ne font pas foi."""
    assert list(inspect.signature(statut_stade).parameters) == ["valeur"]


def test_cinq_stades_dont_echantillon_de_conformite():
    assert set(STADES_QUALITE) == {"MAT", "SP", "BAT", "RECEP", "ECH"}
    assert STADES_QUALITE["ECH"] == "echantillon_conformite"
