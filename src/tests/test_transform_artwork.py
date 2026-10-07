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

TAGGED_ROWS = [
    ("Suivi", r) for r in [["Suivi"], H1, B1_OK, B1_NOREF, H2, B2_OK, B2_NA, B2_DUP]
] + [
    ("Artworks en attente", r) for r in [H1, B1_NOUVEAU]
]


class TestTransformArtwork:
    def setup_method(self):
        self.recs = {r["code_article"]: r for r in transform_rows(TAGGED_ROWS, "test.xlsx")}

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

    def test_statut_en_attente(self):
        assert self.recs["Comp0806"]["statut_artwork"] == "En attente"

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


class TestOngletEnAttenteReel:
    """
    Structure reelle du gsheet au 07/10/2026 : l'onglet "Artworks en attente"
    n'a pas d'intitule en colonne A, la colonne de commentaire acheteur s'appelle
    "Commentaire Maxence", et les lignes portent "REF À CRÉER" ou "PAS DE REF".
    Avant correctif, tout l'onglet etait ignore.
    """
    H_ATTENTE = ["", "Désignation", "Date de dernière version", "Date de dernière validation",
                 "Date de demande artwork", "Niveau de priorité\n1->5", "Valideur",
                 "Commentaire Maxence", "Commentaire Clarisse / Thomas",
                 "Date d'application :\n17/07/2025"]
    LIGNES = [
        ["REF À CRÉER", "BLOC À COUTEAUX VIDE EN ALUMINIUM", "NOUVEAU", "NOUVEAU", " /", "3",
         "Clarisse", "Création", "ARTWORK EN COURS DE VALIDATION", ""],
        ["PAS DE REF", "M16 - COUVERTS LAGUIOLE HÉRITAGE - INSPIRATION", "NOUVEAU", "NOUVEAU",
         "/", "4", "Clarisse", "Création", "à valider avec Éric", ""],
        ["Comp0806", "BOITE DETAIL VIDE POUR 3CTX", "NOUVEAU", "NOUVEAU", " /", "5",
         "Clarisse", "Création", "en attente de DIE CUT", ""],
        ["", "#N/A", "#N/A", "#N/A", "", "", "#N/A", "#N/A", "", ""],
    ]
    H_LISTE = ["Référence", "Désignation", "Date de dernière version",
               "Date de dernière validation", "Valideur", "Commentaire sur dernière version"]
    L_LISTE = ["402010", "M24 LAG METAL COF. + BANDEAU", "24-août-26", "24-août-26",
               "Clarisse", "Version 2026"]

    def setup_method(self):
        rows = [("Artworks en attente", r) for r in [self.H_ATTENTE] + self.LIGNES]
        rows += [("Liste artworks", r) for r in [["LISTE DES ARTWORKS"], self.H_LISTE, self.L_LISTE]]
        self.recs = {r["code_article"]: r for r in transform_rows(rows, "test")}

    def test_onglet_en_attente_lu(self):
        attente = [r for r in self.recs.values() if r["statut_artwork"] == "En attente"]
        assert len(attente) == 3

    def test_ref_a_creer_et_pas_de_ref_recoivent_un_code_synthetique(self):
        assert "NOUVEAU-BLOC-A-COUTEAUX-VIDE-EN-ALUMINIUM" in self.recs
        assert "NOUVEAU-M16-COUVERTS-LAGUIOLE-HERITAGE-INSPIRATION" in self.recs
        assert "REF À CRÉER" not in self.recs

    def test_commentaire_maxence_dans_la_colonne_acheteur(self):
        r = self.recs["Comp0806"]
        assert r["commentaire_andrea"] == "Création"
        assert r["commentaire"] is None
        assert r["priorite"] == 5

    def test_en_tete_de_l_onglet_precedent_non_reutilise(self):
        r = self.recs["402010"]
        assert r["statut_artwork"] == "Validé"
        assert r["valideur"] == "Clarisse"
        assert r["commentaire"] == "Version 2026"
