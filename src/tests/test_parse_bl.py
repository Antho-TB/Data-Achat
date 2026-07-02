# -*- coding: utf-8 -*-
"""[TEST] Tests parse_bl -- logique d'extraction (sans dépendance PDF/OCR)."""
from src.scripts.gmail.parse_bl import parse_bl, _to_iso


# Fixture calée sur l'exemple prouvé BL-SZSE2606480 (cf. TASKS.md).
BL_TEXT = """
QUALITAIR & SEA LOGISTICS
Bill of Lading No: BL-SZSE2606480
Shipper: DONGGUAN JIUSHENG HARDWARE SPRING CO., LTD
Consignee: TARRERIAS BONJEAN
Container No.: TGBU2004021
P/O: 00017281 / 00017639
Shipped on board: 05/06/2026
ETA: 2026-07-10
Port of loading: Shekou
Port of discharge: Fos-sur-Mer
Invoice No: INV-2026-0098
"""


class TestParseBL:
    def setup_method(self):
        self.rec = parse_bl(BL_TEXT)

    def test_conteneur(self):
        assert self.rec["n_conteneur"] == "TGBU2004021"

    def test_bl(self):
        assert self.rec["n_bl"] == "BL-SZSE2606480"

    def test_etd_reel_iso(self):
        assert self.rec["etd_reel"] == "2026-06-05"  # 05/06/2026 dd/mm/yyyy

    def test_eta_iso(self):
        assert self.rec["eta"] == "2026-07-10"

    def test_transitaire(self):
        assert self.rec["transitaire"] == "QUALITAIR"

    def test_pos_zero_padded(self):
        assert self.rec["po_numbers"] == ["00017281", "00017639"]

    def test_facture(self):
        assert self.rec["n_facture"] == "INV-2026-0098"


class TestToIso:
    def test_ddmmyyyy(self):
        assert _to_iso("05/06/2026") == "2026-06-05"

    def test_iso(self):
        assert _to_iso("2026-07-10") == "2026-07-10"

    def test_textual_month(self):
        assert _to_iso("05 Jun 2026") == "2026-06-05"

    def test_invalid(self):
        assert _to_iso("pas une date") is None
