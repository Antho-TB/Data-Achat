# -*- coding: utf-8 -*-
"""
[ETL]
=============================================================================
TRANSFORM SUIVI DES ARTWORKS (source #3 Andréa) -> records achat.artwork_statut
=============================================================================

Lit le gsheet "LIS-CON-28-0 Suivi des artworks-import" (Clarisse / Design),
keyé par ARTICLE (Référence, SANS PO), et produit des enregistrements pour
achat.artwork_statut (PK code_article). La vue achat.v_artwork EST ce gsheet
(décision 22/07 : plus de fusion avec achat.artwork/Excel IMPORT, cf.
sql/20260722_artwork_gsheet_only.sql).

Le gsheet réel a 2 onglets, SANS colonne "statut" explicite -- le statut est
l'appartenance à l'onglet lui-même :
  - "Artworks en attente" (8 lignes réelles)   -> statut_artwork = 'En attente'
  - "Liste artworks"      (385 lignes réelles) -> statut_artwork = 'Validé'
⚠️ Avant le 22/07, le statut était déduit d'une heuristique sur les dates
(litéral "NOUVEAU" ou présence d'une date de validation). Ça misclassait par
exemple l'article 32030006 : il a de VRAIES dates de version/validation
passées (26/08/2025) mais reste dans l'onglet "en attente" car une nouvelle
demande de retouche est en cours -- la date ne suffit pas, seul l'onglet fait
foi. D'où le passage à un statut dérivé de l'onglet d'origine, pas des dates.

Les lignes « PAS DE REF » (onglet « Artworks en attente », produits pas encore
commandés donc sans code Sylob attribué) reçoivent un code provisoire
NOUVEAU-<slug designation>, même principe que FRAIS-<slug> déjà utilisé pour
les lignes de frais sans code_article dans achat.commande.

Les 2 onglets n'ont pas les mêmes colonnes : "Artworks en attente" a une date
de demande, une priorité (1->5) et DEUX commentaires distincts (Andréa /
Clarisse-Thomas) ; "Liste artworks" a un valideur et UN commentaire de
validation. On ne les fusionne plus dans un seul champ "commentaire" --
chacun garde sa colonne propre (cf. migration 20260722).

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

# Statuts UNIQUEMENT derives du gsheet (decision 22/07). Voir STATUTS_ARTWORK
# dans app/main.py -- doit rester synchronise avec cette liste.
STATUT_EN_ATTENTE = "En attente"
STATUT_VALIDE = "Validé"


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
    m = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)                    # ISO pandas/openpyxl (cellule Excel typee date -> "2024-06-06 00:00:00")
    if m:
        y, mo, d = (int(x) for x in m.groups())
        return _safe(y, mo, d)
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


def _slug(s: str) -> str:
    """Code synthetique stable a partir d'une designation (meme pattern que
    FRAIS-<slug> deja utilise pour les lignes de frais sans code_article dans
    achat.commande, cf. TASKS.md 30/06)."""
    s = _strip_accents(str(s)).upper()
    s = re.sub(r"[^A-Z0-9]+", "-", s).strip("-")
    return s[:60] or "SANS-DESIGNATION"


def _header_map(row: list[str]) -> dict[str, int]:
    """Construit nom_normalisé -> index pour un en-tête (mapping robuste aux
    2 onglets, qui n'ont pas les memes colonnes ni le meme ordre)."""
    m: dict[str, int] = {}
    for i, cell in enumerate(row):
        n = _norm(cell)
        if "reference" in n and "ref" not in m:
            m["ref"] = i
        elif "designation" in n and "designation" not in m:
            m["designation"] = i
        elif n.startswith("commentaire") and "andrea" in n:
            m["com_andrea"] = i
        elif n.startswith("commentaire") and "clarisse" in n:
            m["com_clarisse_thomas"] = i
        elif n.startswith("commentaire"):          # "Commentaire sur derniere version" (onglet Liste)
            m["com_validation"] = i
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


def transform_rows(tagged_rows: list[tuple[str, list[str]]], source_fichier: str = "suivi_artworks") -> list[dict]:
    """tagged_rows : liste de (nom_onglet, ligne). Le statut est derive du nom
    d'onglet (contient "attente" -> En attente, sinon -> Valide), jamais des
    dates -- cf. cas 32030006 en tete de module."""
    hmap: dict[str, int] = {}
    by_ref: dict[str, dict] = {}   # dédoublonnage : garde la dernière occurrence
    n_skip = 0
    for sheet_name, row in tagged_rows:
        if _is_header(row):
            hmap = _header_map(row)
            continue
        if not hmap:
            continue
        ref = _get(row, hmap.get("ref"))
        designation = _get(row, hmap.get("designation"))
        sans_code = bool(ref) and _norm(ref) in {"pas de ref", "pas de reference"}
        # Titre de bloc/onglet capte parfois comme ref tant que hmap n'est pas
        # reinitialise -- un vrai code_article ne contient jamais d'espace.
        if not ref or (not sans_code and " " in ref.strip()):
            n_skip += 1
            continue
        if sans_code and not designation:
            n_skip += 1
            continue
        code = f"NOUVEAU-{_slug(designation)}" if sans_code else ref
        statut = STATUT_EN_ATTENTE if "attente" in _norm(sheet_name) else STATUT_VALIDE
        version_raw = _get(row, hmap.get("version"))
        validation_raw = _get(row, hmap.get("validation"))
        prio = _get(row, hmap.get("priorite"))
        by_ref[code] = {
            "code_article": code,
            "designation": designation,
            "statut_artwork": statut,
            "date_demande": parse_fr_date(_get(row, hmap.get("demande"))),
            "date_validation": parse_fr_date(validation_raw),
            "derniere_version": parse_fr_date(version_raw),
            "priorite": int(prio) if (prio and prio.isdigit()) else None,
            "valideur": _get(row, hmap.get("valideur")),
            "commentaire": _get(row, hmap.get("com_validation")),
            "commentaire_andrea": _get(row, hmap.get("com_andrea")),
            "commentaire_clarisse_thomas": _get(row, hmap.get("com_clarisse_thomas")),
            "source_fichier": source_fichier,
        }
    logger.info("[SUCCÈS] Artworks : %d article(s) (dédoublonnés), %d ligne(s) sans réf ignorée(s).",
                len(by_ref), n_skip)
    return list(by_ref.values())


def _read_rows(path: str) -> list[tuple[str, list[str]]]:
    """Lit TOUTES les feuilles d'un xlsx (le gsheet source a 2 onglets --
    'Artworks en attente' et 'Liste artworks') et tague chaque ligne avec le
    nom de son onglet (necessaire pour deriver le statut, cf. transform_rows).
    """
    import pandas as pd
    if path.lower().endswith((".xlsx", ".xls", ".xlsm")):
        sheets = pd.read_excel(path, sheet_name=None, header=None, dtype=str)
        rows: list[tuple[str, list[str]]] = []
        for sheet_name, df in sheets.items():
            for r in df.fillna("").astype(str).values.tolist():
                rows.append((sheet_name, r))
        return rows
    df = pd.read_csv(path, header=None, dtype=str)
    return [("csv", r) for r in df.fillna("").astype(str).values.tolist()]


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
