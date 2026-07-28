# -*- coding: utf-8 -*-
"""
[GMAIL]
=============================================================================
PARSER DES MAILS ETA TRANSITAIRES -> EVENEMENTS TRANSPORT
=============================================================================

Les transitaires (QUALITAIRSEA, Bollore, Sealogis, Geodis...) annoncent les
reestimations de date par mail, jamais dans un fichier. Ce module en extrait :
- le numero de conteneur (ISO 6346, 4 lettres + 7 chiffres),
- les dates reestimees (ETA, ETD, date de livraison),
- le motif du changement (congestion portuaire, greve, douane...),
et produit des evenements prets pour achat.transport_evenement.

Strategie de segmentation : un mail recapitulatif liste souvent plusieurs
conteneurs avec CHACUN sa propre date. La version precedente extrayait une
seule date pour tout le mail et la recopiait sur tous les conteneurs, donc un
mail a 5 conteneurs produisait 4 ETA fausses. On decoupe desormais le texte en
segments, un par conteneur, et on ne cherche les dates que dans le segment
correspondant. La date globale du mail n'est utilisee en repli que s'il n'y a
qu'un seul conteneur, cas ou l'ambiguite n'existe pas.

Junior Tip : une ETA fausse en base est pire qu'une ETA absente. Marlene
planifie le dechargement et previent le client sur cette date ; mieux vaut une
case vide qu'elle ira verifier qu'un chiffre faux auquel elle fait confiance.

=============================================================================
!! MODULE NON RETENU -- NE PAS ORDONNANCER (decision du 28/07/2026)
=============================================================================
Les reestimations de date depuis le corps des mails sont captees en production
par la TACHE COWORK (toutes les 2 h, poste de Marlene), qui alimente
achat.transport_evenement via load_evenements.py avec les types "retard" et
"imprevu" sur les champs eta et etd.

Ce module est une seconde implementation a base de regex, jamais executee. Elle
est conservee comme repli documente pour le jour ou l'on voudra sortir de la
dependance a l'application Claude ouverte, mais **l'ordonnancer en parallele du
Cowork produirait des evenements en double** sur la meme table.
Cf. docs/plan_action.md section 3.4.

Usage :
    python -m src.scripts.gmail.parse_email_eta --file data/sample_mail.txt
"""
from __future__ import annotations

import argparse
import json
import logging
import re
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from typing import Any, Optional

from src.utils.logging_setup import setup_logging

logger = logging.getLogger(__name__)

# Transitaires reconnus
KNOWN_FORWARDERS = (
    "QUALITAIR", "QUALITAIRSEA", "BOLLORE", "SEALOGIS", "GEODIS",
    "SCHENKER", "KUEHNE", "NAGEL", "DSV", "SINOTRANS", "DHL", "CEVA",
    "DACHSER", "EXPEDITORS",
)

# Motif du changement de date. Le prefixe est OBLIGATOIRE : sans lui, la regex
# attrapait la formule de politesse "dans l'attente de votre retour" et la
# stockait comme motif de retard sur tous les evenements du mail.
RE_JUSTIFICATION = re.compile(
    r"(?:motif|raison|cause|remarque|note)\s*[:\-]\s*([^.\n;]{3,200})",
    re.IGNORECASE,
)

# Repli : phrase contenant explicitement un terme d'incident transport.
RE_JUSTIFICATION_IMPLICITE = re.compile(
    r"([^.\n;]*(?:congestion|tempête|météo|grève|blank sailing|roulé|surestarie|"
    r"douane bloquée|retard\s+(?:de|du|au|a\s|à\s))[^.\n;]*)",
    re.IGNORECASE,
)

MOTIF_PAR_DEFAUT = "Mise a jour transitaire (mail)"

# ISO 6346 : 4 lettres + 7 chiffres (ex: TGBU2004021)
# ISO 6346 : la 4e lettre vaut toujours U, J ou Z (cf. parse_bl.py).
RE_CONTAINER = re.compile(r"(?<![A-Za-z0-9])([A-Z]{3}[UJZ]\d{7})(?![A-Za-z0-9])")

# PO TB : 6 a 8 chiffres precedes d'un libelle (ex: PO 176529, commande 00176529)
RE_PO = re.compile(r"(?:P[\./ ]?O|purchase\s*order|commande)[^0-9]{0,12}(\d{6,8})", re.IGNORECASE)

