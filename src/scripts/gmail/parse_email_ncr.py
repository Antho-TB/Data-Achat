"""
Module de parsing des emails de rejets et non-conformités (Eric Tarrerias / Qualité).

Analyse les corps et sujets d'emails émis par le Commerce/Qualité pour extraire
de manière déterministe les décisions de non-conformité (NCR), les numéros de PO,
les codes articles et les motifs de refus.
"""

import re
import logging
from typing import Any, Dict, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Patterns regex ciblés
PATTERN_PO = [
    re.compile(r'(?<![A-Za-z0-9])(?:PO|COMMANDE|CMD|SO)\s*[:#-]?\s*([0-9]{4,8})(?![A-Za-z0-9])', re.IGNORECASE),
    re.compile(r'(?<![A-Za-z0-9])(1[0-9]{5})(?![A-Za-z0-9])'),
]

PATTERN_ARTICLE = re.compile(r'(?<![A-Za-z0-9])([0-9]{8})(?![A-Za-z0-9])')

PATTERN_NCR_REF = [
    re.compile(r'(?<![A-Za-z0-9])(NCR[-_\s]*[0-9A-Za-z\-]+)(?![A-Za-z0-9])', re.IGNORECASE),
    re.compile(r'(?<![A-Za-z0-9])(CA[0-9]{6})(?![A-Za-z0-9])', re.IGNORECASE),
]

KEYWORDS_REJET = [
    'non conforme', 'non-conforme', 'rejet', 'rejete', 'rejeté', 'refuse', 'refusé',
    'ncr', 'defectueux', 'defectueuse', 'non conformite', 'non-conformite', 'fail'
]


def is_ncr_email(subject: str, body: str) -> bool:
    """Vérifie si l'email traite d'une non-conformité ou d'un rejet qualité.

    Args:
        subject (str): Sujet du mail.
        body (str): Corps du mail.

    Returns:
        bool: True si l'email signale une non-conformité.
    """
    text_full = f"{subject} {body}".lower()
    return any(kw in text_full for kw in KEYWORDS_REJET)


def parse_email_ncr(body: str, subject: str = "", sender: str = "", date_sent: str = "") -> Optional[Dict[str, Any]]:
    """Extrait le PO, le code article, la référence NCR et le motif du rejet depuis un email.

    Args:
        body (str): Corps textuel du message.
        subject (str): Objet du mail.
        sender (str): Adresse email de l'expéditeur (ex: Eric Tarrerias).
        date_sent (str): Date d'envoi du mail (ISO ou YYYY-MM-DD).

    Returns:
        Optional[Dict[str, Any]]: Dictionnaire des données NCR ou None si non applicable.
    """
    if not is_ncr_email(subject, body):
        return None

    full_text = f"{subject}\n{body}"

    # 1. Extraction du N° PO
    po_number = None
    for pat in PATTERN_PO:
        match = pat.search(full_text)
        if match:
            po_number = match.group(1).lstrip('0')
            break

    # 2. Extraction du Code Article
    match_art = PATTERN_ARTICLE.search(full_text)
    code_article = match_art.group(1) if match_art else None

    # 3. Extraction Référence NCR / Rapport CA...
    ncr_ref = None
    for pat in PATTERN_NCR_REF:
        match = pat.search(full_text)
        if match:
            ncr_ref = match.group(1).upper()
            break

    if not ncr_ref:
        ncr_ref = "NCR-EMAIL"

    # 4. Décision & Motif
    decision = "NON CONFORME"
    
    # Extraire une ligne explicative si possible
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    motif_lines = [l for l in lines if any(kw in l.lower() for kw in KEYWORDS_REJET)]
    motif = motif_lines[0] if motif_lines else (subject if subject else "Rejet qualité signalé par mail")

    # Si expediteur Eric T. -> mentionner la validation Commerce
    is_eric_t = "tarrerias" in sender.lower() or "eric" in sender.lower()
    if is_eric_t and "Eric T." not in motif:
        motif = f"[Décision Eric T.] {motif}"

    result = {
        "po_number": po_number,
        "code_article": code_article,
        "ncr_ref": ncr_ref,
        "decision": decision,
        "motif": motif,
        "date_decision": date_sent,
        "expediteur": sender,
    }

    logger.info(f"[INFO] Email NCR détecté : PO={po_number}, Article={code_article}, Ref={ncr_ref}")
    return result


if __name__ == "__main__":
    sample_subject = "RE: NON-CONFORMITE PO 181325 - Echantillon couteau fromage"
    sample_body = "Bonjour Andréa,\nSuite aux tests labo, présence de piqûres de rouille. Le lot est NON CONFORME et rejeté. Merci d'ouvrir la NCR2026-04.\nCdlt,\nEric Tarrerias"
    res = parse_email_ncr(sample_body, sample_subject, "eric.tarrerias@tb-groupe.fr", "2026-07-27")
    print("Parsing Result:", res)
