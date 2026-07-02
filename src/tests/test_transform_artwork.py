# -*- coding: utf-8 -*-
"""[TEST] Tests transform_artwork -- 2 blocs empilés, dates FR, gotchas (profil #3)."""
from src.scripts.etl.transform_artwork import transform_rows, parse_fr_date

# Bloc 1 (10 col) puis Bloc 2 (6 col), en-têtes distincts -> mapping par NOM.
H1 = ["Référence", "Désignation", "Date de dernière version", "Date de dernière validation",
      "Date de demande artwork", "Niveau de priorité 1->5", "Valideur",
      "Commentaire Andréa", "Commentaire Clarisse / Thomas", "Date d'application"]
B1_OK = ["443850", "M16 LAG ABS MARBRE ROUGE", "26/03/2024", "26/03/2024",
         "24/06/2026", "3", "Clarisse", "Ancienne version", "", "17/07/2025"]
B1_NOUVEAU = ["Comp0806", "LAGUIOLE HÉRITAGE COSTCO", "NOUVEAU", "NOUVEAU", "/", "4",
              "Clarisse", "Création", "", ""]
B1_NOREF = ["PAS DE REF", "X", "NOUVEAU", "NOUVEAU", "/", "4", "Clarisse", "", "", ""]

H2 = ["Référence", "Désignation", "Date de dernière version",
      "Date de dernière validation", "Valideur", "Commentaire sur dernière version"]
B2_OK = ["401740", "PIERRE A AIGUISER EN BOITE", "6-juin-24", "24-févr.-26",
         "Clarisse", "Site web à modifier"]
B2_NA = ["10320023", "ETUI", "\\#N/A", "\\#N/A", "Carrefour", "à voir"]
B2_DUP = ["401740", "PIERRE A AIGUISER (maj)", "8-avr.-25", "22/1/2026", "Clarisse", "version récente"]

ROWS = [["Suivi"], H1, B1_OK, B1_NOUVEAU, B1_NOREF, H2, B2_OK, B2_NA, B2_DUP]


class TestTransformArtwork:
    def setup_method(self):
        self.recs = {r["code_article"]: r for r in transform_rows(ROWS, "test.xlsx")}

    def test_skips_pas_de_ref(self):
        assert "PAS DE REF" not in self.recs

    def test_dedup_keeps_last(self):
        # 401740 présent 2x -> garde la dernière (date_validation 22/1/2026)
        assert self.recs["401740"]["date_validation"] == "2026-01-22"
        assert "récente" in self.recs["401740"]["commentaire"]

    def test_bloc1_dates_and_prio(self):
        r = self.recs["443850"]
        assert r["date_demande"] == "2026-06-24"
        assert r["date_validation"] == "2024-03-26"
        assert r["priorite"] == 3

    def test_statut_nouveau(self):
        assert self.recs["Comp0806"]["statut_artwork"] == "Nouveau"

    def test_statut_valide(self):
        assert self.recs["443850"]["statut_artwork"] == "Validé"

    def test_na_to_null(self):
        assert self.recs["10320023"]["date_validation"] is None
        assert self.recs["10320023"]["derniere_version"] is None


class TestParseFrDate:
    def test_slash(self):
        assert parse_fr_date("26/03/2024") == "2024-03-26"
        assert parse_fr_date("22/1/2026") == "2026-01-22"

    def test_fr_month_abbrev(self):
        assert parse_fr_date("6-juin-24") == "2024-06-06"
        assert parse_fr_date("24-févr.-26") == "2026-02-24"
        assert parse_fr_date("8-avr.-25") == "2025-04-08"

    def test_literals_null(self):
        for x in ("NOUVEAU", "/", "#N/A", "\\#N/A", ""):
            assert parse_fr_date(x) is None
