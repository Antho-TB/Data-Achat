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
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from src.scripts.etl import apply_enrichissement as mod_apply
from src.scripts.etl import enrich_reception_sylob as mod
from src.scripts.etl.enrich_reception_sylob import (
    SQL_RECEPTIONS_REPLI,
    SQL_RECEPTIONS_SYLOB,
    SQL_UPSERT,
    Reception,
    RepliIndisponibleError,
    rapprocher,
)


def test_ecrit_dans_la_table_denrichissement_et_pas_dans_commande():
    """Invariant central : achat.commande est full-refresh, on n'y touche pas."""
    assert "commande_enrichissement" in SQL_UPSERT
    assert "UPDATE achat.commande" not in SQL_UPSERT
    assert "UPDATE achat.qualite" not in SQL_UPSERT


@pytest.mark.parametrize("sql", [SQL_RECEPTIONS_SYLOB, SQL_RECEPTIONS_REPLI])
def test_sources_au_grain_article_et_sans_date_future(sql):
    """Grain (PO, article), PO sans zeros de tete, receptions futures ecartees."""
    assert "article_code_article" in sql
    assert "LTRIM(TRIM(commande_numero_de_la_commande), '0')" in sql
    assert "ligne_receptionnee_le <= CURRENT_DATE" in sql


def test_ne_lit_plus_la_table_figee():
    """receptions_detaillees2 est figee depuis le 04/08/2026."""
    assert "receptions_detaillees2" not in SQL_RECEPTIONS_SYLOB + SQL_RECEPTIONS_REPLI


def test_upsert_idempotent_au_grain_article():
    assert "ON CONFLICT (po_number, code_article) DO UPDATE" in SQL_UPSERT
    assert ":code_article" in SQL_UPSERT
    assert "IS DISTINCT FROM" in SQL_UPSERT


def _rec(po: str, art: str, creee: date | None, recu: date) -> Reception:
    return Reception(po=po, code_article=art, creee_le=creee, date_reception=recu)


def test_rapprocher_departage_les_po_homonymes_par_date_de_creation():
    """Le 18130 de GDD (2026) et celui de Cie (2014) : on garde le plus proche."""
    lignes = [{"po": "18130", "code_article": "A1", "date_commande": date(2026, 9, 1)}]
    recs = [_rec("18130", "A1", date(2014, 3, 1), date(2014, 11, 18)),
            _rec("18130", "A1", date(2026, 8, 28), date(2026, 9, 28))]
    out, rejets = rapprocher(lignes, recs)
    assert rejets == 0
    assert out == [{"po_number": "18130", "code_article": "A1",
                    "date_reception_sylob": date(2026, 9, 28)}]


def test_rapprocher_rejette_une_homonymie_seule():
    """Seule la commande Cie de 2014 existe : ce n'est pas notre commande."""
    lignes = [{"po": "18130", "code_article": "A1", "date_commande": date(2026, 9, 1)}]
    out, rejets = rapprocher(lignes, [_rec("18130", "A1", date(2014, 3, 1), date(2014, 11, 18))])
    assert out == [] and rejets == 1


def test_rapprocher_ne_marque_pas_les_autres_articles_du_po():
    """Defaut de l'ancienne version : un article recu marquait tout le PO livre."""
    lignes = [{"po": "1", "code_article": "A1", "date_commande": date(2026, 1, 1)},
              {"po": "1", "code_article": "A2", "date_commande": date(2026, 1, 1)}]
    out, _ = rapprocher(lignes, [_rec("1", "A1", date(2026, 1, 2), date(2026, 3, 1))])
    assert [o["code_article"] for o in out] == ["A1"]


def _engine_achat(lignes: list[dict]) -> tuple[MagicMock, MagicMock]:
    engine, conn = MagicMock(), MagicMock()
    engine.begin.return_value.__enter__.return_value = conn
    lecture = MagicMock()
    lecture.mappings.return_value = lignes
    upsert = MagicMock(rowcount=1)
    conn.execute.side_effect = [lecture] + [upsert] * 10
    return engine, conn


def test_enrich_ecrit_les_lignes_rapprochees():
    lignes = [{"po": "174471", "code_article": "A1", "date_commande": date(2026, 2, 1)}]
    engine, conn = _engine_achat(lignes)
    recs = [_rec("174471", "A1", date(2026, 2, 3), date(2026, 4, 21))]
    with patch.object(mod, "get_engine", return_value=engine),          patch.object(mod, "lire_receptions_sylob", return_value=recs):
        stats = mod.enrich_receptions_sylob()
    assert stats["lignes_rapprochees"] == 1
    assert stats["enrichissements_ecrits"] == 1
    assert conn.execute.call_count == 2  # lecture commandes + 1 upsert


def test_dry_run_nexecute_aucune_ecriture():
    lignes = [{"po": "174471", "code_article": "A1", "date_commande": date(2026, 2, 1)}]
    engine, conn = _engine_achat(lignes)
    recs = [_rec("174471", "A1", date(2026, 2, 3), date(2026, 4, 21))]
    with patch.object(mod, "get_engine", return_value=engine),          patch.object(mod, "lire_receptions_sylob", return_value=recs):
        stats = mod.enrich_receptions_sylob(dry_run=True)
    assert stats["enrichissements_ecrits"] == 0
    assert conn.execute.call_count == 1


def test_repli_myreport_si_sylob_injoignable():
    lignes = [{"po": "1", "code_article": "A1", "date_commande": date(2026, 2, 1)}]
    engine, _ = _engine_achat(lignes)
    recs = [_rec("1", "A1", date(2026, 2, 1), date(2026, 3, 1))]
    with patch.object(mod, "get_engine", return_value=engine),          patch.object(mod, "lire_receptions_sylob", side_effect=OSError("timeout")),          patch.object(mod, "lire_receptions_repli", return_value=recs) as repli:
        stats = mod.enrich_receptions_sylob(dry_run=True)
    repli.assert_called_once()
    assert stats["lignes_rapprochees"] == 1


def test_repli_refuse_une_copie_figee():
    """Copie MyReport figee : on leve plutot que de reprojeter des dates perimees."""
    conn = MagicMock()
    conn.execute.return_value.scalar.return_value = 62
    with pytest.raises(RepliIndisponibleError):
        mod.lire_receptions_repli(conn, ["1"])


def test_reprojection_en_deux_passes_po_puis_article():
    """L'article passe en dernier : la valeur la plus precise gagne toujours."""
    assert "e.code_article = ''" in mod_apply.SQL_COMMANDE[0]
    assert "e.code_article = c.code_article" in mod_apply.SQL_COMMANDE[1]
    assert "e.code_article = c.code_article" in mod_apply.SQL_QUALITE[1]


def test_statuts_figes_proteges_de_la_reprojection():
    """Une commande annulee ou deja payee ne doit jamais repasser a Livree."""
    for statut in ("Annulée", "Payée", "CLOTUREE"):
        assert statut in mod_apply.SQL_STATUTS_FIGES
    for sql in mod_apply.SQL_COMMANDE:
        assert mod_apply.SQL_STATUTS_FIGES in sql


def test_reprojection_protegee_par_is_distinct_from():
    """Sans ce garde-fou, updated_at remonte sur toute la table a chaque nuit."""
    for sql in mod_apply.SQL_COMMANDE + mod_apply.SQL_QUALITE:
        assert sql.count("IS DISTINCT FROM") >= 2
