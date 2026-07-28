# -*- coding: utf-8 -*-
"""
[TEST] Parser de corps de mail transitaire (ETA, ETD, livraison).
"""
from src.scripts.gmail.load_email_eta import process_messages
from src.scripts.gmail.parse_email_eta import (
    MOTIF_PAR_DEFAUT,
    detect_forwarder,
    extract_motif,
    normalize_date_msg,
    parse_date_to_iso,
    parse_email_body,
    segment_par_conteneur,
)


def test_parse_date_to_iso():
    assert parse_date_to_iso("20/10/2026") == "2026-10-20"
    assert parse_date_to_iso("2026-10-20") == "2026-10-20"
    assert parse_date_to_iso("5/6/2026") == "2026-06-05"
    assert parse_date_to_iso("20.10.2026") == "2026-10-20"


def test_parse_date_to_iso_refuse_les_dates_impossibles():
    """Une date invalide doit donner None, pas une chaine que PostgreSQL rejettera."""
    assert parse_date_to_iso("35/13/2026") is None
    assert parse_date_to_iso("30/02/2026") is None
    assert parse_date_to_iso("pas une date") is None


def test_normalize_date_msg_accepte_le_format_gmail():
    """Gmail renvoie du RFC 2822 : le decoupage brut donnait 'Mon, 27 J' en colonne DATE."""
    assert normalize_date_msg("Mon, 27 Jul 2026 09:12:00 +0200") == "2026-07-27"
    assert normalize_date_msg("2026-07-27T09:12:00") == "2026-07-27"
    assert normalize_date_msg("") != ""


def test_detect_forwarder():
    assert detect_forwarder("ops@qualitairsea.com", "Bonjour") == "QUALITAIR"
    assert detect_forwarder("transit@bollore.com", "Info BOLLORE") == "BOLLORE"
    assert detect_forwarder("inconnu@domain.com", "Hello") == "TRANSITAIRE"


def test_motif_ignore_les_formules_de_politesse():
    """'Dans l'attente de votre retour' n'est pas un motif de retard."""
    assert extract_motif("Dans l'attente de votre retour, cordialement.") == MOTIF_PAR_DEFAUT
    assert "congestion" in extract_motif("Motif : congestion portuaire a Ningbo").lower()
    assert "grève" in extract_motif("Le navire est bloque par une grève des dockers").lower()


def test_segmentation_par_conteneur():
    texte = ("TGBU2004021 ETA 20/10/2026\n"
             "MSCU9988776 ETA 05/11/2026\n"
             "CMAU1234567 ETA 12/11/2026")
    segments = dict(segment_par_conteneur(texte))
    assert set(segments) == {"TGBU2004021", "MSCU9988776", "CMAU1234567"}
    assert "20/10/2026" in segments["TGBU2004021"]
    assert "20/10/2026" not in segments["MSCU9988776"]


def test_chaque_conteneur_recoit_sa_propre_eta():
    """
    Regression : un mail recapitulatif a plusieurs conteneurs recopiait l'ETA du
    premier sur tous les autres, soit 4 ETA fausses sur un mail a 5 conteneurs.
    """
    body = ("Bonjour,\n"
            "TGBU2004021 : ETA Fos le 20/10/2026\n"
            "MSCU9988776 : ETA Fos le 05/11/2026\n"
            "CMAU1234567 : ETA Fos le 12/11/2026\n"
            "Cordialement")
    events = parse_email_body("Point hebdo conteneurs", body, "msg_multi",
                              "2026-07-27", "ops@qualitairsea.com")
    etas = {e["n_conteneur"]: e["nouvelle_valeur"] for e in events if e["champ_date"] == "eta"}
    assert etas == {
        "TGBU2004021": "2026-10-20",
        "MSCU9988776": "2026-11-05",
        "CMAU1234567": "2026-11-12",
    }


def test_parse_email_body_qualitair():
    subject = "Mise à jour ETA conteneur TGBU2004021 - PO 00176529"
    body = (
        "Bonjour Andréa,\n"
        "Veuillez noter que pour le conteneur TGBU2004021 (PO 00176529), "
        "l'ETA Fos est reportée au 20/10/2026.\n"
        "Raison : congestion portuaire à Ningbo.\n"
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
    assert liv_ev["nouvelle_valeur"] == "2026-10-25"


def test_cles_idempotence_distinctes_par_champ_date():
    """
    Regression : ETA et date de livraison du meme mail partageaient la meme cle,
    donc le second evenement etait avale par le ON CONFLICT DO NOTHING.
    """
    subject = "ETA conteneur TGBU2004021"
    body = "ETA Fos le 20/10/2026. Livraison site prévue le 25/10/2026."
    events = parse_email_body(subject, body, "msg_cle", "2026-07-27", "ops@qualitairsea.com")
    cles = [e["cle_idempotence"] for e in events]
    assert len(cles) == len(set(cles))


def test_process_messages_dry_run_sans_acces_base():
    """Le dry-run doit fonctionner hors VPN : aucun appel a get_engine."""
    messages = [{
        "id": "msg_dry_01",
        "subject": "Suivi SEALOGIS - MSCU9988776",
        "body": "Conteneur MSCU9988776: ETA 15/11/2026 suite a une congestion.",
        "date": "Mon, 27 Jul 2026 09:12:00 +0200",
        "from_email": "sealogis@sealogis.com",
    }]
    assert process_messages(messages, dry_run=True) == 1
