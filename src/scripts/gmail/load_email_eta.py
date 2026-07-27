# -*- coding: utf-8 -*-
"""
[ETL]
=============================================================================
LOADER MAILS ETA TRANSITAIRES -> achat.transport_evenement
=============================================================================

Prend une liste de messages emails (objet, corps, id, expéditeur), extrait
les événements d'ETA via parse_email_eta, et les route vers la BDD PostgreSQL.

Usage :
    python -m src.scripts.gmail.load_email_eta --file data/mails_eta.json [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

from src.scripts.gmail.load_evenements import load as load_evenements
from src.scripts.gmail.parse_email_eta import parse_email_body

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s -- %(message)s",
)
logger = logging.getLogger("load_email_eta")


def process_messages(messages: list[dict[str, Any]], dry_run: bool = False) -> int:
    """
    Extrait et charge les événements d'ETA depuis une liste de messages.

    Args:
        messages: liste de dicts contenant (subject, body, id, date, from_email)
        dry_run: si True, simule sans écriture en base

    Returns:
        Nombre d'événements extraits et routés
    """
    all_events: list[dict[str, Any]] = []

    for msg in messages:
        subject = msg.get("subject", "")
        body = msg.get("body", "")
        msg_id = msg.get("id", msg.get("message_id", "msg_unk"))
        date_msg = msg.get("date", msg.get("date_info", ""))
        from_email = msg.get("from_email", msg.get("from", ""))

        events = parse_email_body(subject, body, msg_id, date_msg, from_email)
        all_events.extend(events)

    if not all_events:
        logger.info("Aucun événement d'ETA trouvé dans les %d message(s).", len(messages))
        return 0

    logger.info("%d événement(s) d'ETA extrait(s). Routage vers achat.transport_evenement...", len(all_events))
    load_evenements(all_events, dry_run=dry_run)
    return len(all_events)


def main() -> None:
    ap = argparse.ArgumentParser(description="Charge les événements d'ETA depuis un fichier JSON de messages")
    ap.add_argument("--file", required=True, help="Chemin du fichier JSON de messages")
    ap.add_argument("--dry-run", action="store_true", help="Mode simulation (rollback)")
    args = ap.parse_args()

    file_path = Path(args.file)
    if not file_path.exists():
        logger.error("Fichier introuvable : %s", file_path)
        return

    data = json.loads(file_path.read_text(encoding="utf-8-sig"))
    messages = data if isinstance(data, list) else [data]
    process_messages(messages, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
