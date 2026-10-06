# -*- coding: utf-8 -*-
"""
[TEST] Repli du suivi maritime sur le fichier serveur quand le gsheet est illisible.

Constaté le 06/10 : le repli levait NameError (Config non importé), donc un gsheet
injoignable arrêtait le chargement maritime au lieu de revenir au fichier serveur.
"""
from pathlib import Path

import pandas as pd
import pytest

from src.scripts.etl import extract, transform_maritime


@pytest.fixture
def gsheet_illisible(monkeypatch: pytest.MonkeyPatch) -> None:
    def _echec(_file_id: str) -> list[dict]:
        raise RuntimeError("credentials.json introuvable")
    monkeypatch.setattr(transform_maritime, "_read_rows_gsheet", _echec)


def test_repli_sur_fichier_serveur(gsheet_illisible: None, tmp_path: Path,
                                   monkeypatch: pytest.MonkeyPatch) -> None:
    fichier = tmp_path / "2026 SUIVI MARITIME.xlsx"
    pd.DataFrame({"CONTENEUR": ["MSMU3526021"]}).to_excel(
        fichier, sheet_name="CONTENEUR PLEIN", index=False)
    monkeypatch.setattr(extract.Config, "SUIVI_MARITIME_PATH_FICHIER", str(fichier))

    df = extract.extract_suivi_maritime("gsheet")

    assert df is not None and list(df["CONTENEUR"]) == ["MSMU3526021"]


def test_repli_sans_fichier_passe_en_degrade(gsheet_illisible: None,
                                              monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(extract.Config, "SUIVI_MARITIME_PATH_FICHIER", "")

    assert extract.extract_suivi_maritime("gsheet") is None
