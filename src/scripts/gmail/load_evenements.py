# -*- coding: utf-8 -*-
"""
[GMAIL] Routeur d'événements métier extraits des threads -> tables achat.* par sujet
=====================================================================================
Remplace le fourre-tout achat.commande_annotation par 4 tables structurées
(créées par sql/20260722_tables_evenements_metier.sql) :
  - qualite_decision    (domaine="qualite")
  - transport_evenement (domaine="transport")
  - commerce_decision   (domaine="commerce")
  - design_evenement    (domaine="design")

Chaque enregistrement JSON porte un `domaine` + les colonnes communes
(po_number, code_article, n_conteneur, thread_id, acteur, source, date_info, texte)
+ les colonnes propres au sujet. Idempotent via cle_idempotence (ON CONFLICT DO NOTHING).

Usage : python -m src.scripts.gmail.load_evenements --file data\_evenements.json [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import sys

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from app.database import get_engine  # noqa: E402

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s -- %(message)s")
logger = logging.getLogger(__name__)

COMMON = ["po_number", "code_article", "n_conteneur", "thread_id",
          "acteur", "source", "date_info", "texte"]

# domaine -> (table, colonnes spécifiques, champ discriminant pour la clé)
ROUTES = {
    "qualite":   ("achat.qualite_decision",    ["decision", "motif", "stade"],                         "decision"),
    "transport": ("achat.transport_evenement", ["type", "champ_date", "ancienne_valeur",
                                                 "nouvelle_valeur", "motif"],                            "type"),
    "commerce":  ("achat.commerce_decision",   ["type", "contenu"],                                     "type"),
    "design":    ("achat.design_evenement",    ["type", "statut"],                                      "type"),
}


def _cle(rec: dict, discr: str) -> str:
    return "|".join([
        rec.get("thread_id", "?"), rec.get("domaine", "?"),
        str(rec.get(discr) or ""), rec.get("po_number") or "",
        rec.get("code_article") or "",
    ])


def load(records: list[dict], dry_run: bool = False) -> None:
    engine = get_engine()
    stats: dict[str, int] = {}
    ignored = 0
    with engine.begin() as conn:
        for rec in records:
            dom = (rec.get("domaine") or "").strip().lower()
            if dom not in ROUTES:
                ignored += 1
                logger.warning("Ignoré (domaine inconnu '%s') : %s", dom, (rec.get("texte") or "")[:60])
                continue
            table, spec_cols, discr = ROUTES[dom]
            cols = COMMON + spec_cols
            payload = {k: rec.get(k) for k in cols}
            payload["cle_idempotence"] = _cle(rec, discr)
            if dry_run:
                stats[dom] = stats.get(dom, 0) + 1
                logger.info("(dry-run) -> %s | %s", table, payload["cle_idempotence"])
                continue
            col_list = ["cle_idempotence"] + cols
            placeholders = ", ".join(f":{c}" for c in col_list)
            conn.execute(text(
                f"INSERT INTO {table} ({', '.join(col_list)}) VALUES ({placeholders}) "
                f"ON CONFLICT (cle_idempotence) DO NOTHING"
            ), payload)
            stats[dom] = stats.get(dom, 0) + 1
    mode = "[DRY-RUN] " if dry_run else ""
    logger.info("%s%s ; ignorés=%d", mode,
                ", ".join(f"{k}={v}" for k, v in stats.items()) or "0 enregistrement", ignored)


def main() -> None:
    ap = argparse.ArgumentParser(description="Route les événements Gmail -> tables achat.* par sujet")
    ap.add_argument("--file", required=True, help="JSON (liste d'événements avec 'domaine')")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    records = json.loads(Path(args.file).read_text(encoding="utf-8-sig"))
    if isinstance(records, dict):
        records = [records]
    logger.info("%d enregistrement(s) à router (dry_run=%s)", len(records), args.dry_run)
    load(records, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
