# -*- coding: utf-8 -*-
"""
[TESTS]
Tests unitaires de la couche Transform du pipeline ETL Data-Achat.

Stratégie : la couche Transform est pure (pas d'I/O), donc testable sans DB
ni fichiers Excel. On couvre les fonctions de parsing critiques et les
invariants du pipeline (clé métier propre, dédoublonnage).

Usage : pytest src/tests/ -v
"""
import pandas as pd
import pytest

from src.scripts.etl.transform import (
    _clean_ref,
    _to_date_or_none,
    parse_statut_commande,
    transform_artwork,
    transform_commande,
)


class TestCleanRef:
    """_clean_ref : nettoyage des références Excel (PO#, MEN#, code article)."""

    def test_float_excel_devient_entier(self):
        assert _clean_ref(150073.0) == "150073"

    def test_str_float_devient_entier(self):
        assert _clean_ref("150073.0") == "150073"

    def test_decimal_reel_preserve(self):
        # "150073.05" ne doit PAS être tronqué (piège du replace('.0'))
        assert _clean_ref("150073.05") == "150073.05"

    def test_reference_texte_preservee(self):
        assert _clean_ref("ACCE0610005") == "ACCE0610005"

    def test_valeurs_poubelle(self):
        assert _clean_ref(" /") is None
        assert _clean_ref("-") is None
        assert _clean_ref("") is None
        assert _clean_ref(None) is None
        assert _clean_ref(float("nan")) is None

    def test_espaces_strippes(self):
        assert _clean_ref("  GDD-001  ") == "GDD-001"


class TestParseStatutCommande:
    """parse_statut_commande : champ libre acheteur -> statut normalisé + date."""

    def test_livree_avec_date(self):
        assert parse_statut_commande("Livrée le 18/09/2025") == ("Livrée", "2025-09-18")

    def test_en_production(self):
        assert parse_statut_commande("En production") == ("En production", None)

    def test_annulee_variantes(self):
        assert parse_statut_commande("ANNULÉE")[0] == "Annulée"
        assert parse_statut_commande("annulation client")[0] == "Annulée"

    def test_non_string(self):
        assert parse_statut_commande(None) == ("Inconnu", None)
        assert parse_statut_commande(12345) == ("Inconnu", None)


class TestToDateOrNone:
    def test_timestamp(self):
        assert _to_date_or_none(pd.Timestamp("2026-01-15")) == "2026-01-15"

    def test_nat(self):
        assert _to_date_or_none(pd.NaT) is None


class TestTransformCommande:
    """Invariants du DataFrame commande prêt pour PostgreSQL."""

    @pytest.fixture
    def df_import(self) -> pd.DataFrame:
        return pd.DataFrame({
            "PO#":                  [150073.0, 150073.0, 1.0, 165368.0],
            "MEN#":                 [900001.0, 900001.0, None, 900002.0],
            "REF":                  ["20480002", "20480002", " /", "10110035"],
            "Fournisseur":          ["JIUSHENG", "JIUSHENG", None, "POLYFLAME"],
            "Quantité":             [100, 200, None, 50],
            "PU":                   [1.5, 1.6, None, 3.2],
            "Etat de la commande":  ["En production", "Livrée le 18/09/2025", None, "En cours"],
        })

    def test_po_number_sans_artefact_float(self, df_import):
        result = transform_commande(df_import)
        assert "150073.0" not in result["po_number"].tolist()
        assert "150073" in result["po_number"].tolist()

    def test_lignes_frais_conservees(self, df_import):
        # Règle Circuit B : REF "/" = ligne de frais (molding fee) -> conservée
        # avec code_article NULL, jamais écartée
        result = transform_commande(df_import)
        frais = result[result["code_article"].isna()]
        assert len(frais) == 1
        assert frais["po_number"].iloc[0] == "1"

    def test_frais_multiples_non_fusionnes(self):
        # Plusieurs lignes de frais d'un même PO (code_article NULL) ne doivent
        # PAS être dédoublonnées entre elles (NaN == NaN pour drop_duplicates)
        df = pd.DataFrame({
            "PO#":                 [1.0, 1.0, 1.0],
            "MEN#":                [None, None, None],
            "REF":                 ["/", "/", "/"],
            "Fournisseur":         [None, None, None],
            "Quantité":            [None, None, None],
            "PU":                  [None, None, None],
            "Etat de la commande": [None, None, None],
        })
        result = transform_commande(df)
        assert len(result) == 3

    def test_dedoublonnage_cle_metier(self, df_import):
        # (150073, 20480002) présent 2 fois -> 1 seule ligne, la dernière gagne
        result = transform_commande(df_import)
        mask = (result["po_number"] == "150073") & (result["code_article"] == "20480002")
        assert mask.sum() == 1
        assert result.loc[mask, "statut"].iloc[0] == "Livrée"

    def test_artwork_mapping_statuts(self):
        # Semantique colonne Artwork de la Matrice : date -> Validé,
        # 'Oui' -> Validé, 'Non'/'Aucun'/'/' -> Aucun. Marquage '/' = pas suivi.
        df = pd.DataFrame({
            "Référence":      ["A1", "A2", "A3", "A4", "A5"],
            "Description FR": ["P1", "P2", "P3", "P4", "P5"],
            "Marquage":       ["TB COLLECTION", "LAGUIOLE", "TB", " /", "TB"],
            "Artwork":        [pd.Timestamp("2024-01-25"), "Oui", "Non", "Oui", None],
        })
        result = transform_artwork(df)
        statuts = dict(zip(result["code_article"], result["statut_artwork"]))
        assert statuts == {"A1": "Validé", "A2": "Validé", "A3": "Aucun", "A5": "Aucun"}
        assert "A4" not in statuts  # marquage '/' -> pas de suivi artwork
        assert result.set_index("code_article").loc["A1", "date_demande"].isoformat() == "2024-01-25"

    def test_po_number_jamais_nul(self, df_import):
        # Prérequis : toute ligne chargée a un PO#. Le code_article peut être
        # NULL (lignes de frais) -- la contrainte UNIQUE PostgreSQL traite les
        # NULL comme distincts, pas de conflit possible.
        result = transform_commande(df_import)
        assert result["po_number"].notna().all()
