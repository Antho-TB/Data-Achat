# -*- coding: utf-8 -*-
"""
=============================================================================
TRANSFORM SUIVI MARITIME (source #4 Andréa) -> records achat.ot_transport
=============================================================================

Lit la feuille "SUIVI MARITIME TARRERIAS 2026" (gsheet en POC, xlsx serveur
TRANSITAIRE en prod -- décision 30/06) et produit des enregistrements compatibles
avec le loader `src.scripts.gmail.load_ot_gmail` (mêmes clés). Source-agnostique :
le coeur `transform_rows` prend des lignes brutes (list[list[str]]), l'adaptateur
de source (xlsx/csv) est en bout.

Voir docs/profil_suivi_maritime.md (mapping + 7 gotchas). Gérés ici :
- 2 colonnes ETA (estimée / confirmée) -> on prend la confirmée ;
- ETD estimé vs ATD réel -> etd_reel = ATD sinon ETD ;
- dates mois anglais SANS année -> inférence (oct-déc => campagne-1) ;
- calendrier hebdo en bas de feuille -> ignoré (stop au 1er marqueur SEM/jour) ;
- COMMANDE multi-PO -> éclatée et nettoyée (po_numbers) ;
- lignes sans conteneur (bookings futurs) -> exclues (PK ot_transport).

⚠️ Inférence d'année = heuristique (la feuille n'a pas d'année). À valider.

Usage :
    python -m src.scripts.etl.transform_maritime --file "2026 SUIVI MARITIME.xlsx" --out data/_maritime.json
    # puis : python -m src.scripts.gmail.load_ot_gmail --file data/_maritime.json --dry-run
"""
from __future__ import annotations

import argparse
import json
import logging
import re
from datetime import date
from typing import Optional

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s -- %(message)s")
logger = logging.getLogger("transform_maritime")

# Positions (0-based) dans la zone données, en-tête réel "FOURNISSEUR,...".
COL = {
    "fournisseur": 0, "commande": 1, "ref_qualitair": 2, "navire": 6,
    "etd": 7, "eta1": 8, "conteneur": 9, "atd": 10, "eta2": 11,
    "bl": 12, "date_confirmee": 15, "site": 17,
}
MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"], start=1)}
# ISO 6346 conteneur autonome.
RE_CONTAINER = re.compile(r"(?<![A-Za-z0-9-])([A-Z]{4}\d{7})(?![A-Za-z0-9-])")
RE_CAL_STOP = re.compile(r"\bSEM\b|^(janvier|février|mars|avril|mai|juin|juillet|"
                         r"ao[uû]t|septembre|octobre|novembre|décembre)\b", re.I)


def parse_maritime_date(raw: Optional[str], campaign_year: int = 2026) -> Optional[str]:
    """'28 December' / '6 March' -> ISO. Année inférée (oct-déc => campagne-1)."""
    if not raw:
        return None
    m = re.match(r"(\d{1,2})\s+([A-Za-z]+)", str(raw).strip())
    if not m:
        return None
    day = int(m.group(1))
    month = MONTHS.get(m.group(2).lower())
    if not month:
        return None
    year = campaign_year - 1 if month >= 10 else campaign_year
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def clean_pos(commande: Optional[str]) -> list[str]:
    """Éclate COMMANDE multi-PO et nettoie (annotations (PP..), préfixes PO/GE#/TB#)."""
    if not commande:
        return []
    out: list[str] = []
    for tok in str(commande).replace("+", "/").split("/"):
        tok = re.sub(r"\(.*?\)", "", tok)                 # retire (PP 231)
        tok = re.sub(r"\b(PO|GE|TB)#?", "", tok, flags=re.I)  # préfixes
        tok = re.sub(r"[^0-9]", "", tok)                  # garde les chiffres
        if tok:
            out.append(tok.zfill(8) if len(tok) <= 8 else tok)
    return sorted(set(out))


def _cell(row: list[str], idx: int) -> Optional[str]:
    if idx < len(row):
        v = (row[idx] or "").strip()
        return v or None
    return None


def transform_rows(rows: list[list[str]], campaign_year: int = 2026,
                   source_fichier: str = "suivi_maritime") -> list[dict]:
    """Coeur source-agnostique : lignes brutes -> records ot_transport."""
    # 1) localiser l'en-tête réel
    start = next((i for i, r in enumerate(rows)
                  if r and "FOURNISSEUR" in str(r[0]).upper()), None)
    if start is None:
        logger.warning("[ATTENTION] En-tête 'FOURNISSEUR' introuvable.")
        return []

    records: list[dict] = []
    skipped_no_cont = 0
    for row in rows[start + 1:]:
        col0 = _cell(row, 0) or ""
        # 2) stop au calendrier hebdo
        if RE_CAL_STOP.search(col0):
            break
        conteneurs = RE_CONTAINER.findall((_cell(row, COL["conteneur"]) or ""))
        if not conteneurs:
            skipped_no_cont += 1   # booking futur sans conteneur -> hors ot_transport
            continue
        bls = (_cell(row, COL["bl"]) or "").split()
        rec_base = {
            "n_bl": bls[0] if bls else None,
            "etd_reel": parse_maritime_date(_cell(row, COL["atd"]), campaign_year)
                        or parse_maritime_date(_cell(row, COL["etd"]), campaign_year),
            "eta": parse_maritime_date(_cell(row, COL["eta2"]), campaign_year)
                   or parse_maritime_date(_cell(row, COL["eta1"]), campaign_year),
            "transitaire": "QUALITAIR",
            "n_facture": None,
            "lieu_livraison": _cell(row, COL["site"]),
            "po_numbers": clean_pos(_cell(row, COL["commande"])) or None,
            "source_fichier": source_fichier,
        }
        for cont in conteneurs:   # 1 record par conteneur (PK)
            records.append({"n_conteneur": cont, **rec_base})

    logger.info("[SUCCÈS] SUIVI MARITIME : %d conteneur(s) transformé(s) (%d ligne(s) sans conteneur ignorée(s)).",
                len(records), skipped_no_cont)
    return records


def _read_rows(path: str) -> list[list[str]]:
    """Adaptateur source : xlsx/csv -> lignes brutes (header=None, positionnel)."""
    import pandas as pd
    if path.lower().endswith((".xlsx", ".xls", ".xlsm")):
        df = pd.read_excel(path, header=None, dtype=str)
    else:
        df = pd.read_csv(path, header=None, dtype=str)
    return df.fillna("").astype(str).values.tolist()


def main() -> int:
    ap = argparse.ArgumentParser(description="Transform SUIVI MARITIME -> JSON ot_transport.")
    ap.add_argument("--file", required=True, help="xlsx/csv (gsheet exporté en POC, serveur TRANSITAIRE en prod).")
    ap.add_argument("--out", default="", help="JSON de sortie (sinon stdout).")
    ap.add_argument("--campaign-year", type=int, default=2026)
    args = ap.parse_args()

    rows = _read_rows(args.file)
    records = transform_rows(rows, args.campaign_year, source_fichier=args.file.split("/")[-1])
    payload = json.dumps(records, ensure_ascii=False, indent=2)
    if args.out:
        from pathlib import Path
        Path(args.out).write_text(payload, encoding="utf-8")
        logger.info("[SUCCÈS] %d record(s) -> %s", len(records), args.out)
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
