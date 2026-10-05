# -*- coding: utf-8 -*-
"""
[TEST] Validation de la génération et de l'export Excel de la Fiche Achat (FOR-ACH-03-12)
"""
from io import BytesIO

import openpyxl
import pytest
from fastapi.testclient import TestClient

from src.utils.export_fiche_excel import (
    EQUIV_COLONNES,
    EQUIV_TITRE_SECTION,
    generate_fiche_excel_bytes,
    lignes_equivalentes_non_vides,
)


@pytest.fixture(scope="module")
def client() -> TestClient:
    """
    Client HTTP de test, instancie a la demande.

    Junior Tip : TestClient(app) au niveau module declenchait le lifespan
    FastAPI, donc la connexion PostgreSQL, des la COLLECTE des tests. Toute la
    suite devenait dependante du VPN, y compris les tests purement unitaires.
    """
    from app.main import app
    with TestClient(app) as test_client:
        yield test_client


def test_generate_fiche_excel_bytes():
    data = {
        "supplier": "GUANGWEI",
        "po_number": "PO-2026-999",
        "n_lot": "2607231636",
        "forwarder": "QUALITAIRSEA",
        "transport_type": "Sea",
        "port": "FOS SUR MER",
        "etd": "2026-10-15",
        "testing_samples": True,
        "shipping_paid_by": "TB",
        "please_send_us": ["Production sample"],
    }
    items = [
        {
            "reference": "100200",
            "name": "STEAK KNIFE 11CM",
            "french_desc": "Couteau à steak 11cm",
            "pcs_item": 1,
            "pcs_inner": 12,
            "pcs_master": 144,
            "thickness": "2.0",
            "length": "110",
            "quality": "3Cr13",
            "ean13": "3148520000019",
        }
    ]

    excel_bytes = generate_fiche_excel_bytes(data, items)
    assert isinstance(excel_bytes, bytes)
    assert len(excel_bytes) > 0

    wb = openpyxl.load_workbook(BytesIO(excel_bytes))
    ws = wb.active
    assert ws.title == "Purchase Sheet"
    assert "PURCHASE SHEET" in str(ws["C1"].value)


def test_api_export_fiche_excel(client: TestClient):
    payload = {
        "data": {
            "supplier": "POLLYDA",
            "po_number": "PO-8888",
            "code_article": "00182725",
        },
        "items": [
            {
                "reference": "00182725",
                "name": "KNIFE BLOCK SET",
                "french_desc": "Bloc 5 couteaux",
            }
        ],
        "equivalents": [{"variante": "Noir", "difference": "Coloris"}],
    }

    response = client.post("/api/fiche-achat/export-excel", json=payload)
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert "attachment; filename=" in response.headers["content-disposition"]
    assert len(response.content) > 1000
    ws = openpyxl.load_workbook(BytesIO(response.content)).active
    assert EQUIV_TITRE_SECTION in [str(c.value) for row in ws.iter_rows() for c in row]


def _cellules(ws) -> list[str]:
    """Toutes les valeurs non vides de la feuille, en texte."""
    return [str(c.value) for row in ws.iter_rows() for c in row if c.value is not None]


def _ligne_de(ws, valeur: str) -> int:
    """Numero de la premiere ligne contenant exactement cette valeur."""
    for row in ws.iter_rows():
        for c in row:
            if c.value == valeur:
                return c.row
    raise AssertionError(f"{valeur!r} absent de la feuille")


def test_references_equivalentes_exportees():
    equivalents = [
        {"code_article": "100201", "variante": "Rouge", "ean13": "3148520000026",
         "designation": "Couteau steak 11cm rouge", "difference": "Coloris",
         "quantite": "1 200", "prix": "1,35"},
        {"variante": "Vrac", "designation": "Couteau steak 11cm vrac",
         "difference": "Conditionnement", "quantite": "", "prix": "a confirmer"},
    ]
    wb = openpyxl.load_workbook(BytesIO(generate_fiche_excel_bytes(
        {"supplier": "GUANGWEI"}, [{"reference": "100200"}], equivalents)))
    ws = wb.active

    titre = _ligne_de(ws, EQUIV_TITRE_SECTION)
    entetes = [ws.cell(row=titre + 1, column=i).value for i in range(1, 8)]
    assert entetes == [t for _, t in EQUIV_COLONNES]

    rouge = [ws.cell(row=titre + 2, column=i).value for i in range(1, 8)]
    # EAN reste du texte (sinon Excel le passe en notation scientifique),
    # quantite et prix deviennent des nombres, virgule francaise comprise.
    assert rouge == ["100201", "Rouge", "3148520000026", "Couteau steak 11cm rouge", "Coloris", 1200, 1.35]

    vrac = [ws.cell(row=titre + 3, column=i).value for i in range(1, 8)]
    assert vrac[1] == "Vrac"
    assert vrac[6] == "a confirmer"  # saisie non numerique conservee

    # Placee entre la description produit et le transport.
    assert _ligne_de(ws, "SUPPLIER:") < titre < _ligne_de(ws, "TRANSPORT")


def test_references_equivalentes_vides_non_imprimees():
    lignes_vides = [{"code_article": "", "variante": "  ", "prix": None}]
    for equivalents in (None, [], lignes_vides):
        ws = openpyxl.load_workbook(BytesIO(generate_fiche_excel_bytes(
            {"supplier": "GUANGWEI"}, [{"reference": "100200"}], equivalents))).active
        assert EQUIV_TITRE_SECTION not in _cellules(ws)


def test_lignes_equivalentes_non_vides_filtre():
    lignes = [{"variante": ""}, {"variante": "Noir"}, {"prix": " "}, {"quantite": "0"}]
    assert lignes_equivalentes_non_vides(lignes) == [{"variante": "Noir"}, {"quantite": "0"}]
