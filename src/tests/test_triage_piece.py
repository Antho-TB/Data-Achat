# -*- coding: utf-8 -*-
"""
[TEST]
=============================================================================
TRI PREALABLE DES PIECES JOINTES (triage_piece.py)
=============================================================================

Ces tests ne lisent aucun PDF reel et n'appellent aucun modele : la couche texte
est injectee, de sorte que ce qui est teste est la REGLE DE DECISION, pas
pdfplumber. C'est la logique qui decide si on paie un appel, donc celle qui peut
faire perdre une facture.

Le test central est test_liasse_nom_expedition_mais_facture_dedans : il couvre la
seule facon dont ce module peut coûter de l'argent a TB Groupe, c'est-a-dire
ecarter une liasse dont le nom parle d'expedition alors qu'elle contient une
facture (cas JIT GLOBAL cite par Marlene le 29/07). Les autres tests verrouillent
le biais asymetrique : dans le doute, on paie.
"""
from pathlib import Path

import pytest

from src.scripts.gmail import triage_piece
from src.scripts.gmail.triage_piece import trier

# Texte assez long pour depasser SEUIL_TEXTE_EXPLOITABLE, sans aucun marqueur
# comptable : c'est la silhouette d'un connaissement.
TEXTE_BL = (
    "BILL OF LADING SHIPPER DONGGUAN SURPASS CONSIGNEE TARRERIAS BONJEAN "
    "NOTIFY PARTY PORT OF LOADING SHENZHEN PORT OF DISCHARGE FOS SUR MER "
    "VESSEL CMA CGM VOYAGE 0FL9NE1MA CONTAINER NO TGBU3898959 SEAL NO "
    "GROSS WEIGHT 12500 KGS FREIGHT PREPAID CY/CY SHIPPING MARKS N/M "
) * 2

TEXTE_LIASSE = TEXTE_BL + " COMMERCIAL INVOICE No HX-2607-118 TOTAL AMOUNT USD 6403.20"


@pytest.fixture(autouse=True)
def _sans_lecture_pdf(monkeypatch: pytest.MonkeyPatch) -> None:
    """Par defaut, aucun texte : equivaut a un scan ou a un fichier absent."""
    monkeypatch.setattr(triage_piece, "_texte_pdf", lambda chemin: "")


def _avec_texte(monkeypatch: pytest.MonkeyPatch, texte: str) -> None:
    monkeypatch.setattr(triage_piece, "_texte_pdf", lambda chemin: texte)


def test_nom_comptable_gagne_sur_gabarit_transitaire() -> None:
    """"Facture - Confirmation d'embarquement" est une facture, pas un avis."""
    verdict = trier(Path("Facture - Confirmation d'embarquement 202607.pdf"))
    assert verdict.decision == "a_analyser"
    assert verdict.etage == "nom"


def test_gabarit_transitaire_ecarte_si_texte_confirme(
        monkeypatch: pytest.MonkeyPatch) -> None:
    """Un BL dont le texte ne porte aucun marqueur comptable ne coute rien."""
    _avec_texte(monkeypatch, TEXTE_BL)
    verdict = trier(Path("BL-SZSE2606480-PACKING LIST.pdf"))
    assert verdict.decision == "non_comptable"
    assert verdict.etage == "nom"
    assert "confirme par la couche texte" in verdict.motif


def test_liasse_nom_expedition_mais_facture_dedans(
        monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Le test qui protege l'argent : nom d'expedition, facture a l'interieur.

    Un rejet sur le nom seul perdrait le montant sans erreur ni trace. La couche
    texte doit annuler le rejet des qu'un marqueur comptable apparait.
    """
    _avec_texte(monkeypatch, TEXTE_LIASSE)
    verdict = trier(Path("BL-SZSE2606480.pdf"))
    assert verdict.decision == "a_analyser"
    assert verdict.etage == "liasse"
    assert "marqueur comptable" in verdict.motif


def test_scan_sans_couche_texte_paye_l_appel() -> None:
    """Un PDF sans texte est un scan : c'est le coeur de cible du multimodal."""
    verdict = trier(Path("HONGXING_20260729.pdf"))
    assert verdict.decision == "a_analyser"
    assert verdict.etage == "defaut"


def test_texte_lisible_sans_marqueur_est_ecarte(
        monkeypatch: pytest.MonkeyPatch) -> None:
    """Nom neutre, texte lisible, aucun marqueur comptable : on n'appelle pas."""
    _avec_texte(monkeypatch, TEXTE_BL)
    verdict = trier(Path("document_20260729.pdf"))
    assert verdict.decision == "non_comptable"
    assert verdict.etage == "texte"


def test_texte_lisible_avec_marqueur_est_analyse(
        monkeypatch: pytest.MonkeyPatch) -> None:
    """Un IBAN ou un TOTAL AMOUNT suffit a declencher l'appel."""
    _avec_texte(monkeypatch, TEXTE_BL + " BANK DETAILS IBAN FR7630006000011234")
    verdict = trier(Path("document_20260729.pdf"))
    assert verdict.decision == "a_analyser"
    assert verdict.etage == "texte"


def test_jpeg_toujours_analyse() -> None:
    """Une photo de facture n'a pas de couche texte : elle doit etre payee."""
    verdict = trier(Path("IMG_4471.jpg"))
    assert verdict.decision == "a_analyser"
    assert verdict.etage == "defaut"


def test_extension_non_traitable_ecartee_sans_lecture() -> None:
    """Un .xlsx ou un .eml ne part jamais au modele multimodal."""
    assert trier(Path("recap.xlsx")).decision == "non_comptable"
    assert trier(Path("fil_de_mails.eml")).decision == "non_comptable"


def test_gabarit_sans_texte_est_ecarte_mais_le_motif_le_dit() -> None:
    """
    Seul rejet non verifie du module : il doit s'annoncer comme tel.

    On l'accepte parce que les gabarits transitaire sont generes par logiciel,
    donc precis. Mais le motif doit permettre de le retrouver dans le journal le
    jour ou une facture manque.
    """
    verdict = trier(Path("Avis de retard 202607.pdf"))
    assert verdict.decision == "non_comptable"
    assert "non verifiable" in verdict.motif
