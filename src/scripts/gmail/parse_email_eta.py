# -*- coding: utf-8 -*-
"""
[ETL]
=============================================================================
PARSER MAILS ETA TRANSITAIRES (Corps de Mail Gmail) -> Événements transport
=============================================================================

Extrait du corps textuel ou HTML des emails transitaires (QUALITAIRSEA, Bolloré,
Sealogis, Geodis, etc.) :
- Le n° de conteneur (`n_conteneur`, ISO 4 lettres + 7 chiffres)
- Les dates réestimées (`eta`, `date_livraison`, `etd_reel`)
- Le motif/justification du changement (ex. congestion portuaire, grève, etc.)
- Émet une liste d'événements formatés pour achat.transport_evenement (pattern A)

Usage :
    python -m src.scripts.gmail.parse_email_eta --file data/sample_mail.txt
"""
from __future__ import annotations

import argparse
import json
import logging
import re
from datetime import datetime
from typing import Any, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s -- %(message)s",
)
logger = logging.getLogger("parse_email_eta")

# Transitaire reconnus
KNOWN_FORWARDERS = (
    "QUALITAIR", "QUALITAIRSEA", "BOLLORE", "SEALOGIS", "GEODIS",
    "SCHENKER", "KUEHNE", "NAGEL", "DSV", "SINOTRANS", "DHL", "CEVA",
    "DACHSER", "EXPEDITORS",
)

# Motifs de retard / justifications
RE_JUSTIFICATION = re.compile(
    r"(?:motif|raison|cause|remarque|note)?\s*[:\-]?\s*"
    r"([^.\n;]*(?:retard|report|congestion|tempête|météo|grève|décalage|attente|escale|douane)[^.\n;]*)",
    re.IGNORECASE,
)

# ISO 6346 : 4 lettres + 7 chiffres (ex: TGBU2004021)
RE_CONTAINER = re.compile(r"(?<![A-Za-z0-9-])([A-Z]{4}\d{7})(?![A-Za-z0-9-])")

# PO TB : 8 chiffres (ex: 00176529) ou PO 176529
RE_PO = re.compile(r"(?:P[\./ ]?O|purchase\s*order|commande)[^0-9]{0,12}(\d{6,8})", re.IGNORECASE)

# Expressions régulières pour les dates dans le corps
RE_ETA_DATE = re.compile(
    r"(?:ETA|arrivée\s*estimée|arrivée\s*port|arrivée\s*Fos|arrivée\s*Marseille)[^0-9\n]{0,35}?"
    r"(\d{1,2}[\/\.\-]\d{1,2}[\/\.\-]\d{2,4}|\d{4}[\/\.\-]\d{1,2}[\/\.\-]\d{1,2})",
    re.IGNORECASE,
)

RE_LIVRAISON_DATE = re.compile(
    r"(?:livraison\s*prévue|livraison\s*site|livraison\s*Pommier|livraison\s*GDD|livraison\s*estimée|livraison)[^0-9\n]{0,35}?"
    r"(\d{1,2}[\/\.\-]\d{1,2}[\/\.\-]\d{2,4}|\d{4}[\/\.\-]\d{1,2}[\/\.\-]\d{1,2})",
    re.IGNORECASE,
)

RE_ETD_DATE = re.compile(
    r"(?:ETD|départ\s*prévu|départ\s*Chine|départ\s*estimé)[^0-9\n]{0,35}?"
    r"(\d{1,2}[\/\.\-]\d{1,2}[\/\.\-]\d{2,4}|\d{4}[\/\.\-]\d{1,2}[\/\.\-]\d{1,2})",
    re.IGNORECASE,
)


def parse_date_to_iso(date_str: str) -> Optional[str]:
    """Convertit une chaîne date française ou ISO en YYYY-MM-DD."""
    if not date_str:
        return None
    date_str = date_str.strip().replace(".", "/").replace("-", "/")
    parts = date_str.split("/")
    try:
        if len(parts) == 3:
            if len(parts[0]) == 4:  # YYYY/MM/DD
                y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
            else:  # DD/MM/YYYY ou DD/MM/YY
                d, m, y = int(parts[0]), int(parts[1]), int(parts[2])
                if y < 100:
                    y += 2000
            return f"{y:04d}-{m:02d}-{d:02d}"
    except ValueError:
        pass
    return None


