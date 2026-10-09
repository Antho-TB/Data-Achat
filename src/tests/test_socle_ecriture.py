# -*- coding: utf-8 -*-
"""
[TEST]
Socle d'ecriture FUSEAU (phase d'ecriture, 08/10/2026) : identifiant d'artwork,
concurrence optimiste, liste blanche des champs, domaine eteint par defaut,
reprise du gsheet.
"""
from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.ecriture import ConflitVersion, LigneIntrouvable, identifiant_artwork, modifier
from src.scripts.etl.reprise_artwork_gsheet import convertir

JOUR = date(2026, 10, 8)


# ------------------------------------------------------------ identifiant
def test_identifiant_article_et_date():
    assert identifiant_artwork("32030006", JOUR, []) == "32030006-20261008"


def test_identifiant_suffixe_si_meme_article_meme_jour():
    pris = ["32030006-20261008", "32030006-20261008-2"]
    assert identifiant_artwork("32030006", JOUR, pris) == "32030006-20261008-3"


def test_identifiant_sans_reference():
    assert identifiant_artwork(None, JOUR, []) == "NOUVEAU-20261008"


# ------------------------------------------------------------ modifier
class _Resultat:
    def __init__(self, ligne: dict[str, Any] | None) -> None:
        self._ligne = ligne

    def mappings(self) -> "_Resultat":
        return self

    def first(self) -> dict[str, Any] | None:
        return self._ligne

    def one(self) -> dict[str, Any]:
        assert self._ligne is not None
        return self._ligne


class _ConnFactice:
    """Connexion minimale : renvoie la ligne en base au SELECT, applique l'UPDATE."""

    def __init__(self, ligne: dict[str, Any] | None) -> None:
        self.ligne = ligne
        self.requetes: list[str] = []

    def execute(self, requete: Any, params: dict[str, Any] | None = None) -> _Resultat:
        sql = str(requete)
        self.requetes.append(sql)
        if sql.lstrip().startswith("SELECT"):
            return _Resultat(self.ligne)
        if sql.lstrip().startswith("UPDATE"):
            nouvelle = {**self.ligne, **{k: v for k, v in params.items() if not k.startswith("_")}}
            nouvelle["version"] = self.ligne["version"] + 1
            return _Resultat(nouvelle)
        return _Resultat(None)  # INSERT du journal


LIGNE = {"identifiant": "32030006-20261008", "designation": "Coffret", "priorite": 3,
         "version": 2, "maj_par": "clarisse@tb-groupe.fr"}


def test_conflit_si_la_version_a_change():
    conn = _ConnFactice(dict(LIGNE))
    with pytest.raises(ConflitVersion) as exc:
        modifier(conn, "artwork_fuseau", "identifiant", LIGNE["identifiant"], {"priorite": 1},
                 version_attendue=1, auteur="maxence", champs_autorises=["priorite"])
    assert exc.value.actuelle["maj_par"] == "clarisse@tb-groupe.fr"
    assert not any(r.lstrip().startswith("UPDATE") for r in conn.requetes)


def test_champ_non_autorise_refuse():
    with pytest.raises(ValueError):
        modifier(_ConnFactice(dict(LIGNE)), "artwork_fuseau", "identifiant", "x", {"statut": "archive"},
                 version_attendue=2, auteur="maxence", champs_autorises=["priorite"])


def test_ligne_introuvable():
    with pytest.raises(LigneIntrouvable):
        modifier(_ConnFactice(None), "artwork_fuseau", "identifiant", "x", {"priorite": 1},
                 version_attendue=1, auteur="maxence", champs_autorises=["priorite"])


def test_modification_journalisee_et_version_incrementee():
    conn = _ConnFactice(dict(LIGNE))
    ligne = modifier(conn, "artwork_fuseau", "identifiant", LIGNE["identifiant"], {"priorite": 1},
                     version_attendue=2, auteur="maxence", champs_autorises=["priorite"])
    assert ligne["priorite"] == 1 and ligne["version"] == 3
    assert any("journal_modification" in r for r in conn.requetes)


def test_sans_changement_reel_rien_n_est_ecrit():
    conn = _ConnFactice(dict(LIGNE))
    modifier(conn, "artwork_fuseau", "identifiant", LIGNE["identifiant"], {"priorite": 3},
             version_attendue=2, auteur="maxence", champs_autorises=["priorite"])
    assert not any(r.lstrip().startswith("UPDATE") or "journal_modification" in r for r in conn.requetes)


def test_table_hors_liste_blanche_refusee():
    with pytest.raises(ValueError):
        modifier(_ConnFactice(dict(LIGNE)), "commande", "id", 1, {"statut": "x"},
                 version_attendue=2, auteur="x", champs_autorises=["statut"])


# ------------------------------------------------------------ domaine eteint
def test_domaine_artwork_eteint_par_defaut(monkeypatch):
    from src.utils.config_manager import Config
    monkeypatch.setattr(Config, "ECRITURE_ARTWORK", False)
    monkeypatch.setattr(Config, "AUTH_MODE", "entra")
    import app.main as m
    client = TestClient(m.app)
    assert client.get("/api/artworks/mode").json() == {"ecriture": False}
    r = client.post("/api/artworks", json={"designation": "Test"},
                    headers={"X-MS-CLIENT-PRINCIPAL-NAME": "a.bezille@tb-groupe.fr"})
    assert r.status_code == 409


# ------------------------------------------------------------ reprise
def test_reprise_ligne_en_attente_sans_reference():
    ids: set[str] = set()
    a = convertir({"code_article": "NOUVEAU-BLOC-A-COUTEAUX", "designation": "BLOC A COUTEAUX",
                   "statut_artwork": "En attente", "priorite": 3, "valideur": "Clarisse",
                   "commentaire_andrea": "Création", "commentaire_clarisse_thomas": "en attente photos",
                   "date_demande": None, "derniere_version": None, "date_validation": None}, ids, JOUR)
    assert a["identifiant"] == "NOUVEAU-20261008" and a["code_article"] is None
    assert (a["statut"], a["commentaire_acheteur"], a["valide_le"]) == ("en_attente", "Création", None)


def test_reprise_ligne_validee_datee_par_sa_derniere_version():
    ids: set[str] = set()
    a = convertir({"code_article": "402010", "designation": "M24 LAG METAL", "statut_artwork": "Validé",
                   "valideur": "Clarisse", "commentaire": "Version 2026", "date_demande": None,
                   "derniere_version": date(2026, 8, 24), "date_validation": date(2026, 8, 24)}, ids, JOUR)
    assert a["identifiant"] == "402010-20260824"
    assert (a["statut"], a["valide_par"], a["commentaire_version"]) == ("valide", "Clarisse", "Version 2026")
