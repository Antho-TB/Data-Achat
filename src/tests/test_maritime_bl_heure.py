# -*- coding: utf-8 -*-
"""
[TEST] BL multiples par conteneur et heure de livraison confirmée.

Deux règles métier confirmées par Andréa le 28/07 :
- un conteneur groupe plusieurs fournisseurs, chacun éditant son BL ;
- le transitaire renseigne la date de livraison confirmée en colonne P et
  l'heure en colonne Q, les deux comptent pour organiser le déchargement.
"""
from src.scripts.etl.transform_maritime import (
    combiner_date_heure,
    extraire_bls,
    resoudre_colonnes,
)

# En-tête réel du classeur partagé avec le transitaire (18 colonnes).
HEADER_GSHEET = ["FOURNISSEUR", "COMMANDE", "REF QUALITAIR", "TYPE", "POL", "POD",
                 "NAVIRE", "ETD", "ETA", "CONTENEUR", "ATD", "ETA", "BL", "ORIGINAUX",
                 "DDL ESTIMEE", "DATE CONFIRMEE", "HEURE", "SITE", "COMMENTAIRE"]


class TestExtractionBL:
    def test_un_seul_bl(self):
        assert extraire_bls("SZSE2600172") == ["SZSE2600172"]

    def test_plusieurs_bl_separes_par_espace(self):
        """Cas réel du gsheet : deux fournisseurs dans le même conteneur."""
        assert extraire_bls("SZSE2606480 SZSE2606397") == ["SZSE2606480", "SZSE2606397"]

    def test_separateurs_varies(self):
        for cellule in ("SZSE2606480, SZSE2606397", "SZSE2606480;SZSE2606397",
                        "SZSE2606480 / SZSE2606397"):
            assert extraire_bls(cellule) == ["SZSE2606480", "SZSE2606397"]

    def test_doublons_ecartes(self):
        assert extraire_bls("SZSE2606480 SZSE2606480") == ["SZSE2606480"]

    def test_bruit_historique_ecarte(self):
        """La colonne contenait du bruit : 'DHL', 'ATTACH', '/', '-'."""
        for bruit in ("DHL", "ATTACH", "ACKTRAY", "/", "-", "", None):
            assert extraire_bls(bruit) == [], f"{bruit!r} ne devrait pas passer"

    def test_melange_bruit_et_vrai_bl(self):
        assert extraire_bls("- Telex - SZSE2606480") == ["SZSE2606480"]


class TestHeureLivraison:
    def test_date_et_heure(self):
        assert combiner_date_heure("2026-09-08", "08:00") == "2026-09-08T08:00:00"

    def test_notation_francaise(self):
        assert combiner_date_heure("2026-09-08", "14h30") == "2026-09-08T14:30:00"
        assert combiner_date_heure("2026-09-08", "8h") == "2026-09-08T08:00:00"

    def test_sans_heure(self):
        assert combiner_date_heure("2026-09-08", "") == "2026-09-08"
        assert combiner_date_heure("2026-09-08", None) == "2026-09-08"

    def test_heure_illisible_ne_casse_pas_la_date(self):
        assert combiner_date_heure("2026-09-08", "matin") == "2026-09-08"
        assert combiner_date_heure("2026-09-08", "99:99") == "2026-09-08"

    def test_sans_date(self):
        assert combiner_date_heure(None, "08:00") is None


class TestColonnesGsheet:
    def test_lettres_citees_par_andrea(self):
        """
        Andréa repère les colonnes par leur lettre : conteneur en J, BL en M,
        date de livraison confirmée en P, heure en Q. Vérification que la
        résolution par nom retombe bien sur ces positions.
        """
        col = resoudre_colonnes(HEADER_GSHEET)
        assert col["conteneur"] == 9, "colonne J"
        assert col["bl"] == 12, "colonne M"
        assert col["date_confirmee"] == 15, "colonne P"
        assert col["heure"] == 16, "colonne Q"

    def test_deux_colonnes_eta_la_confirmee_gagne(self):
        col = resoudre_colonnes(HEADER_GSHEET)
        assert col["eta1"] == 8
        assert col["eta2"] == 11
