# -*- coding: utf-8 -*-
"""
[TEST]
Controle d'ecart des montants de facture : PO compares sans zeros de tete.

Constat du 06/10/2026 (poste de Marlene) : la piece porte "00173654",
achat.commande stocke "173654". Le controle ne trouvait jamais de montant IMPORT.
"""
from src.scripts.gmail.load_facture import SQL_MONTANT_IMPORT, normaliser_pos


def test_po_normalises_sans_zeros():
    assert normaliser_pos(["00173654", "00179321", " 186738 "]) == ["173654", "179321", "186738"]


def test_po_vides_ou_nuls_ignores():
    assert normaliser_pos(["", "0000", None]) == []


def test_requete_compare_sans_zeros():
    assert "LTRIM(po_number::text, '0') = ANY(:pos)" in SQL_MONTANT_IMPORT
