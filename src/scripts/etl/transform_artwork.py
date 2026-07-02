# -*- coding: utf-8 -*-
"""
[ETL]
=============================================================================
TRANSFORM SUIVI DES ARTWORKS (source #3 Andréa) -> records achat.artwork_statut
=============================================================================

Lit le gsheet "LIS-CON-28-0 Suivi des artworks-import" (Clarisse / Design),
keyé par ARTICLE (Référence, SANS PO), et produit des enregistrements pour
achat.artwork_statut (PK code_article). La vue achat.v_artwork fusionne ensuite
avec achat.artwork sur code_article (décision 30/06, pattern A).
Voir docs/profil_artworks.md (2 tableaux empilés, 8 gotchas).

Gérés : 2 blocs empilés (en-têtes/colonnes différents), mapping PAR NOM d'en-tête
(robuste aux décalages), dates FR hétérogènes + littéraux (NOUVEAU, /, #N/A) -> NULL,
filtrage « PAS DE REF » / lignes vides, dédoublonnage par code_article (garde la
dernière occurrence).

⚠️ statut_artwork dérivé (pas de colonne native). À ajuster avec le métier.

Usage :
    python -m src.scripts.etl.transform_artwork --file artworks.xlsx --out data/_artwork.json
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import unicodedata
from datetime import date
from typing import Optional

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s -- %(message)s")
logger = logging.getLogger("transform_artwork")

NULL_LITERALS = {"", "/", "nouveau", "#n/a", "\\#n/a", "n/a", "-"}
_FR_MONTHS = [
    ("janv", 1), ("jan", 1), ("fevr", 2), ("fev", 2), ("mars", 3), ("mar", 3),
    ("avr", 4), ("mai", 5), ("juil", 7), ("juin", 6), ("jui", 6),
    ("aout", 8), ("sept", 9), ("sep", 9), ("oct", 10), ("nov", 11),
    ("dec", 12),
]


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")


def parse_fr_date(raw: Optional[str]) -> Optional[str]:
    """Dates FR hétérogènes -> ISO. Littéraux (NOUVEAU, /, #N/A) -> None."""
    if raw is None:
        return None
    s = str(raw).strip()
    if _strip_accents(s).lower() in NULL_LITERALS:
        return None
    m = re.match(r"(\d{1,2})[/.](\d{1,2})[/.](\d{2,4})$", s)          # 26/03/2024
    if m:
        d, mo, y = (int(x) for x in m.groups())
        y += 2000 if y < 100 else 0
        return _safe(y, mo, d)
    m = re.match(r"(\d{1,2})[-\s]([A-Za-zàâäéèêëîïôöùûüç.]+)[-\s](\d{2,4})$", s)  # 8-avr.-25
    if m:
        d = int(m.group(1)); y = int(m.group(3)); y += 2000 if y < 100 else 0
        tok = _strip_accents(m.group(2)).lower().replace(".", "")
        mo = next((num for pref, num in _FR_MONTHS if tok.startswith(pref)), None)
        return _safe(y, mo, d) if mo else None
    return None


def _safe(y: int, mo: Optional[int], d: int) -> Optional[str]:
    try:
        return date(y, mo, d).isoformat()
    except (ValueError, TypeError):
        return None


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", _strip_accents(str(s)).strip().lower())


def _header_map(row: list[str]) -> dict[str, int]:
    """Construit nom_normalisé -> index pour un en-tête (mapping robuste)."""
    m: dict[str, int] = {}
    for i, cell in enumerate(row):
        n = _norm(cell)
        if "reference" in n and "ref" not in m:
            m["ref"] = i
        elif "designation" in n and "designation" not in m:
            m["designation"] = i
        elif n.startswith("commentaire"):   # AVANT version/validation : "Commentaire
            m.setdefault("commentaires", [])  # sur dernière version" contient "derniere version"
            m["commentaires"].append(i)
        elif "demande artwork" in n:
            m["demande"] = i
        elif "derniere version" in n:
            m["version"] = i
        elif "derniere validation" in n:
            m["validation"] = i
        elif "priorite" in n:
            m["priorite"] = i
        elif n == "valideur":
            m["valideur"] = i
    return m


def _is_header(row: list[str]) -> bool:
    return bool(row) and _norm(row[0]) == "reference"


def _get(row: list[str], idx: Optional[int]) -> Optional[str]:
    if idx is None or idx >= len(row):
        return None
    v = (row[idx] or "").strip()
    return v or None


def _statut(version_raw, validation_raw, date_validation) -> Optional[str]:
    for r in (version_raw, validation_raw):
        if r and _strip_accents(str(r)).strip().lower() == "nouveau":
            return "Nouveau"
    return "Validé" if date_validation else None


def transform_rows(rows: list[list[str]], source_fichier: str = "suivi_artworks") -> list[dict]:
    """Source-agnostique : 2 blocs empilés -> records artwork_statut (dédoublonnés)."""
    hmap: dict[str, int] = {}
    by_ref: dict[str, dict] = {}   # dédoublonnage : garde la dernière occurrence
    n_skip = 0
    for row in rows:
        if _is_header(row):
            hmap = _header_map(row)
            continue
        if not hmap:
            continue
        ref = _get(row, hmap.get("ref"))
        if not ref or _norm(ref) in {"pas de ref", "pas de reference"}:
            n_skip += 1
            continue
        version_raw = _get(row, hmap.get("version"))
        validation_raw = _get(row, hmap.get("validation"))
        date_validation = parse_fr_date(validation_raw)
        comments = " | ".join(
            c for c in (_get(row, i) for i in (hmap.get("commentaires") or [])) if c
        ) or None
        prio = _get(row, hmap.get("priorite"))
        by_ref[ref] = {
            "code_article": ref,
            "designation": _get(row, hmap.get("designation")),
            "statut_artwork": _statut(version_raw, validation_raw, date_validation),
            "date_demande": parse_fr_date(_get(row, hmap.get("demande"))),
            "date_validation": date_validation,
            "derniere_version": parse_fr_date(version_raw),
            "priorite": int(prio) if (prio and prio.isdigit()) else None,
            "valideur": _get(row, hmap.get("valideur")),
            "commentaire": comments,
            "source_fichier": source_fichier,
        }
    logger.info("[SUCCÈS] Artworks : %d article(s) (dédoublonnés), %d ligne(s) sans réf ignorée(s).",
                len(by_ref), n_skip)
    return list(by_ref.values())


def _read_rows(path: str) -> list[list[str]]:
    import pandas as pd
    if path.lower().endswith((".xlsx", ".xls", ".xlsm")):
        df = pd.read_excel(path, header=None, dtype=str)
    else:
        df = pd.read_csv(path, header=None, dtype=str)
    return df.fillna("").astype(str).values.tolist()


def main() -> int:
    ap = argparse.ArgumentParser(description="Transform Suivi artworks -> JSON artwork_statut.")
    ap.add_argument("--file", required=True)
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    rows = _read_rows(args.file)
    records = transform_rows(rows, source_fichier=args.file.split("/")[-1])
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
