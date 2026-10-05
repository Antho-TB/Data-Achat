# -*- coding: utf-8 -*-
"""
[TEST]
Preseance chronologique des pieces jointes Gmail sur le suivi maritime.

Cas reel du 05/10/2026 : un PDF transitaire du 20/05, relu a chaque passage,
ecrasait chaque matin l'ETA du suivi maritime du conteneur MSMU3526021, car sa
date de transmission retombait sur l'heure du chargement.
"""
from datetime import date, datetime
from unittest.mock import MagicMock

from src.scripts.gmail.load_ot_gmail import (
    _horodatage,
    _resolve_tracked,
    _row_params,
    date_depuis_nom_fichier,
)

PDF = "20260520_Lucie BONNET _lbonnet@qualitai_Confirmation de date de livraison.PDF"


def _conn(eta: date, eta_maj_le: datetime) -> MagicMock:
    conn = MagicMock()
    conn.execute.return_value.fetchone.return_value = (eta, None, eta_maj_le, None)
    return conn


def test_date_lue_dans_le_prefixe_du_fichier():
    assert date_depuis_nom_fichier(PDF) == "2026-05-20T00:00:00+00:00"
    assert date_depuis_nom_fichier("sans_date.pdf") is None
    assert date_depuis_nom_fichier("20261340_mois_invalide.pdf") is None
    assert date_depuis_nom_fichier(None) is None


def test_row_params_utilise_la_date_du_mail_et_pas_maintenant():
    params = _row_params({"n_conteneur": "MSMU3526021", "eta": "2026-05-12", "source_fichier": PDF})
    assert params["date_transmission"] == "2026-05-20T00:00:00+00:00"


def test_vieux_pdf_necrase_plus_une_eta_plus_recente():
    params = _row_params({"n_conteneur": "MSMU3526021", "eta": "2026-05-12", "source_fichier": PDF})
    conn = _conn(date(2026, 5, 29), datetime(2026, 10, 5, 8, 19, 45))
    events = _resolve_tracked(conn, params)
    assert events == []
    assert params["eta"] == date(2026, 5, 29)


def test_piece_sans_date_ne_pretend_pas_etre_la_plus_recente():
    params = _row_params({"n_conteneur": "X1", "eta": "2026-05-12", "source_fichier": "scan.pdf"})
    events = _resolve_tracked(_conn(date(2026, 5, 29), datetime(2026, 6, 1)), params)
    assert events == [] and params["eta"] == date(2026, 5, 29)


def test_piece_plus_recente_gagne_et_historise():
    params = _row_params({"n_conteneur": "X1", "eta": "2026-06-10",
                          "source_fichier": "20260602_maj_eta.pdf"})
    events = _resolve_tracked(_conn(date(2026, 5, 29), datetime(2026, 6, 1)), params)
    assert len(events) == 1
    assert events[0]["nouvelle_valeur"] == "2026-06-10"


def test_horodatage_compare_formats_mixtes():
    assert _horodatage("2026-05-20T00:00:00+00:00") < _horodatage(datetime(2026, 10, 5, 8, 19))
    assert _horodatage("2026-10-05T10:00:00+02:00") == datetime(2026, 10, 5, 8, 0)
