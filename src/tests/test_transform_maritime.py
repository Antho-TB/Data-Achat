# -*- coding: utf-8 -*-
"""[TEST] Tests transform_maritime -- lignes réelles du gsheet SUIVI MARITIME (30/06)."""
from src.scripts.etl.transform_maritime import (
    transform_rows, parse_maritime_date, clean_pos,
)

HEADER = ["FOURNISSEUR", "COMMANDE", "REF QUALITAIR", "TYPE", "POL", "POD",
          "NAVIRE", "ETD", "ETA", "CONTENEUR", "ATD", "ETA", "BL", "ORIGINAUX",
          "DDL ESTIMEE", "DATE CONFIRMEE", "HEURE", "SITE", "COMMENTAIRE"]

# Lignes réelles (extraits du gsheet 1hP73oiv…).
ROW_A = ["DONG GUAN QYPACKING", "00016852", "SOFSI25075366", "20GP", "SHEKOU",
         "FOS", "ONE FREEDOM", "28 December", "6 March", "TGBU3898959",
         "25 December", "26 February", "SZSE2600172", "Reçu", "12 March",
         "12 March", "08:00", "GDD", "Livré"]
ROW_B = ["BONLY / MINGHAO", "00017281 (PP242) / 00017639 (PP244) / 00173655",
         "SOFSI26033782", "20GP", "SHEKOU", "FOS", "YM TRUTH", "4 June",
         "25 July", "TGBU2004021 ", "5 June", "25 July",
         "SZSE2606480 SZSE2606397", "- Telex - En attente", "28 July", "", "",
         "GDD / POMMIER", "PERFECTIONNEMENT PASSIF"]
ROW_BOOKING = ["NOSKI", "", "TB#FUSION-PROMO", "40GP", "SHEKOU", "FOS", "", "",
               "", "", "", "", "", "", "", "7 January", "", "", ""]
ROW_CAL = [" AVRIL SEM 14", "Monday 30/03", "Tuesday 31/03", "", "", "", "", "",
           "", "", "", "", "", "", "", "", "", "", ""]
ROW_AFTER_CAL = ["8H", "", "", "", "", "", "", "", "", "ZZZU9999999", "", "", "", "", "", "", "", "", ""]

ROWS = [["SUIVI"], ["bannière"], HEADER, ROW_A, ROW_B, ROW_BOOKING, ROW_CAL, ROW_AFTER_CAL]


class TestTransformRows:
    def setup_method(self):
        self.recs = transform_rows(ROWS, campaign_year=2026, source_fichier="test.xlsx")

    def test_count_stops_at_calendar_and_skips_bookings(self):
        # A + B seulement (booking sans conteneur ignoré, calendrier non parcouru)
        assert len(self.recs) == 2
        assert all(r["n_conteneur"] != "ZZZU9999999" for r in self.recs)

    def test_row_a(self):
        a = self.recs[0]
        assert a["n_conteneur"] == "TGBU3898959"
        assert a["etd_reel"] == "2025-12-25"   # ATD 25 December -> année-1
        assert a["eta"] == "2026-02-26"         # ETA confirmée 26 February
        assert a["n_bl"] == "SZSE2600172"
        assert a["po_numbers"] == ["00016852"]
        assert a["transitaire"] == "QUALITAIR"

    def test_row_b_multi_po_and_trailing_space(self):
        b = self.recs[1]
        assert b["n_conteneur"] == "TGBU2004021"            # espace final nettoyé
        assert b["n_bl"] == "SZSE2606480"                   # 1er BL
        assert b["etd_reel"] == "2026-06-05"
        assert b["eta"] == "2026-07-25"
        assert b["po_numbers"] == ["00017281", "00017639", "00173655"]
        assert b["lieu_livraison"] == "GDD / POMMIER"


class TestHelpers:
    def test_date_year_rollover(self):
        assert parse_maritime_date("28 December", 2026) == "2025-12-28"
        assert parse_maritime_date("6 March", 2026) == "2026-03-06"
        assert parse_maritime_date("25 July", 2026) == "2026-07-25"
        assert parse_maritime_date("", 2026) is None

    def test_clean_pos(self):
        assert clean_pos("00162299/ 163764") == ["00162299", "00163764"]
        assert clean_pos("PO00169477/174098/00017492") == ["00017492", "00169477", "00174098"]
        assert clean_pos("00015863 (PP 231)") == ["00015863"]
        assert clean_pos("") == []
