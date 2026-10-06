# -*- coding: utf-8 -*-
"""
[TEST] Rattachement des non-conformites aux lignes de commande (06/10/2026).

Deux sources : decisions qualite recues par mail (achat.qualite_decision), au
grain PO + article ou PO seul ; fiches de non-conformite Sylob, au grain article.
"""
from datetime import date

from app.main import rattacher_non_conformites


def _ligne(po: str, art: str, date_commande: date | None = date(2026, 3, 1)) -> dict:
    return {"po_number": po, "code_article": art, "date_commande": date_commande}


def _decision(po: str, art: str | None, stade: str = "reception") -> dict:
    return {"po": po, "code_article": art, "stade": stade,
            "date_info": date(2026, 9, 30), "motif": "rayures", "acteur": "Eric T"}


def _fiche(art: str, declaree: date | None) -> dict:
    return {"code_fiche": "00000500", "code_article": art, "type_fiche": "NCR",
            "societe": "SE", "date_declaration": declaree}


class TestDecisionsMail:
    def test_decision_article_ne_touche_que_son_article(self) -> None:
        lignes = [_ligne("00017308", "A1"), _ligne("17308", "A2")]
        rattacher_non_conformites(lignes, [_decision("17308", "A1")], [])
        assert len(lignes[0]["non_conformites"]) == 1
        assert lignes[1]["non_conformites"] == []

    def test_decision_sans_article_couvre_tout_le_po(self) -> None:
        """PO compares sans zeros de tete : 6 chiffres dans l'IMPORT, 8 dans les mails."""
        lignes = [_ligne("017308", "A1"), _ligne("017308", "A2"), _ligne("99999", "A1")]
        rattacher_non_conformites(lignes, [_decision("17308", None)], [])
        assert [len(l["non_conformites"]) for l in lignes] == [1, 1, 0]


class TestFichesSylob:
    def test_fiche_anterieure_a_la_commande_ignoree(self) -> None:
        """Une fiche declaree avant la commande concerne une autre commande du meme article."""
        lignes = [_ligne("1", "A1", date(2026, 3, 1))]
        fiches = [_fiche("A1", date(2025, 6, 1)), _fiche("A1", date(2026, 5, 2))]
        rattacher_non_conformites(lignes, [], fiches)
        assert [f["date_declaration"] for f in lignes[0]["fiches_ncr"]] == [date(2026, 5, 2)]

    def test_dates_inconnues_gardees(self) -> None:
        lignes = [_ligne("1", "A1", None), _ligne("2", "A1")]
        rattacher_non_conformites(lignes, [], [_fiche("A1", None)])
        assert all(len(l["fiches_ncr"]) == 1 for l in lignes)

    def test_aucune_source(self) -> None:
        lignes = [_ligne("1", "A1")]
        rattacher_non_conformites(lignes, [], [])
        assert lignes[0]["non_conformites"] == [] and lignes[0]["fiches_ncr"] == []
