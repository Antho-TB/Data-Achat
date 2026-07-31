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

from src.scripts.gmail.parse_facture import _normaliser

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
