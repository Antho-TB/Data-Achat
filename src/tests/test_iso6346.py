# -*- coding: utf-8 -*-
"""
[TEST] Discrimination conteneur ISO 6346 contre numéro de BL transitaire.

Régression du 28/07/2026 : 27 lignes sur 173 de achat.ot_transport portaient un
numéro de BL en guise de numéro de conteneur. Les deux références ont la même
forme apparente (4 lettres + 7 chiffres), la seule différence tient à la 4e
lettre, qui vaut toujours U, J ou Z sur un conteneur normalisé.
"""
import pytest

from src.scripts.etl.transform_maritime import RE_CONTAINER as RE_MARITIME
from src.scripts.gmail.parse_bl import RE_CONTAINER as RE_BL
from src.scripts.gmail.parse_email_eta import RE_CONTAINER as RE_ETA

# Numéros réellement observés en base ou dans les noms de pièces jointes.
CONTENEURS_VALIDES = [
    "TEMU2613140", "ONEU4049406", "MSMU7221231", "TGBU2004021",
    "CMAU8355260", "YMMU6960921", "NYKU3773364", "MSNU2829027",
]
BL_A_REJETER = [
    "SZSE2604053", "SZAE2601690", "COMP0600002", "SZSE2603894",
    "SZSE2513755", "COMP1370029",
]


@pytest.mark.parametrize("regex", [RE_BL, RE_MARITIME, RE_ETA])
class TestDiscriminationConteneur:
    def test_reconnait_les_vrais_conteneurs(self, regex):
        for ref in CONTENEURS_VALIDES:
            assert regex.findall(ref) == [ref], f"{ref} devrait être reconnu"

    def test_rejette_les_numeros_de_bl(self, regex):
        for ref in BL_A_REJETER:
            assert regex.findall(ref) == [], f"{ref} est un BL, pas un conteneur"

    def test_nom_de_fichier_portant_les_deux_references(self, regex):
        """
        Cas réel : "PL-SZSE2603894-TEMU2613140.PDF". Le BL apparaît en premier
        et gagnait ; seul le conteneur doit désormais ressortir.
        """
        assert regex.findall("PL-SZSE2603894-TEMU2613140.PDF") == ["TEMU2613140"]

    def test_nom_de_fichier_sans_conteneur(self, regex):
        """Un BL seul ne doit produire aucun conteneur, pas un faux positif."""
        assert regex.findall("BL-SZSE2604053.PDF") == []
