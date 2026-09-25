# -*- coding: utf-8 -*-
"""
[TEST]
=============================================================================
CRAWL DRIVE QUALITE (crawl_drive_qualite.py)
=============================================================================

La racine qualite "TARRERIAS BONJEAN - TB" est un Drive partage. Sans
supportsAllDrives / includeItemsFromAllDrives, l'API Drive renvoie une liste
vide au lieu d'une erreur : le 24/09, le crawl a annonce [SUCCES] avec 0
dossier PO. Le faux client ci-dessous reproduit ce comportement.

Les noms de sous-dossiers sont ceux releves sur le Drive le 25/09, faute de
frappe comprise : une comparaison exacte les ratait tous.
"""
from __future__ import annotations

from typing import Any

import pytest

from src.scripts.etl.crawl_drive_qualite import FOLDER_MIME, _type_sous_dossier, crawl

ROOT_ID = "root"

TREE: dict[str, list[dict[str, str]]] = {
    ROOT_ID: [{"id": "po1", "name": "PO 00189493 - Appro 290831 - HONGXING", "mimeType": FOLDER_MIME}],
    "po1": [
        {"id": "sub1", "name": "Results of Analysis", "mimeType": FOLDER_MIME},
        {"id": "sub2", "name": "Inpesctions", "mimeType": FOLDER_MIME},
        {"id": "sub3", "name": "Artworks", "mimeType": FOLDER_MIME},
    ],
    "sub1": [{"id": "f1", "name": "PO189493 SP CA123 ech1.pdf", "mimeType": "application/pdf"}],
    "sub2": [{"id": "f2", "name": "PO189493 inspection CA124.pdf", "mimeType": "application/pdf"}],
    "sub3": [{"id": "f3", "name": "PO189493 artwork.pdf", "mimeType": "application/pdf"}],
}


class _Request:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def execute(self) -> dict[str, Any]:
        return self._payload


class _SharedDriveFiles:
    """Imite l'API Drive v3 sur un Drive partage."""

    def list(self, q: str, supportsAllDrives: bool = False,
             includeItemsFromAllDrives: bool = False, **_: Any) -> _Request:
        if not (supportsAllDrives and includeItemsFromAllDrives):
            return _Request({"files": []})
        parent = q.split("'")[1]
        return _Request({"files": TREE.get(parent, [])})


class _Service:
    def files(self) -> _SharedDriveFiles:
        return _SharedDriveFiles()


class _EmptyService(_Service):
    def files(self) -> _SharedDriveFiles:
        files = _SharedDriveFiles()
        files.list = lambda **_: _Request({"files": []})  # type: ignore[method-assign]
        return files


def test_drive_partage_lu_jusqu_aux_pdf() -> None:
    rows = crawl(_Service(), ROOT_ID)
    types = {r["drive_file_id"]: r["type"] for r in rows}
    assert types == {"f1": "analyse", "f2": "inspection"}
    assert all(r["po_number"] is not None for r in rows)


@pytest.mark.parametrize(("nom", "attendu"), [
    ("Results of Analysis", "analyse"),
    ("Results of analysis", "analyse"),
    ("Reports of analysis", "analyse"),
    ("Inspections", "inspection"),
    ("Inpesctions", "inspection"),
    ("Inspection", "inspection"),
    ("Artworks", None),
    ("Purchase Sheets", None),
    ("Instructions", None),
])
def test_type_sous_dossier(nom: str, attendu: str | None) -> None:
    assert _type_sous_dossier(nom) == attendu


def test_racine_sans_dossier_po_echoue() -> None:
    with pytest.raises(RuntimeError, match="Aucun dossier PO"):
        crawl(_EmptyService(), ROOT_ID)
