# -*- coding: utf-8 -*-
"""
[TEST]
=============================================================================
NORMALISATION DES PIECES COMPTABLES EXTRAITES DES PJ GMAIL
=============================================================================

Ces tests ne touchent PAS au modele : ils portent sur la normalisation, c'est a
dire sur les regles que le code doit garantir quoi qu'ait repondu le modele. Un
test qui appellerait l'API verifierait surtout que Google repond, ce qui ne dit
rien de notre logique et coute un appel a chaque execution.

Les trois regles couvertes viennent du retour de Marlene du 29/07 et du schema
de achat.facture_fournisseur :
  1. une note de credit est stockee en NEGATIF, meme si le document et le modele
     l'annoncent en positif (sinon on la compte comme une somme a payer) ;
  2. les PO sont completes a 8 chiffres, sinon la jointure sur achat.commande
     ne retrouve rien ;
  3. un type de piece inconnu retombe sur 'facture' plutot que de faire echouer
     la contrainte CHECK au moment de l'insertion.
"""
from pathlib import Path

import pytest

from src.scripts.gmail import parse_facture as pf
from src.scripts.gmail.parse_facture import _normaliser
from src.utils.config_manager import Config

MODELE = "models/gemini-3.5-flash"
FICHIER = Path("facture_hongxing.pdf")


def test_note_de_credit_forcee_en_negatif() -> None:
    """Une note de credit rendue en positif par le modele doit devenir negative."""
    piece = _normaliser(
        {"type_piece": "note_credit", "montant": 250.0, "devise": "USD"},
        FICHIER, MODELE)
    assert piece["montant"] == -250.0
    assert piece["type_piece"] == "note_credit"


def test_note_de_credit_deja_negative_inchangee() -> None:
    """Le signe correct ne doit pas etre inverse une seconde fois."""
    piece = _normaliser(
        {"type_piece": "note_credit", "montant": -250.0}, FICHIER, MODELE)
    assert piece["montant"] == -250.0


def test_facture_reste_positive() -> None:
    """Une facture garde son signe : la correction ne vise que les notes de credit."""
    piece = _normaliser(
        {"type_piece": "facture", "montant": 6403.20, "devise": "EUR"},
        FICHIER, MODELE)
    assert piece["montant"] == 6403.20
    assert piece["devise"] == "EUR"


def test_po_completes_a_huit_chiffres() -> None:
    """17281 doit devenir 00017281, sinon la jointure sur commande ne trouve rien."""
    piece = _normaliser(
        {"type_piece": "facture", "montant": 10.0,
         "po_numbers": ["17281", " 00017639 ", ""]},
        FICHIER, MODELE)
    assert piece["po_numbers"] == ["00017281", "00017639"]


def test_type_inconnu_retombe_sur_facture() -> None:
    """Un type hors nomenclature ne doit pas faire echouer la contrainte CHECK."""
    piece = _normaliser(
        {"type_piece": "bon de livraison", "montant": 10.0}, FICHIER, MODELE)
    assert piece["type_piece"] == "facture"


def test_montant_absent_reste_absent() -> None:
    """Aucune valeur inventee : un montant illisible reste None."""
    piece = _normaliser({"type_piece": "facture", "montant": None}, FICHIER, MODELE)
    assert piece["montant"] is None


def test_tracabilite_de_la_source() -> None:
    """Le fichier et le modele doivent toujours accompagner le chiffre."""
    piece = _normaliser(
        {"type_piece": "facture", "montant": 10.0, "confiance": 0.42,
         "libelle_montant_lu": "TOTAL AMOUNT EUR"},
        FICHIER, MODELE)
    assert piece["source_fichier"] == "facture_hongxing.pdf"
    assert piece["methode_extraction"] == f"llm:{MODELE}"
    assert piece["confiance"] == 0.42
    assert piece["texte_source"] == "TOTAL AMOUNT EUR"


def test_devise_absente_non_devinee() -> None:
    """Pas de devise par defaut : une facture sans devise lisible rend None."""
    piece = _normaliser({"type_piece": "facture", "montant": 10.0}, FICHIER, MODELE)
    assert piece["devise"] is None


# ===========================================================================
# BORNES DE TEMPS SUR L'APPEL AU MODELE
# ===========================================================================
# Ajoute apres la mesure du 06/08/2026 : un PDF de 0,4 Mo avait fige le lot plus
# de 4 minutes, faute de timeout. Le client est simule, donc ces tests ne
# consomment aucun appel : ils verifient QUI est repris et QUI ne l'est pas.

