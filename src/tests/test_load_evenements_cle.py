# -*- coding: utf-8 -*-
"""
[TEST] Normalisation et clé d'idempotence des événements Gmail (08/10/2026).

Constat du poste métier (06/10) : 57 lignes en trop sur 366 dans
achat.qualite_decision. PO écrit avec ou sans zéros de tête, champs transport
remplis au hasard sur une décision qualité, stade absent de la clé.
"""
import logging

import pytest

from src.scripts.gmail.load_evenements import (
    _cle, load, normaliser, normaliser_po, normaliser_stade, sql_insertion,
)


def _qualite(**kw: object) -> dict:
    rec = {"domaine": "qualite", "thread_id": "19f88e7cdd469906",
           "po_number": "00187324", "code_article": "30110003",
           "decision": "conforme", "stade": "MAT"}
    rec.update(kw)
    return rec


def _cle_qualite(**kw: object) -> str:
    return _cle(normaliser(_qualite(**kw)), "decision")


class TestNormalisation:
    @pytest.mark.parametrize("brut,attendu", [
        ("187324", "00187324"), ("00187324", "00187324"), (" 187324 ", "00187324"),
        (187324, "00187324"), ("123456789", "123456789"), ("PO142645 ", "PO142645"),
        ("", None), (None, None),
    ])
    def test_po(self, brut: object, attendu: str | None) -> None:
        assert normaliser_po(brut) == attendu

    @pytest.mark.parametrize("brut,attendu", [
        ("FRI", "inspection"), ("fri", "inspection"), ("Inspection", "inspection"),
        ("mat", "MAT"), (" SP ", "SP"), ("bat", "BAT"),
        ("RECEP", "reception"), ("reception", "reception"), ("Reception", "reception"),
        ("echantillon", "echantillon"), ("", None), (None, None),
    ])
    def test_stade(self, brut: object, attendu: str | None) -> None:
        assert normaliser_stade(brut) == attendu

    def test_decision_et_type_en_minuscules(self) -> None:
        rec = normaliser({"domaine": " Qualite ", "decision": " Non_Conforme ", "type": "ETA"})
        assert rec["domaine"] == "qualite"
        assert rec["decision"] == "non_conforme"
        assert rec["type"] == "eta"

    def test_enregistrement_source_non_modifie(self) -> None:
        brut = _qualite(po_number="187324")
        normaliser(brut)
        assert brut["po_number"] == "187324"

    def test_cle_reservation_po_normalise(self) -> None:
        rec = normaliser(_qualite(decision="reservee", stade="inspection",
                                  cle_idempotence="dekra_resa|1a0d|187324"))
        assert _cle(rec, "decision") == "dekra_resa|1a0d|00187324"


class TestCleQualite:
    def test_po_avec_ou_sans_zeros_meme_cle(self) -> None:
        assert _cle_qualite(po_number="187324") == _cle_qualite(po_number="00187324")

    def test_mat_et_sp_cles_differentes(self) -> None:
        assert _cle_qualite(stade="MAT") != _cle_qualite(stade="SP")

    def test_fri_et_inspection_meme_cle(self) -> None:
        assert _cle_qualite(stade="FRI") == _cle_qualite(stade="inspection")

    def test_casse_de_la_decision_ignoree(self) -> None:
        assert _cle_qualite(decision="Conforme ") == _cle_qualite(decision="conforme")

    def test_champs_transport_hors_cle_qualite(self) -> None:
        avec = _cle_qualite(n_conteneur="MSMU4312765", champ_date="eta",
                            nouvelle_valeur="2026-10-01")
        assert avec == _cle_qualite()

    def test_format(self) -> None:
        assert _cle_qualite(po_number="187324", stade="fri") == (
            "19f88e7cdd469906|qualite|conforme|00187324|30110003|inspection")

    def test_po_absent(self) -> None:
        assert _cle_qualite(po_number=None, code_article=None) == (
            "19f88e7cdd469906|qualite|conforme|||MAT")


class TestCleTransportInchangee:
    def test_format_transport(self) -> None:
        rec = {"domaine": "transport", "thread_id": "1a116d10ced7f12c", "type": "retard",
               "po_number": "00177464", "n_conteneur": "MSMU4312765",
               "champ_date": "livraison", "nouvelle_valeur": "2026-10-12"}
        assert _cle(normaliser(rec), "type") == (
            "1a116d10ced7f12c|transport|retard|00177464||MSMU4312765|livraison|2026-10-12")

    def test_discriminants_secondaires_conserves(self) -> None:
        base = {"domaine": "transport", "thread_id": "t", "type": "chgt_date",
                "po_number": "00181325", "champ_date": "eta"}
        etd = dict(base, champ_date="etd")
        assert _cle(normaliser(base), "type") != _cle(normaliser(etd), "type")

    def test_cle_fournie_respectee(self) -> None:
        rec = {"domaine": "transport", "cle_idempotence": "transport:MSMU3526021:eta:2026-05-12"}
        assert _cle(normaliser(rec), "type") == "transport:MSMU3526021:eta:2026-05-12"


class TestSqlInsertion:
    COLS = ["cle_idempotence", "po_number", "date_info", "decision", "motif", "texte"]

    def test_reservation_mise_a_jour_si_differente(self) -> None:
        sql = sql_insertion("achat.qualite_decision", self.COLS,
                            normaliser(_qualite(decision="Reservee", stade="inspection")))
        assert "ON CONFLICT (cle_idempotence) DO UPDATE SET" in sql
        assert "date_info = EXCLUDED.date_info" in sql
        assert "IS DISTINCT FROM" in sql
        assert "DO NOTHING" not in sql

    def test_autre_decision_ignoree_si_presente(self) -> None:
        sql = sql_insertion("achat.qualite_decision", self.COLS, normaliser(_qualite()))
        assert sql.endswith("ON CONFLICT (cle_idempotence) DO NOTHING")

    def test_transport_ignore_si_present(self) -> None:
        sql = sql_insertion("achat.transport_evenement", ["cle_idempotence", "type"],
                            normaliser({"domaine": "transport", "type": "reservee"}))
        assert sql.endswith("DO NOTHING")


def test_dry_run_normalise_sans_base(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        load([_qualite(po_number="187324", stade="FRI")], dry_run=True)
    assert "19f88e7cdd469906|qualite|conforme|00187324|30110003|inspection" in caplog.text
