# -*- coding: utf-8 -*-
"""[TEST] Sondes de fraicheur des sources et de droits MyReport (app/sondes.py)."""
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone

from app.sondes import SONDES, mesurer_sources, statut_fraicheur

MAINTENANT = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)


def test_source_recente_ok() -> None:
    assert statut_fraicheur(MAINTENANT - timedelta(hours=10), 48, MAINTENANT) == ("ok", 10.0)


def test_source_figee_en_retard() -> None:
    """Cas receptions_detaillees2 : analysee pour la derniere fois le 04/08."""
    statut, age = statut_fraicheur(datetime(2026, 8, 4, tzinfo=timezone.utc), 48, MAINTENANT)
    assert statut == "en_retard" and age > 48


def test_table_jamais_alimentee_vide_pas_ok() -> None:
    assert statut_fraicheur(None, 48, MAINTENANT) == ("vide", None)


def test_horodatage_sans_fuseau_lu_en_utc() -> None:
    naif = (MAINTENANT - timedelta(hours=3)).replace(tzinfo=None)
    assert statut_fraicheur(naif, 48, MAINTENANT) == ("ok", 3.0)


class _ConnEnPanne:
    """Connexion dont chaque requete echoue (droit retire, table renommee)."""

    def begin_nested(self):
        return nullcontext()

    def execute(self, *_args, **_kwargs):
        raise RuntimeError("permission denied for table articles3")


def test_sonde_illisible_ne_passe_jamais_ok() -> None:
    resultats = mesurer_sources(_ConnEnPanne())
    assert len(resultats) == len(SONDES)
    assert {r["statut"] for r in resultats} == {"illisible"}
