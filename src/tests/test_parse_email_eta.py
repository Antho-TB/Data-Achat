# -*- coding: utf-8 -*-
"""
[TEST] Validation du parser de corps de mail transitaire (ETA / livraison)
"""
from src.scripts.gmail.parse_email_eta import parse_email_body, detect_forwarder, parse_date_to_iso
from src.scripts.gmail.load_email_eta import process_messages


def test_parse_date_to_iso():
    assert parse_date_to_iso("20/10/2026") == "2026-10-20"
    assert parse_date_to_iso("2026-10-20") == "2026-10-20"
    assert parse_date_to_iso("5/6/2026") == "2026-06-05"
    assert parse_date_to_iso("20.10.2026") == "2026-10-20"


def test_detect_forwarder():
    assert detect_forwarder("ops@qualitairsea.com", "Bonjour") == "QUALITAIR"
    assert detect_forwarder("transit@bollore.com", "Info BOLLORE") == "BOLLORE"
    assert detect_forwarder("inconnu@domain.com", "Hello") == "TRANSITAIRE"


def test_parse_email_body_qualitair():
    subject = "Mise à jour ETA conteneur TGBU2004021 - PO 00176529"
    body = (
        "Bonjour Andréa,\n"
        "Veuillez noter que pour le conteneur TGBU2004021 (PO 00176529), "
        "l'ETA Fos est reportée au 20/10/2026.\n"
        "Raison : motif retard congestion portuaire à Ningbo.\n"
        "Livraison site Pommier prévue le 25/10/2026.\n"
        "Cordialement,\nQualitairsea"
    )

    events = parse_email_body(subject, body, "msg_123", "2026-07-27", "ops@qualitairsea.com")
    assert len(events) == 2

    eta_ev = next(e for e in events if e["champ_date"] == "eta")
    assert eta_ev["n_conteneur"] == "TGBU2004021"
    assert eta_ev["po_number"] == "00176529"
    assert eta_ev["nouvelle_valeur"] == "2026-10-20"
    assert eta_ev["acteur"] == "QUALITAIR"

    liv_ev = next(e for e in events if e["champ_date"] == "date_livraison")
    assert liv_ev["n_conteneur"] == "TGBU2004021"
    assert liv_ev["nouvelle_valeur"] == "2026-10-25"


def test_process_messages_dry_run():
    messages = [
        {
            "id": "msg_dry_01",
            "subject": "Suivi SEALOGIS - MSCU9988776",
            "body": "Conteneur MSCU9988776: ETA 15/11/2026 suite à un retard d'escale.",
            "date": "2026-07-27",
            "from_email": "sealogis@sealogis.com",
        }
    ]
    cnt = process_messages(messages, dry_run=True)
    assert cnt == 1