class _FauxModeles:
    """Enregistre les appels et rejoue un comportement fourni par le test."""

    def __init__(self, comportement) -> None:
        self.appels = 0
        self.derniere_config = None
        self._comportement = comportement

    def generate_content(self, **kwargs):
        self.appels += 1
        self.derniere_config = kwargs.get("config")
        return self._comportement(self.appels)


class _FauxClient:
    def __init__(self, comportement) -> None:
        self.models = _FauxModeles(comportement)


class _FausseReponse:
    def __init__(self, text: str) -> None:
        self.text = text


@pytest.fixture
def piece_jointe(tmp_path: Path) -> Path:
    """Un fichier reel : _appel_modele lit les octets avant tout appel."""
    chemin = tmp_path / "facture_hongxing.pdf"
    chemin.write_bytes(b"%PDF-1.4 contenu factice")
    return chemin


@pytest.fixture(autouse=True)
def _sans_attente(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralise le backoff : on teste la logique, pas la patience."""
    monkeypatch.setattr(pf.time, "sleep", lambda _: None)


def test_reponse_non_json_jamais_reprise(piece_jointe: Path) -> None:
    """
    Une mauvaise reponse ne se repare pas en reessayant.

    La temperature est nulle : le meme document redonnerait exactement la meme
    reponse. Reprendre ne ferait que payer trois fois la meme erreur.
    """
    client = _FauxClient(lambda _: _FausseReponse("ceci n'est pas du json"))
    with pytest.raises(ValueError):
        pf._appel_modele(client, piece_jointe, MODELE)
    assert client.models.appels == 1


def test_reponse_vide_jamais_reprise(piece_jointe: Path) -> None:
    """Meme raison : une reponse vide est un verdict, pas un incident reseau."""
    client = _FauxClient(lambda _: _FausseReponse(""))
    with pytest.raises(ValueError):
        pf._appel_modele(client, piece_jointe, MODELE)
    assert client.models.appels == 1


def test_panne_de_transport_reprise_puis_timeout(piece_jointe: Path) -> None:
    """Une panne reseau persistante consomme les tentatives puis leve."""
    def toujours_en_panne(_):
        raise ConnectionError("connexion reinitialisee")

    client = _FauxClient(toujours_en_panne)
    with pytest.raises(TimeoutError):
        pf._appel_modele(client, piece_jointe, MODELE)
    assert client.models.appels == Config.GEMINI_TENTATIVES


def test_panne_passagere_puis_succes(piece_jointe: Path) -> None:
    """Le cas qui justifie la reprise : le second essai passe."""
    def en_panne_puis_ok(appel: int):
        if appel == 1:
            raise ConnectionError("503 service indisponible")
        return _FausseReponse('{"est_piece_comptable": true, '
                              '"type_piece": "facture", "confiance": 0.9}')

    client = _FauxClient(en_panne_puis_ok)
    donnees = pf._appel_modele(client, piece_jointe, MODELE)
    assert donnees["confiance"] == 0.9
    assert client.models.appels == 2


def test_le_modele_d_escalade_recoit_un_timeout_plus_long(
        piece_jointe: Path) -> None:
    """
    Le modele lourd est plus lent : lui imposer le timeout standard le tuerait.

    Ce test verrouille le branchement entre le nom du modele et la borne de temps,
    qui est exactement le genre de fil qu'un refactoring coupe sans bruit.
    """
    reponse = '{"est_piece_comptable": false, "type_piece": "facture", "confiance": 0.1}'

    standard = _FauxClient(lambda _: _FausseReponse(reponse))
    pf._appel_modele(standard, piece_jointe, Config.MODELE_FACTURE)
    assert (standard.models.derniere_config.http_options.timeout
            == Config.GEMINI_TIMEOUT_MS)

    escalade = _FauxClient(lambda _: _FausseReponse(reponse))
    pf._appel_modele(escalade, piece_jointe, Config.MODELE_FACTURE_ESCALADE)
    assert (escalade.models.derniere_config.http_options.timeout
            == Config.GEMINI_TIMEOUT_ESCALADE_MS)
    assert (Config.GEMINI_TIMEOUT_ESCALADE_MS > Config.GEMINI_TIMEOUT_MS)
