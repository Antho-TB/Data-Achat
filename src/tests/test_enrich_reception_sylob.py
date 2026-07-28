# -*- coding: utf-8 -*-
"""
[TEST]
Rapprochement des receptions physiques Sylob.

L'ancienne version de ce test mockait integralement le moteur et se contentait
de verifier qu'un rowcount injecte ressortait a l'identique : elle passait au
vert alors que le module ecrivait dans une table full-refresh et forcait le
statut "Livree" sur des commandes annulees. On teste desormais le SQL reellement
emis et les invariants metier qui comptent.
"""
from unittest.mock import MagicMock, patch

from src.scripts.etl import apply_enrichissement as mod_apply
from src.scripts.etl.enrich_reception_sylob import (
    SQL_RECEPTIONS,
    SQL_UPSERT,
    enrich_receptions_sylob,
)


def _mock_engine(lignes: list[dict]) -> tuple[MagicMock, MagicMock]:
    """Moteur SQLAlchemy simule renvoyant les lignes fournies en lecture."""
    engine, conn = MagicMock(), MagicMock()
    engine.begin.return_value.__enter__.return_value = conn
    select_result = MagicMock()
    select_result.mappings.return_value.all.return_value = lignes
    upsert_result = MagicMock()
    upsert_result.rowcount = 1
    conn.execute.side_effect = [select_result] + [upsert_result] * len(lignes)
    return engine, conn


def test_ecrit_dans_la_table_denrichissement_et_pas_dans_commande():
    """Invariant central : achat.commande est full-refresh, on n'y touche pas."""
    assert "commande_enrichissement" in SQL_UPSERT
    assert "UPDATE achat.commande" not in SQL_UPSERT
    assert "UPDATE achat.qualite" not in SQL_UPSERT


def test_po_normalises_des_deux_cotes_de_la_jointure():
    """Sylob prefixe les PO de zeros, pas le fichier Excel : sans LTRIM, zero match."""
    assert SQL_RECEPTIONS.count("LTRIM(TRIM(") >= 2


def test_upsert_idempotent():
    """Rejouer le module ne doit pas creer de doublon ni toucher aux lignes inchangees."""
    assert "ON CONFLICT (po_number, code_article) DO UPDATE" in SQL_UPSERT
    assert "IS DISTINCT FROM" in SQL_UPSERT


def test_enrich_receptions_sylob_compte_les_ecritures():
    lignes = [
        {"po_number": "174471", "date_reception_sylob": "2026-04-21"},
        {"po_number": "166222", "date_reception_sylob": "2026-04-16"},
    ]
    engine, conn = _mock_engine(lignes)
    with patch("src.scripts.etl.enrich_reception_sylob.get_engine", return_value=engine):
        stats = enrich_receptions_sylob()
    assert stats == {"receptions_lues": 2, "enrichissements_ecrits": 2}
    # 1 SELECT + 2 UPSERT
    assert conn.execute.call_count == 3


def test_dry_run_nexecute_aucune_ecriture():
    engine, conn = _mock_engine([{"po_number": "174471", "date_reception_sylob": "2026-04-21"}])
    with patch("src.scripts.etl.enrich_reception_sylob.get_engine", return_value=engine):
        stats = enrich_receptions_sylob(dry_run=True)
    assert stats["enrichissements_ecrits"] == 0
    assert conn.execute.call_count == 1  # le SELECT seulement


def test_statuts_figes_proteges_de_la_reprojection():
    """Une commande annulee ou deja payee ne doit jamais repasser a Livree."""
    for statut in ("Annulée", "Payée", "CLOTUREE"):
        assert statut in mod_apply.SQL_STATUTS_FIGES
    assert mod_apply.SQL_STATUTS_FIGES in mod_apply.SQL_COMMANDE


def test_reprojection_protegee_par_is_distinct_from():
    """Sans ce garde-fou, updated_at remonte sur toute la table a chaque nuit."""
    assert mod_apply.SQL_COMMANDE.count("IS DISTINCT FROM") >= 2
    assert mod_apply.SQL_QUALITE.count("IS DISTINCT FROM") >= 2
