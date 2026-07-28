# -*- coding: utf-8 -*-
"""
[GMAIL]
=============================================================================
PARSER DES MAILS DE NON-CONFORMITE (NCR) -> DONNEES STRUCTUREES
=============================================================================

Eric T. signale les rejets qualite par mail. Ce module lit l'objet et le corps
du message pour en extraire de facon deterministe : le numero de PO, le code
article, la reference du rapport (NCR..., CA...) et le motif du refus.

LIMITE CONNUE (regle metier corrigee le 28/07/2026) : ce parser ne reconnait
que les REJETS. Le questionnaire de demo du 07/07 posait que la conformite
etait validee implicitement, sans mail, d'ou une detection volontairement
asymetrique. C'est faux : conformite et non-conformite sont l'une comme l'autre
validees par mail. Le module reste donc a etendre pour capter les deux
decisions, cf. docs/plan_action.md section 5.2.

Strategie : le parser reste PUR, sans acces base. Il se contente d'extraire et
de refuser les valeurs douteuses ; c'est load_email_ncr qui ecrit. Cette
separation permet de rejouer un parsing sur un mail reel sans VPN ni risque
d'ecriture.

Junior Tip : un code article TB fait 8 chiffres, mais une date compactee
(20260715) aussi, et un PO a 8 chiffres aussi. Sans garde-fou, le parser
prenait la date du mail pour un code article et posait la non-conformite sur
un article au hasard. On exclut donc le PO deja reconnu et tout ce qui
ressemble a une date.

Usage :
    python -m src.scripts.gmail.parse_email_ncr --file data/mail_ncr.txt
"""
from __future__ import annotations

import argparse
import json
import logging
import re
from typing import Any, Optional

from src.utils.logging_setup import setup_logging

logger = logging.getLogger(__name__)

PATTERN_PO = [
    re.compile(r'(?<![A-Za-z0-9])(?:PO|COMMANDE|CMD|SO)\s*[:#-]?\s*([0-9]{4,8})(?![A-Za-z0-9])',
               re.IGNORECASE),
    re.compile(r'(?<![A-Za-z0-9])(1[0-9]{5})(?![A-Za-z0-9])'),
]

PATTERN_ARTICLE = re.compile(r'(?<![A-Za-z0-9])([0-9]{8})(?![A-Za-z0-9])')

PATTERN_NCR_REF = [
    re.compile(r'(?<![A-Za-z0-9])(NCR[-_\s]*[0-9A-Za-z\-]+)(?![A-Za-z0-9])', re.IGNORECASE),
    re.compile(r'(?<![A-Za-z0-9])(CA[0-9]{6})(?![A-Za-z0-9])', re.IGNORECASE),
]

KEYWORDS_REJET = [
    'non conforme', 'non-conforme', 'rejet', 'rejete', 'rejeté', 'refuse', 'refusé',
    'ncr', 'defectueux', 'defectueuse', 'non conformite', 'non-conformite', 'fail',
]

NCR_REF_DEFAUT = "NCR-EMAIL"


def is_ncr_email(subject: str, body: str) -> bool:
    """Indique si le mail signale une non-conformite ou un rejet qualite."""
    text_full = f"{subject} {body}".lower()
    return any(kw in text_full for kw in KEYWORDS_REJET)


def _ressemble_a_une_date(valeur: str) -> bool:
    """Ecarte les suites de 8 chiffres qui sont en realite des dates YYYYMMDD."""
    if len(valeur) != 8:
        return False
    annee, mois, jour = int(valeur[:4]), int(valeur[4:6]), int(valeur[6:])
    return 2000 <= annee <= 2099 and 1 <= mois <= 12 and 1 <= jour <= 31


def extract_code_article(full_text: str, po_number: Optional[str]) -> Optional[str]:
    """
    Extrait un code article a 8 chiffres, en ecartant le PO et les dates.

    Args:
        full_text: objet + corps du mail.
        po_number: PO deja reconnu, a ne pas reprendre comme code article.
    Returns:
        Code article plausible, ou None si aucun candidat fiable.
    """
    for match in PATTERN_ARTICLE.finditer(full_text):
        candidat = match.group(1)
        if po_number and candidat.lstrip("0") == po_number:
            continue
        if _ressemble_a_une_date(candidat):
            logger.info("[INFO] Suite de 8 chiffres ecartee (ressemble a une date) : %s", candidat)
            continue
        return candidat
    return None


def parse_email_ncr(body: str, subject: str = "", sender: str = "",
                    date_sent: str = "") -> Optional[dict[str, Any]]:
    """
    Extrait le PO, le code article, la reference NCR et le motif d'un mail de rejet.

    Args:
        body: corps textuel du message.
        subject: objet du mail.
        sender: adresse de l'expediteur.
        date_sent: date d'envoi (ISO ou YYYY-MM-DD).
    Returns:
        Dictionnaire NCR, ou None si le mail ne concerne pas une non-conformite.
    """
    if not is_ncr_email(subject, body):
        return None

    full_text = f"{subject}\n{body}"

    po_number = None
    for pat in PATTERN_PO:
        match = pat.search(full_text)
        if match:
            po_number = match.group(1).lstrip('0')
            break

    code_article = extract_code_article(full_text, po_number)

    ncr_ref = NCR_REF_DEFAUT
    for pat in PATTERN_NCR_REF:
        match = pat.search(full_text)
        if match:
            ncr_ref = match.group(1).upper()
            break

    lignes = [ligne.strip() for ligne in body.splitlines() if ligne.strip()]
    motif_lignes = [l for l in lignes if any(kw in l.lower() for kw in KEYWORDS_REJET)]
    motif = motif_lignes[0] if motif_lignes else (subject or "Rejet qualite signale par mail")

    if ("tarrerias" in sender.lower() or "eric" in sender.lower()) and "Eric T." not in motif:
        motif = f"[Decision Eric T.] {motif}"

    if not po_number:
        logger.warning("[ATTENTION] Mail NCR sans PO identifiable, il ne sera pas ingere : %s",
                       subject[:80])

    logger.info("[INFO] Mail NCR detecte : PO=%s, article=%s, ref=%s",
                po_number, code_article, ncr_ref)
    return {
        "po_number": po_number,
        "code_article": code_article,
        "ncr_ref": ncr_ref,
        "decision": "NON CONFORME",
        "motif": motif,
        "date_decision": date_sent,
        "expediteur": sender,
    }


def main() -> None:
    setup_logging()
    ap = argparse.ArgumentParser(description="Parse un mail de non-conformite qualite")
    ap.add_argument("--file", required=True, help="Fichier texte du mail")
    ap.add_argument("--subject", default="", help="Objet du mail")
    ap.add_argument("--sender", default="", help="Adresse de l'expediteur")
    args = ap.parse_args()

    with open(args.file, "r", encoding="utf-8") as fh:
        body = fh.read()
    resultat = parse_email_ncr(body, args.subject, args.sender)
    logger.info("[SUCCES] Resultat :\n%s", json.dumps(resultat, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
