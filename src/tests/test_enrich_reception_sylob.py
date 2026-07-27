"""
Tests unitaires du module de rapprochement des réceptions physiques réelles Sylob.
"""

from unittest.mock import MagicMock, patch
from src.scripts.etl.enrich_reception_sylob import enrich_receptions_sylob


def test_enrich_receptions_sylob_structure():
    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_engine.connect.return_value.__enter__.return_value = mock_conn

    res_cmd_mock = MagicMock()
    res_cmd_mock.rowcount = 47
    res_q_mock = MagicMock()
    res_q_mock.rowcount = 46

    mock_conn.execute.side_effect = [res_cmd_mock, res_q_mock]

    with patch("src.scripts.etl.enrich_reception_sylob.get_engine", return_value=mock_engine):
        stats = enrich_receptions_sylob()
        assert stats["commandes_mises_a_jour"] == 47
        assert stats["qualite_mises_a_jour"] == 46
        assert mock_conn.commit.called
