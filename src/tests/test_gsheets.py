# -*- coding: utf-8 -*-
"""
[TEST] Validation du connecteur Google Sheets API gsheets.py
"""
from src.utils.gsheets import grid_to_dicts


def test_grid_to_dicts():
    values = [
        ["code_article", "designation", "statut"],
        ["10110034", "Couteau Chef 20cm", "Validé"],
        ["11410021", "Bloc 5 couteaux", "En attente"],
    ]
    res = grid_to_dicts(values)
    assert len(res) == 2
    assert res[0]["code_article"] == "10110034"
    assert res[0]["statut"] == "Validé"
    assert res[1]["code_article"] == "11410021"


def test_grid_to_dicts_empty():
    assert grid_to_dicts([]) == []
    assert grid_to_dicts([["Header Only"]]) == []
