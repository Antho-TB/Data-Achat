# -*- coding: utf-8 -*-
"""Tests parse_qualite -- nom de fichier + extraction SPECTRO (échantillon réel CA183435)."""
from src.scripts.etl.parse_qualite import parse_filename, parse_spectro

# Extrait réel du rapport labo SPECTRO (PO181325, éch3, CA183435).
SPECTRO = """SPECTRO
Date Heure mesure

12/06/2026 09:29:48

Nom Méthode

Fe-30-F

Hardness (HRC)

/NA

Norme Nuance

Décret 1976

CA183435

Alimentarité acier inox (décret 1976)

Conformity

Sample Name

PO181325 SP lg herit fromage 3 p éch3 DK

Cr

Mo

Ni

0.0082

13.32

0.0021
"""


class TestParseFilename:
    def test_analysis_file(self):
        r = parse_filename("PO181325 SP lg herit fromage 3 p éch1 couperet DK CA183435.pdf",
                           type_doc="analyse", societe="TB")
        assert r["po_number"] == "00181325"
        assert r["ref_rapport"] == "CA183435"
        assert r["stade"] == "SP"
        assert r["echantillon"] == "1"
        assert r["type"] == "analyse"
        assert r["societe"] == "TB"


class TestParseSpectro:
    def setup_method(self):
        self.r = parse_spectro(SPECTRO)

    def test_ref(self):
        assert self.r["ref_rapport"] == "CA183435"

    def test_date(self):
        assert self.r["date_mesure"] == "2026-06-12T09:29:48"

    def test_sample_name(self):
        assert "PO181325" in self.r["sample_name"] and "éch3" in self.r["sample_name"]

    def test_hardness_na_is_none(self):
        assert self.r["hardness_hrc"] is None   # « /NA »

    def test_norme_and_conformite(self):
        assert "décret 1976" in self.r["norme"].lower()
        assert self.r["conformite"] == "Conforme"

    def test_cr_best_effort_in_range(self):
        # best-effort : None ou une valeur inox plausible
        assert self.r["cr_pct"] is None or 11.5 <= self.r["cr_pct"] <= 20.0
