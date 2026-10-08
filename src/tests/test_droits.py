# -*- coding: utf-8 -*-
"""
[TEST]
Droits par onglet (roles Entra, 08/10/2026) : lecture du principal Easy Auth,
profils, couverture de toutes les routes /api, blocage et masquage des montants.
"""
import base64
import json

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.droits import (PUBLIC, REGLES, droits_depuis_roles, masquer_montants, regle_pour,
                        roles_du_principal)

ROLE_TYP = "http://schemas.microsoft.com/ws/2008/06/identity/claims/role"


def principal(*roles: str, role_typ: str = ROLE_TYP, typ: str | None = None) -> str:
    claims = [{"typ": typ or role_typ, "val": r} for r in roles]
    claims.append({"typ": "name", "val": "clarisse@tb-groupe.fr"})
    return base64.b64encode(json.dumps({"auth_typ": "aad", "role_typ": role_typ,
                                        "claims": claims}).encode()).decode()


def entetes(*roles: str) -> dict[str, str]:
    return {"X-MS-CLIENT-PRINCIPAL-NAME": "clarisse@tb-groupe.fr",
            "X-MS-CLIENT-PRINCIPAL": principal(*roles)}


# ------------------------------------------------------------ principal
def test_roles_lus_sous_role_typ_et_sous_roles():
    assert roles_du_principal(principal("Design")) == {"Design"}
    assert roles_du_principal(principal("Achats", typ="roles")) == {"Achats"}


def test_principal_illisible_donne_zero_role():
    assert roles_du_principal("pas du base64 !") == frozenset()
    assert roles_du_principal("") == frozenset()


# ------------------------------------------------------------ profils
def test_profil_design_sans_montants():
    d = droits_depuis_roles("clarisse", frozenset({"Design"}))
    assert d.onglets == {"artwork", "article", "fiche"} and not d.montants


def test_roles_cumules():
    d = droits_depuis_roles("x", frozenset({"Design", "Achats", "Artwork.Archiver"}))
    assert d.montants and "previsionnel" in d.onglets and "artwork.archiver" in d.permissions


def test_role_inconnu_aucun_onglet():
    assert droits_depuis_roles("x", frozenset({"Inconnu"})).onglets == frozenset()


# ------------------------------------------------------------ montants
def test_masquage_montants_recursif():
    donnees = {"designation": "Coffret", "prix_unitaire": 1.2, "valideur": "Clarisse",
               "historique_prix": [{"prix": 3}],
               "lignes": [{"montant_bl": 10, "qte": 4, "total_prix": 40}]}
    assert masquer_montants(donnees) == {"designation": "Coffret", "valideur": "Clarisse",
                                         "lignes": [{"qte": 4}]}


# ------------------------------------------------------------ couverture
def test_chaque_route_api_a_une_regle():
    import app.main as m
    manquantes = []
    for route in m.app.routes:
        if not isinstance(route, APIRoute) or not route.path.startswith("/api/"):
            continue
        chemin = route.path.replace("{", "").replace("}", "")  # {po_number} -> po_number
        for methode in route.methods:
            if regle_pour(methode, chemin) is None:
                manquantes.append(f"{methode} {route.path}")
    assert not manquantes, f"Routes sans regle de droits (app/droits.py) : {manquantes}"


def test_seule_la_sonde_et_moi_sont_publiques():
    publiques = {motif.pattern for _, motif, regle in REGLES if regle == PUBLIC}
    assert publiques == {r"^/api/health$", r"^/api/moi$"}


# ------------------------------------------------------------ middleware
@pytest.fixture
def client(monkeypatch):
    """App minimale avec le vrai middleware : pas de base de donnees."""
    import app.main as m
    from src.utils.config_manager import Config
    monkeypatch.setattr(Config, "AUTH_MODE", "entra")
    monkeypatch.setattr(Config, "DROITS_MODE", "bloquant")
    app = FastAPI()
    app.middleware("http")(m.controler_droits)
    app.get("/api/moi")(m.get_moi)
    app.get("/api/previsionnel")(lambda: {"montant": 1})
    app.get("/api/produit/{code}")(lambda code: {"code": code, "prix_unitaire": 2.5})
    app.get("/api/inconnue")(lambda: {"ok": True})
    app.post("/api/artworks/{i}/archiver")(lambda i: {"ok": i})
    return TestClient(app)


def test_onglet_hors_profil_refuse(client):
    assert client.get("/api/previsionnel", headers=entetes("Design")).status_code == 403


def test_montants_masques_pour_design(client):
    r = client.get("/api/produit/402010", headers=entetes("Design"))
    assert r.status_code == 200 and r.json() == {"code": "402010"}


def test_montants_visibles_pour_achats(client):
    assert client.get("/api/produit/402010", headers=entetes("Achats")).json()["prix_unitaire"] == 2.5


def test_route_non_declaree_refusee(client):
    assert client.get("/api/inconnue", headers=entetes("Achats")).status_code == 403


def test_archivage_reserve_a_la_permission(client):
    assert client.post("/api/artworks/a/archiver", headers=entetes("Achats")).status_code == 403
    assert client.post("/api/artworks/a/archiver",
                       headers=entetes("Achats", "Artwork.Archiver")).status_code == 200


def test_moi_repond_meme_sans_profil(client):
    r = client.get("/api/moi", headers=entetes())
    assert r.status_code == 200 and r.json()["onglets"] == []


def test_moi_garde_le_drapeau_montants(client):
    assert client.get("/api/moi", headers=entetes("Design")).json()["montants"] is False


def test_mode_journal_ne_bloque_ni_ne_masque(client, monkeypatch):
    from src.utils.config_manager import Config
    monkeypatch.setattr(Config, "DROITS_MODE", "journal")
    assert client.get("/api/previsionnel", headers=entetes("Design")).status_code == 200
    assert client.get("/api/produit/1", headers=entetes("Design")).json()["prix_unitaire"] == 2.5
    assert client.get("/api/moi", headers=entetes("Design")).json()["onglets_profil"] == [
        "article", "artwork", "fiche"]


def test_poste_metier_sans_controle(client, monkeypatch):
    from src.utils.config_manager import Config
    monkeypatch.setattr(Config, "AUTH_MODE", "apikey")
    assert client.get("/api/previsionnel").status_code == 200


def test_faute_de_frappe_vaut_bloquant(client, monkeypatch):
    from src.utils.config_manager import Config
    monkeypatch.setattr(Config, "DROITS_MODE", "jounral")
    assert client.get("/api/previsionnel", headers=entetes("Design")).status_code == 403
