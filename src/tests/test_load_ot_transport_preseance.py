# -*- coding: utf-8 -*-
"""
[TEST]
Le suivi maritime trace ses changements d'ETA et respecte la preseance
chronologique, comme les pieces jointes Gmail.

Avant le 07/10/2026, load_ot_transport ecrasait l'ETA sans evenement : les
pastilles de changement ne voyaient que les PJ Gmail.
"""
from datetime import date, datetime
from unittest.mock import MagicMock

import pandas as pd

from src.scripts.etl.load import _appliquer_preseance_eta

GSHEET_LU_LE = "2026-10-07T02:00:00+00:00"


def _conn(eta: date | None, eta_maj_le: datetime | None) -> MagicMock:
    conn = MagicMock()
    conn.execute.return_value.fetchone.return_value = (eta, None, eta_maj_le, None)
    return conn


def _df(eta: date | None, date_transmission: str | None = GSHEET_LU_LE) -> pd.DataFrame:
    return pd.DataFrame([{
        "n_conteneur": "MSMU3526021", "eta": eta, "date_livraison": pd.NaT,
        "source_fichier": "2026 SUIVI MARITIME.xlsx", "date_transmission": date_transmission,
    }])


def test_changement_eta_du_gsheet_trace():
    df, evenements = _appliquer_preseance_eta(
        _conn(date(2026, 10, 12), datetime(2026, 10, 1)), _df(date(2026, 10, 20)))
    assert df.loc[0, "eta"] == date(2026, 10, 20)
    assert df.loc[0, "eta_maj_le"] == pd.Timestamp("2026-10-07 02:00:00")
    assert len(evenements) == 1
    assert evenements[0]["champ_date"] == "eta"
    assert evenements[0]["ancienne_valeur"] == date(2026, 10, 12)


def test_eta_identique_aucun_evenement():
    _, evenements = _appliquer_preseance_eta(
        _conn(date(2026, 10, 12), datetime(2026, 10, 1)), _df(date(2026, 10, 12)))
    assert evenements == []


def test_copie_plus_ancienne_que_le_mail_n_ecrase_pas():
    """Copie serveur datee du 01/10, ETA deja transmise par mail le 05/10."""
    df, evenements = _appliquer_preseance_eta(
        _conn(date(2026, 10, 12), datetime(2026, 10, 5)),
        _df(date(2026, 9, 30), date_transmission="2026-10-01T08:00:00+00:00"))
    assert df.loc[0, "eta"] == date(2026, 10, 12)
    assert evenements == []


def test_bootstrap_sans_date_ne_remplace_pas_une_eta_datee():
    df, evenements = _appliquer_preseance_eta(
        _conn(date(2026, 10, 12), datetime(2026, 10, 5)), _df(date(2026, 9, 30), date_transmission=None))
    assert df.loc[0, "eta"] == date(2026, 10, 12)
    assert evenements == []


def test_cellule_vide_n_efface_pas_l_eta():
    df, _ = _appliquer_preseance_eta(
        _conn(date(2026, 10, 12), datetime(2026, 10, 5)), _df(None))
    assert df.loc[0, "eta"] == date(2026, 10, 12)