_MOTIF_DATE = r"(\d{1,2}[\/\.\-]\d{1,2}[\/\.\-]\d{2,4}|\d{4}[\/\.\-]\d{1,2}[\/\.\-]\d{1,2})"

RE_ETA_DATE = re.compile(
    r"(?:ETA|arrivée\s*estimée|arrivée\s*port|arrivée\s*Fos|arrivée\s*Marseille)"
    r"[^0-9\n]{0,35}?" + _MOTIF_DATE,
    re.IGNORECASE,
)

RE_LIVRAISON_DATE = re.compile(
    r"(?:livraison\s*prévue|livraison\s*site|livraison\s*Pommier|livraison\s*GDD|"
    r"livraison\s*estimée|livraison)[^0-9\n]{0,35}?" + _MOTIF_DATE,
    re.IGNORECASE,
)

RE_ETD_DATE = re.compile(
    r"(?:ETD|départ\s*prévu|départ\s*Chine|départ\s*estimé)[^0-9\n]{0,35}?" + _MOTIF_DATE,
    re.IGNORECASE,
)

# champ cible en base -> regex correspondante
CHAMPS_DATE: dict[str, re.Pattern[str]] = {
    "eta": RE_ETA_DATE,
    "date_livraison": RE_LIVRAISON_DATE,
    "etd_reel": RE_ETD_DATE,
}

LIBELLES_CHAMP = {
    "eta": "ETA réestimée",
    "date_livraison": "Date de livraison estimée",
    "etd_reel": "ETD réestimé",
}


def parse_date_to_iso(date_str: str) -> Optional[str]:
    """
    Convertit une date francaise ou ISO en YYYY-MM-DD.

    Junior Tip : on construit un objet date reel plutot qu'une chaine formatee.
    Un formatage brut acceptait "35/13/2026" et produisait "2026-13-35", que
    PostgreSQL refusait ensuite en bloquant tout le lot d'insertion.

    Args:
        date_str: date brute extraite du mail (ex: "12/08/2026", "2026-08-12").
    Returns:
        Date au format YYYY-MM-DD, ou None si la chaine n'est pas une date valide.
    """
    if not date_str:
        return None
    parts = date_str.strip().replace(".", "/").replace("-", "/").split("/")
    if len(parts) != 3:
        return None
    try:
        if len(parts[0]) == 4:  # YYYY/MM/DD
            y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
        else:  # DD/MM/YYYY ou DD/MM/YY
            d, m, y = int(parts[0]), int(parts[1]), int(parts[2])
            if y < 100:
                y += 2000
        return date(y, m, d).isoformat()
    except ValueError:
        logger.warning("[ATTENTION] Date illisible ignoree : %r", date_str)
        return None


def normalize_date_msg(date_msg: str | None) -> str:
    """
    Normalise la date d'envoi du mail en YYYY-MM-DD.

    Gmail renvoie une date RFC 2822 ("Mon, 27 Jul 2026 09:12:00 +0200"). Un
    simple decoupage des 10 premiers caracteres donnait "Mon, 27 J", insere tel
    quel dans une colonne DATE, ce qui faisait echouer tout le lot.

    Args:
        date_msg: date brute du message (ISO ou RFC 2822).
    Returns:
        Date au format YYYY-MM-DD, celle du jour si la valeur est illisible.
    """
    if not date_msg:
        return datetime.now().strftime("%Y-%m-%d")
    texte = str(date_msg).strip()
    iso = parse_date_to_iso(texte[:10]) if texte[:4].isdigit() else None
    if iso:
        return iso
    try:
        return parsedate_to_datetime(texte).date().isoformat()
    except (TypeError, ValueError):
        logger.warning("[ATTENTION] Date de mail illisible (%r), repli sur la date du jour.", date_msg)
        return datetime.now().strftime("%Y-%m-%d")


def detect_forwarder(from_email: str, body: str) -> str:
    """Detecte le transitaire depuis l'adresse email ou le texte du mail."""
    text_upper = f"{from_email} {body}".upper()
    for fwd in KNOWN_FORWARDERS:
        if fwd in text_upper:
            return fwd
    return "TRANSITAIRE"


