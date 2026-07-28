# -*- coding: utf-8 -*-
"""
[TEST] Validation de la génération et de l'export Excel de la Fiche Achat (FOR-ACH-03-12)
"""
from io import BytesIO

import openpyxl
import pytest
from fastapi.testclient import TestClient

from src.utils.export_fiche_excel import generate_fiche_excel_bytes


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
    }

    response = client.post("/api/fiche-achat/export-excel", json=payload)
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert "attachment; filename=" in response.headers["content-disposition"]
    assert len(response.content) > 1000
