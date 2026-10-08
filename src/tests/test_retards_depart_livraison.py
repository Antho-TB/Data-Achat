# -*- coding: utf-8 -*-
"""
[TEST]
Retard de depart et retard de livraison separes (decision d'Antho, 08/10/2026).

Avant : "en retard" = ETD depasse et pas livre. Une marchandise en mer, dans les
temps, comptait en retard des le lendemain de son ETD (43 lignes sur 55 au 08/10).
La regle est calculee dans l'API (SQL_V_PREVISIONNEL), la vue achat.v_previsionnel
appartenant a platform_team.
"""
import app.main as m


def test_statut_retard_suit_la_nouvelle_regle():
    assert "v.est_retard " in m.SQL_STATUT_RETARD
    assert "est_en_retard" not in m.SQL_STATUT_RETARD


def test_relation_enrichie_definit_les_deux_retards():
    sql = m.SQL_V_PREVISIONNEL
    for col in ("AS est_retard_depart", "AS est_retard_livraison", "AS est_retard", "AS eta_eff"):
        assert col in sql
    # L'ETA du suivi maritime prime sur celle de l'IMPORT.
    assert "COALESCE(vp_ot.eta, vp_c.eta) < CURRENT_DATE" in m._SQL_RETARD_LIVRAISON
    # Une marchandise partie n'est jamais en retard de depart.
    assert "'En cours de livraison'" in m._SQL_RETARD_DEPART
    assert "etd_reel IS NULL" in m._SQL_RETARD_DEPART


def test_l_ancienne_colonne_de_la_vue_n_est_plus_lue():
    import inspect
    source = inspect.getsource(m)
    assert "v.est_en_retard" not in source