def detect_forwarder(from_email: str, body: str) -> str:
    """Détecte le transitaire depuis l'adresse email ou le texte."""
    text_upper = f"{from_email} {body}".upper()
    for fwd in KNOWN_FORWARDERS:
        if fwd in text_upper:
            return fwd
    return "TRANSITAIRE"


def parse_email_body(
    subject: str,
    body: str,
    msg_id: str,
    date_msg: str,
    from_email: str = "",
) -> list[dict[str, Any]]:
    """
    Extrait les événements de réestimation de date de transport depuis un email.

    Args:
        subject: Objet du mail
        body: Corps textuel du mail
        msg_id: ID unique du message Gmail
        date_msg: Date du mail (ISO ou timestamp)
        from_email: Adresse expéditeur

    Returns:
        Liste de dictionnaires d'événements prêts pour achat.transport_evenement
    """
    full_text = f"{subject}\n{body}"
    containers = list(set(RE_CONTAINER.findall(full_text)))
    if not containers:
        return []

    po_matches = RE_PO.findall(full_text)
    po_number = po_matches[0] if po_matches else None
    transitaire = detect_forwarder(from_email, full_text)

    # Motif de retard
    motif_match = RE_JUSTIFICATION.search(full_text)
    motif = motif_match.group(1).strip() if motif_match else "Mise à jour transitaire (mail)"

    events: list[dict[str, Any]] = []

    # Extraction ETA
    eta_match = RE_ETA_DATE.search(full_text)
    if eta_match:
        iso_eta = parse_date_to_iso(eta_match.group(1))
        if iso_eta:
            for cont in containers:
                cle = f"transport:mail:{cont}:eta:{iso_eta}:{msg_id}"
                events.append({
                    "domaine": "transport",
                    "cle_idempotence": cle,
                    "n_conteneur": cont,
                    "po_number": po_number,
                    "thread_id": msg_id,
                    "acteur": transitaire,
                    "source": "mail_corps",
                    "date_info": date_msg[:10] if date_msg else datetime.now().strftime("%Y-%m-%d"),
                    "type": "date_estimee",
                    "champ_date": "eta",
                    "nouvelle_valeur": iso_eta,
                    "motif": motif,
                    "texte": f"Avis {transitaire} par mail : ETA réestimée au {iso_eta} ({motif})"
                })

    # Extraction Livraison
    liv_match = RE_LIVRAISON_DATE.search(full_text)
    if liv_match:
        iso_liv = parse_date_to_iso(liv_match.group(1))
        if iso_liv:
            for cont in containers:
                cle = f"transport:mail:{cont}:date_livraison:{iso_liv}:{msg_id}"
                events.append({
                    "domaine": "transport",
                    "cle_idempotence": cle,
                    "n_conteneur": cont,
                    "po_number": po_number,
                    "thread_id": msg_id,
                    "acteur": transitaire,
                    "source": "mail_corps",
                    "date_info": date_msg[:10] if date_msg else datetime.now().strftime("%Y-%m-%d"),
                    "type": "date_estimee",
                    "champ_date": "date_livraison",
                    "nouvelle_valeur": iso_liv,
                    "motif": motif,
                    "texte": f"Avis {transitaire} par mail : Date de livraison estimée au {iso_liv} ({motif})"
                })

    return events


def main() -> None:
    ap = argparse.ArgumentParser(description="Parser corps de mail -> événements ETA transport")
    ap.add_argument("--file", required=True, help="Chemin du fichier texte/JSON du mail")
    args = ap.parse_args()

    content = open(args.file, "r", encoding="utf-8").read()
    events = parse_email_body("Sujet Test", content, "msg_test_001", "2026-07-27", "qualitairsea@example.com")
    print(json.dumps(events, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
