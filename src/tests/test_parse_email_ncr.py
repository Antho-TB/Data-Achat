# -*- coding: utf-8 -*-
"""
Tests unitaires pour le parser d'emails de rejets et non-conformités (Eric Tarrerias / Qualité).
"""

from src.scripts.gmail.parse_email_ncr import is_ncr_email, parse_email_ncr


def test_is_ncr_email():
    assert is_ncr_email("Rejet PO 181325", "Lot non conforme")
    assert is_ncr_email("Avis de non-conformite", "Merci de bloquer la livraison")
    assert not is_ncr_email("Planning hebdomadaire", "Veuillez trouver ci-joint le planning")


def test_parse_email_ncr_valid():
    subject = "RE: NON-CONFORMITE PO 181325 - Echantillon couteau"
    body = "Bonjour,\nSuite aux tests labo, presence de piqures de rouille. Le lot est NON CONFORME et rejete. NCR2026-04."
    sender = "eric.tarrerias@tb-groupe.fr"

    data = parse_email_ncr(body, subject, sender, "2026-07-27")
    assert data is not None
    assert data["po_number"] == "181325"
    assert data["decision"] == "NON CONFORME"
    assert data["ncr_ref"] == "NCR2026-04"
    assert "[Decision Eric T.]" in data["motif"]


def test_parse_email_ncr_non_ncr():
    data = parse_email_ncr("Bonjour, la commande avance bien", "Suivi commande", "andrea@tb.fr")
    assert data is None


def test_code_article_ne_reprend_ni_le_po_ni_une_date():
    """
    Regression : le parser prenait la premiere suite de 8 chiffres comme code
    article, donc la date compactee du mail ou le PO lui-meme, et posait la
    non-conformite sur un article sans rapport.
    """
    data = parse_email_ncr(
        "Rapport du 20260715 : lot NON CONFORME.",
        "Rejet PO 00181325",
        "eric.tarrerias@tb-groupe.fr",
    )
    assert data is not None
    assert data["po_number"] == "181325"
    assert data["code_article"] != "20260715"
    assert data["code_article"] != "00181325"


def test_code_article_reel_reconnu():
    data = parse_email_ncr(
        "Article 10020112 refuse suite au controle : lot non conforme.",
        "Rejet PO 181325",
        "eric.tarrerias@tb-groupe.fr",
    )
    assert data is not None
    assert data["code_article"] == "10020112"


def test_ncr_sans_po_signalee():
    """Sans PO on ne peut pas cibler la commande : l'alerte doit rester sans PO."""
    data = parse_email_ncr("Le lot est non conforme.", "Probleme qualite", "eric.t@tb-groupe.fr")
    assert data is not None
    assert data["po_number"] is None
