# -*- coding: utf-8 -*-
"""
[TEST] Validation du connecteur Google Sheets API gsheets.py
"""
import pytest

from src.scripts.etl import transform_maritime
from src.utils import gsheets
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


# ===========================================================================
# AIGUILLAGE GOOGLE SHEET NATIF / FICHIER OFFICE
# ===========================================================================
# Le suivi maritime du transitaire est un .xlsx depose dans Drive, pas un Google
# Sheet : l'API Sheets le refusait, et le repli d'extract.py retombait alors sur
# la copie serveur sans colonne BL. Ces tests verrouillent le fait que le choix
# de l'API se fait sur le type MIME REEL, jamais sur le message d'erreur de
# Google, qui peut etre reformule sans preavis.

MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def test_fichier_office_lu_via_drive(monkeypatch) -> None:
    """Un .xlsx Drive doit partir sur la lecture Drive, pas sur l'API Sheets."""
    monkeypatch.setattr(gsheets, "metadonnees_drive", lambda *a, **k: {
        "name": "SUIVI MARITIME TARRERIAS 2026.xlsx", "mimeType": MIME_XLSX})
    monkeypatch.setattr(gsheets, "lire_xlsx_drive",
                        lambda *a, **k: [("SUIVI", [["BL"], ["SZSE2600172"]])])
    monkeypatch.setattr(gsheets, "read_all_tabs", lambda *a, **k: pytest.fail(
        "l'API Sheets ne doit jamais etre appelee sur un fichier Office"))

    assert gsheets.lire_classeur("1hP73o") == [("SUIVI", [["BL"], ["SZSE2600172"]])]


def test_google_sheet_natif_lu_via_api_sheets(monkeypatch) -> None:
    """Les autres classeurs (artworks, qualite) restent lus par l'API Sheets."""
    monkeypatch.setattr(gsheets, "metadonnees_drive", lambda *a, **k: {
        "name": "Suivi Artworks", "mimeType": gsheets.MIME_GOOGLE_SHEET})
    monkeypatch.setattr(gsheets, "read_all_tabs",
                        lambda *a, **k: [("Onglet1", [["a"]])])
    monkeypatch.setattr(gsheets, "lire_xlsx_drive", lambda *a, **k: pytest.fail(
        "un Google Sheet natif ne doit pas etre telecharge comme un fichier"))

    assert gsheets.lire_classeur("1w") == [("Onglet1", [["a"]])]


def test_seul_l_onglet_suivi_est_retenu(monkeypatch) -> None:
    """
    Les onglets mensuels sont des plannings sans BL : les lire melangerait leurs
    lignes a celles du suivi conteneurs.

    _read_rows_gsheet importe lire_classeur DANS la fonction, donc le nom est
    resolu sur le module a l'appel : patcher l'attribut suffit.
    """
    monkeypatch.setattr(gsheets, "lire_classeur", lambda *a, **k: [
        ("SUIVI", [["FOURNISSEUR", "CONTENEUR", "BL"],
                   ["DONGGUAN", "TGBU3898959", "SZSE2600172"]]),
        ("AOUT", [["SEMAINE 32"], ["planning livraison"]]),
    ])

    lignes = transform_maritime._read_rows_gsheet("1hP73o")
    assert ["FOURNISSEUR", "CONTENEUR", "BL"] in lignes
    assert not any("planning livraison" in ligne for ligne in lignes)


def test_repli_si_l_onglet_suivi_est_renomme(monkeypatch) -> None:
    """
    Le transitaire peut renommer son onglet : on replie sur tous les onglets
    plutot que de rendre zero ligne, mais l'avertissement doit sortir.

    Junior Tip : rendre une liste vide ici serait le pire comportement. Le
    transformateur leverait "en-tete introuvable" et on chercherait un bug de
    parsing, alors que le probleme serait un simple renommage d'onglet.
    """
    monkeypatch.setattr(gsheets, "lire_classeur", lambda *a, **k: [
        ("SUIVI 2026", [["FOURNISSEUR", "CONTENEUR", "BL"], ["DONGGUAN", "X", "Y"]]),
    ])

    lignes = transform_maritime._read_rows_gsheet("1hP73o")
    assert ["FOURNISSEUR", "CONTENEUR", "BL"] in lignes
