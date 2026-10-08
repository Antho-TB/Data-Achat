# -*- coding: utf-8 -*-
"""
[TEST] Garde-fou de scopes OAuth Google (src/utils/google_auth.py)

Cause racine de l'ETL Gmail mort du 22/07 au 06/08/2026 : token.json portait 2
scopes, SCOPES en demandait 3, et Google refusait chaque refresh par un
"RefreshError: invalid_scope" opaque. Ces tests verrouillent que l'ecart est
detecte AVANT le refresh, avec un message actionnable, et qu'aucun appelant ne
l'avale. Aucun appel reseau : tokens factices dans tmp_path, refresh simule.

Junior Tip : on monkeypatche Credentials.refresh plutot que d'appeler Google.
Un test qui depend du reseau ou d'un vrai compte est un test qui ment le jour
ou le VPN tombe.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest
from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials

from src.scripts.gmail import preflight_gmail
from src.utils import google_auth, gsheets
from src.utils.google_auth import (
    COMMANDE_RECONSENTEMENT,
    SCOPES,
    ScopesInsuffisantsError,
    get_credentials,
    lire_scopes_token,
    scopes_manquants,
    verifier_scopes_token,
)

SCOPE_SHEETS = "https://www.googleapis.com/auth/spreadsheets.readonly"
DEUX_SCOPES = [s for s in SCOPES if s != SCOPE_SHEETS]


def _ecrire_token(dossier: Path, scopes: object, expire: bool = True) -> Path:
    """Ecrit un token.json factice (expire par defaut pour forcer le refresh)."""
    contenu: dict[str, object] = {
        "token": "faux-access-token",
        "refresh_token": "faux-refresh-token",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "faux-client.apps.googleusercontent.com",
        "client_secret": "faux-secret",
        "expiry": "2020-01-01T00:00:00Z" if expire else "2999-01-01T00:00:00Z",
    }
    if scopes is not None:
        contenu["scopes"] = scopes
    chemin = dossier / "token.json"
    chemin.write_text(json.dumps(contenu), encoding="utf-8")
    return chemin


# ===========================================================================
# LECTURE ET COMPARAISON DES SCOPES
# ===========================================================================
def test_lire_scopes_token_liste_chaine_absent(tmp_path: Path) -> None:
    assert lire_scopes_token(_ecrire_token(tmp_path, DEUX_SCOPES)) == DEUX_SCOPES
    assert lire_scopes_token(_ecrire_token(tmp_path, " ".join(SCOPES))) == SCOPES
    assert lire_scopes_token(_ecrire_token(tmp_path, None)) is None


def test_scopes_manquants() -> None:
    assert scopes_manquants(DEUX_SCOPES) == [SCOPE_SHEETS]
    assert scopes_manquants(SCOPES) == []
    assert scopes_manquants(None) == []


def test_verifier_scopes_token_leve_avec_message_actionnable(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    token = _ecrire_token(tmp_path, DEUX_SCOPES)
    with caplog.at_level(logging.ERROR, logger=google_auth.__name__):
        with pytest.raises(ScopesInsuffisantsError) as exc:
            verifier_scopes_token(token)
    assert exc.value.manquants == [SCOPE_SHEETS]
    assert exc.value.token_path == token
    message = str(exc.value)
    assert SCOPE_SHEETS in message
    assert COMMANDE_RECONSENTEMENT in message
    assert any("[ECHEC]" in r.getMessage() for r in caplog.records)


def test_verifier_scopes_token_ok(tmp_path: Path) -> None:
    verifier_scopes_token(_ecrire_token(tmp_path, SCOPES))


def test_scopes_insuffisants_est_une_runtime_error() -> None:
    assert issubclass(ScopesInsuffisantsError, RuntimeError)


def test_aucun_tiret_cadratin_dans_le_message(tmp_path: Path) -> None:
    erreur = ScopesInsuffisantsError([SCOPE_SHEETS], tmp_path / "token.json")
    assert chr(0x2014) not in str(erreur)


# ===========================================================================
# get_credentials : garde-fou avant refresh + ceinture invalid_scope
# ===========================================================================
def test_get_credentials_bloque_avant_refresh(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = _ecrire_token(tmp_path, DEUX_SCOPES)
    appels: list[object] = []
    monkeypatch.setattr(Credentials, "refresh", lambda self, req: appels.append(req))

    with pytest.raises(ScopesInsuffisantsError):
        get_credentials(tmp_path / "credentials.json", token)
    assert appels == [], "le refresh ne doit jamais etre tente sur un token incomplet"


def test_get_credentials_bloque_meme_si_token_non_expire(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = _ecrire_token(tmp_path, DEUX_SCOPES, expire=False)
    with pytest.raises(ScopesInsuffisantsError):
        get_credentials(tmp_path / "credentials.json", token)


def test_get_credentials_traduit_refresh_invalid_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = _ecrire_token(tmp_path, SCOPES)

    def _refus(self: Credentials, req: object) -> None:
        raise RefreshError("invalid_scope: Bad Request", {"error": "invalid_scope"})

    monkeypatch.setattr(Credentials, "refresh", _refus)
    with pytest.raises(ScopesInsuffisantsError) as exc:
        get_credentials(tmp_path / "credentials.json", token)
    assert isinstance(exc.value.__cause__, RefreshError)
    assert COMMANDE_RECONSENTEMENT in str(exc.value)


def test_get_credentials_laisse_passer_les_autres_refresh_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = _ecrire_token(tmp_path, SCOPES)

    def _revoque(self: Credentials, req: object) -> None:
        raise RefreshError("invalid_grant: Token has been expired or revoked.")

    monkeypatch.setattr(Credentials, "refresh", _revoque)
    with pytest.raises(RefreshError) as exc:
        get_credentials(tmp_path / "credentials.json", token)
    assert not isinstance(exc.value, ScopesInsuffisantsError)


def test_get_credentials_refresh_ok_reecrit_le_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = _ecrire_token(tmp_path, SCOPES)

    def _ok(self: Credentials, req: object) -> None:
        self.token = "nouveau-access-token"
        self.expiry = None  # pas d'expiry = considere valide

    monkeypatch.setattr(Credentials, "refresh", _ok)
    creds = get_credentials(tmp_path / "credentials.json", token)
    assert creds.token == "nouveau-access-token"
    assert json.loads(token.read_text(encoding="utf-8"))["scopes"] == SCOPES


# ===========================================================================
# APPELANTS : preflight et gsheets ne doivent pas masquer l'erreur
# ===========================================================================
def test_preflight_check_gmail_token_statuts(tmp_path: Path) -> None:
    credentials = tmp_path / "credentials.json"
    credentials.write_text("{}", encoding="utf-8")
    absent = tmp_path / "absent.json"

    assert preflight_gmail.check_gmail_token(absent, credentials) == preflight_gmail.STATUT_CONSENTEMENT
    token = _ecrire_token(tmp_path, DEUX_SCOPES)
    assert preflight_gmail.check_gmail_token(token, credentials) == preflight_gmail.STATUT_CONSENTEMENT
    token = _ecrire_token(tmp_path, SCOPES)
    assert preflight_gmail.check_gmail_token(token, credentials) == preflight_gmail.STATUT_OK
    token.write_text("pas du json", encoding="utf-8")
    assert preflight_gmail.check_gmail_token(token, credentials) == preflight_gmail.STATUT_KO
    assert preflight_gmail.check_gmail_token(token, absent) == preflight_gmail.STATUT_KO


@pytest.mark.parametrize(
    ("statut_token", "dwh_ok", "attendu"),
    [
        ("ok", True, 0),
        ("consentement", True, 3),
        ("consentement", False, 3),  # le reconsentement prime sur un VPN tombe
        ("ok", False, 1),
        ("ko", True, 1),
    ],
)
def test_preflight_main_codes_de_sortie(
    monkeypatch: pytest.MonkeyPatch, statut_token: str, dwh_ok: bool, attendu: int
) -> None:
    monkeypatch.setattr(preflight_gmail, "check_binary", lambda name, cmd: True)
    monkeypatch.setattr(preflight_gmail, "check_python_version", lambda: True)
    monkeypatch.setattr(preflight_gmail, "check_git_sync", lambda: True)
    monkeypatch.setattr(preflight_gmail, "check_dwh", lambda: dwh_ok)
    monkeypatch.setattr(preflight_gmail, "check_gmail_token", lambda: statut_token)
    assert preflight_gmail.main() == attendu


def test_gsheets_ne_masque_pas_le_scope_insuffisant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _leve(*args: object, **kwargs: object) -> None:
        raise ScopesInsuffisantsError([SCOPE_SHEETS], tmp_path / "token.json")

    # read_sheet_values renvoyait [] sur toute exception : un scope manquant
    # aurait ete pris pour un onglet vide.
    monkeypatch.setattr(gsheets, "get_sheets_service", _leve)
    with pytest.raises(ScopesInsuffisantsError):
        gsheets.read_sheet_values("id", "A1:B2")

    monkeypatch.setattr(gsheets, "list_tabs", _leve)
    with pytest.raises(ScopesInsuffisantsError):
        gsheets.read_all_tabs("id")

    monkeypatch.setattr(gsheets, "_service_drive", _leve)
    with pytest.raises(ScopesInsuffisantsError):
        gsheets.metadonnees_drive("id")


def test_sha_distant_branche_et_tag_annote() -> None:
    """Le preflight compare HEAD au commit vise, y compris derriere un tag annote."""
    sortie = (
        "aaa\trefs/heads/feature/main\n"
        "bbb\trefs/heads/main\n"
        "ccc\trefs/tags/v1\n"
        "ddd\trefs/tags/v1^{}\n"
    )
    assert preflight_gmail.sha_distant(sortie, "main") == "bbb"
    assert preflight_gmail.sha_distant(sortie, "v1") == "ddd"
    assert preflight_gmail.sha_distant(sortie, "absente") is None