def extract_motif(texte: str) -> str:
    """Extrait le motif du changement de date, ou un libelle neutre par defaut."""
    explicite = RE_JUSTIFICATION.search(texte)
    if explicite:
        return explicite.group(1).strip()
    implicite = RE_JUSTIFICATION_IMPLICITE.search(texte)
    if implicite:
        return implicite.group(1).strip()
    return MOTIF_PAR_DEFAUT


def segment_par_conteneur(texte: str) -> list[tuple[str, str]]:
    """
    Decoupe le texte du mail en un segment par conteneur mentionne.

    Le segment d'un conteneur va de sa premiere occurrence jusqu'a la mention
    du conteneur suivant. C'est ce qui permet, dans un mail recapitulatif, de
    rattacher chaque date au bon conteneur au lieu de recopier la premiere date
    trouvee sur toute la liste.

    Args:
        texte: sujet + corps du mail.
    Returns:
        Liste de couples (n_conteneur, segment de texte associe), sans doublon.
    """
    occurrences = list(RE_CONTAINER.finditer(texte))
    if not occurrences:
        return []

    segments: dict[str, str] = {}
    for i, match in enumerate(occurrences):
        cont = match.group(1)
        if cont in segments:
            continue
        fin = occurrences[i + 1].start() if i + 1 < len(occurrences) else len(texte)
        segments[cont] = texte[match.start():fin]
    return list(segments.items())


def parse_email_body(
    subject: str,
    body: str,
    msg_id: str,
    date_msg: str,
    from_email: str = "",
) -> list[dict[str, Any]]:
    """
    Extrait les evenements de reestimation de date de transport d'un email.

    Args:
        subject: objet du mail.
        body: corps textuel du mail.
        msg_id: identifiant unique du message Gmail.
        date_msg: date du mail (ISO ou RFC 2822).
        from_email: adresse de l'expediteur.
    Returns:
        Liste d'evenements prets pour achat.transport_evenement.
    """
    full_text = f"{subject}\n{body}"
    segments = segment_par_conteneur(full_text)
    if not segments:
        return []

    po_global = RE_PO.search(full_text)
    transitaire = detect_forwarder(from_email, full_text)
    date_info = normalize_date_msg(date_msg)
    mono_conteneur = len(segments) == 1

    events: list[dict[str, Any]] = []
    for cont, segment in segments:
        # Sur un mail mono-conteneur, la date peut figurer avant la reference
        # du conteneur (en objet par exemple) : on autorise le repli sur le
        # texte complet. Des qu'il y a plusieurs conteneurs, c'est interdit,
        # sinon on recopie la date du premier sur tous les autres.
        portee = full_text if mono_conteneur else segment
        po_segment = RE_PO.search(segment)
        po_number = (po_segment or po_global).group(1) if (po_segment or po_global) else None
        motif = extract_motif(portee)

        for champ, regex in CHAMPS_DATE.items():
            trouve = regex.search(portee)
            if not trouve:
                continue
            iso = parse_date_to_iso(trouve.group(1))
            if not iso:
                continue
            events.append({
                "domaine": "transport",
                # Le champ date fait partie de la cle : sans lui, l'ETA et la
                # date de livraison du meme mail portent la meme cle et la
                # seconde est avalee par le ON CONFLICT DO NOTHING.
                "cle_idempotence": f"transport:mail:{cont}:{champ}:{iso}:{msg_id}",
                "n_conteneur": cont,
                "po_number": po_number,
                "thread_id": msg_id,
                "acteur": transitaire,
                "source": "mail_corps",
                "date_info": date_info,
                "type": "date_estimee",
                "champ_date": champ,
                "nouvelle_valeur": iso,
                "motif": motif,
                "texte": f"Avis {transitaire} par mail : {LIBELLES_CHAMP[champ]} au {iso} ({motif})",
            })

    logger.info("[INFO] %d conteneur(s) detecte(s), %d evenement(s) extrait(s) du mail %s.",
                len(segments), len(events), msg_id)
    return events


def main() -> None:
    setup_logging()
    ap = argparse.ArgumentParser(description="Parser corps de mail -> evenements ETA transport")
    ap.add_argument("--file", required=True, help="Chemin du fichier texte du mail")
    args = ap.parse_args()

    with open(args.file, "r", encoding="utf-8") as fh:
        content = fh.read()
    events = parse_email_body("Sujet Test", content, "msg_test_001",
                              "2026-07-27", "qualitairsea@example.com")
    logger.info("[SUCCES] %d evenement(s) :\n%s", len(events),
                json.dumps(events, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
