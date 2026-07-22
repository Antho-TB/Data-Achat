# -*- coding: utf-8 -*-
"""
[GMAIL] Chargement des annotations métier extraites des threads Gmail
=====================================================================
Reçoit un JSON (liste d'objets) d'informations extraites du CORPS des mails
(non-conformité Eric T, raison de retard/imprévu, décisions commerce, échanges
design/supply chain, code article informel, etc.) et les écrit dans
`achat.commande_annotation` — le réceptacle métier ouvert à platform_team.

On n'écrit JAMAIS dans `achat.commande` depuis Gmail (full-refresh Excel).
Le transport (BL/conteneur/ETD/ETA) passe par le pipeline déterministe (ot_transport).

Format d'un enregistrement JSON :
{
  "po_number": "00178307",         # requis (clé de rattachement)
  "code_article": "20110061",      # optionnel
  "thread_id": "18f...",           # requis (idempotence)
  "categorie": "NON-CONFORMITE",   # NON-CONFORMITE|RETARD|IMPREVU|COMMERCE|DESIGN|SUPPLY|CODE-ARTICLE|PROFORMA|PACKING|AUTRE
  "acteur": "Eric T",              # émetteur / décideur
  "statut_retard": null,           # optionnel (texte)
  "date_etd": null,                # optionnel (YYYY-MM-DD)
  "texte": "Refus lot MEN#26028, teinte manche non conforme"
}

Idempotence : on ne réinsère pas si une annotation existe déjà pour
(po_number, code_article) dont le commentaire commence par "[<thread_id>][<categorie>]".

Usage (PowerShell, venv 3.11) :
  python -m src.scripts.gmail.load_annotations --file data\_annotations.json [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from app.database import get_engine  # noqa: E402

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s -- %(message)s")
logger = logging.getLogger(__name__)


def _prefix(rec: dict) -> str:
    return f"[{rec.get('thread_id', '?')}][{rec.get('categorie', 'AUTRE')}]"


def _commentaire(rec: dict) -> str:
    acteur = rec.get("acteur") or "?"
    texte = (rec.get("texte") or "").strip()
    return f"{_prefix(rec)}[{acteur}] {texte}"


def load(records: list[dict], dry_run: bool = False) -> None:
    engine = get_engine()
    inserted = skipped = ignored = 0
    with engine.begin() as conn:
        for rec in records:
            po = (rec.get("po_number") or "").strip()
            if not po:
                ignored += 1
                logger.warning("Ignoré (po_number manquant) : %s", rec.get("texte", "")[:60])
                continue
            code = rec.get("code_article")
            # idempotence : deja une annotation pour ce thread+categorie sur ce PO ?
            exists = conn.execute(text("""
                SELECT 1 FROM achat.commande_annotation
                WHERE po_number = :po
                  AND coalesce(code_article,'') = coalesce(:code,'')
                  AND commentaire LIKE :pat
                LIMIT 1
            """), {"po": po, "code": code, "pat": _prefix(rec) + "%"}).first()
            if exists:
                skipped += 1
                continue
            if dry_run:
                inserted += 1
                logger.info("(dry-run) + %s | %s", po, _commentaire(rec)[:90])
                continue
            conn.execute(text("""
                INSERT INTO achat.commande_annotation
                    (po_number, code_article, statut_retard, date_etd, commentaire, updated_by, updated_at)
                VALUES
                    (:po, :code, :statut, :etd, :comm, 'gmail-thread', NOW())
            """), {
                "po": po, "code": code,
                "statut": rec.get("statut_retard"),
                "etd": rec.get("date_etd"),
                "comm": _commentaire(rec),
            })
            inserted += 1
            logger.info("+ %s | %s", po, _commentaire(rec)[:90])
    mode = "[DRY-RUN] " if dry_run else ""
    logger.info("%s%d inséré(s), %d déjà présent(s), %d ignoré(s).", mode, inserted, skipped, ignored)


def main() -> None:
    ap = argparse.ArgumentParser(description="Charge les annotations Gmail -> achat.commande_annotation")
    ap.add_argument("--file", required=True, help="JSON (liste d'annotations)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    records = json.loads(Path(args.file).read_text(encoding="utf-8-sig"))
    if isinstance(records, dict):
        records = [records]
    logger.info("%d enregistrement(s) à traiter (dry_run=%s)", len(records), args.dry_run)
    load(records, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
