# -*- coding: utf-8 -*-
"""
[ETL]
=============================================================================
PARSEUR BL / CONFIRMATION D'EMBARQUEMENT (PDF) -> JSON pour achat.ot_transport
=============================================================================

Extrait des PDF d'expédition (BL, confirmation d'embarquement, packing) les
champs niveau EXPÉDITION et émet un JSON prêt pour l'UPSERT achat.ot_transport
(pattern A, décision 30/06) :
    n_conteneur, n_bl, etd_reel, eta, transitaire, n_facture, lieu_livraison
+ po_numbers (liste, pour le lien commande / l'enrichissement etd_confirme).

Chaîne robuste : extraction TEXTE d'abord (pdfplumber). Si le PDF est un scan
(0 texte, cas des docs signés / forwarders), bascule OCR (pytesseract + poppler).

Périmètre : parsing pur, aucune écriture DB ici (l'upsert est fait par le skill
achat-gmail-dwh / un loader). EN pour le code et les logs, FR pour le métier.

⚠️ Regex calées sur les conventions documentées (ISO conteneur, formats de date,
PO 8 chiffres) + l'exemple prouvé BL-SZSE2606480 (PO 00017281/00017639, conteneur
TGBU2004021, ETD 05/06/2026). À VALIDER/affiner sur un vrai BL QUALITAIR (poste
Marlène, data/PJ) — voir les fixtures de test.

Usage (VPN inutile, parsing local) :
    python -m src.scripts.gmail.parse_bl --file data/PJ/BL-XXXX.pdf
    python -m src.scripts.gmail.parse_bl --folder data/PJ --out data/PJ/_parsed.json
"""
from __future__ import annotations

import argparse
import json
import logging
import re
from datetime import date
from pathlib import Path
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s -- %(message)s",
)
logger = logging.getLogger("parse_bl")

# --- Connus métier -----------------------------------------------------------
KNOWN_FORWARDERS = (
    "QUALITAIR", "GEODIS", "SCHENKER", "BOLLORE", "KUEHNE", "NAGEL",
    "DSV", "SINOTRANS", "DHL", "CEVA", "DACHSER", "EXPEDITORS",
)
MONTHS = {
    m: i for i, m in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun",
         "jul", "aug", "sep", "oct", "nov", "dec"], start=1)
}

# ISO 6346 : 4 lettres (3 owner + U/J/Z) + 7 chiffres. Ex : TGBU2004021.
# Lookbehind/lookahead : token AUTONOME, pas collé par '-' ou alphanum (évite le
# faux positif tiré d'un n° BL type "BL-SZSE2606480").
RE_CONTAINER = re.compile(r"(?<![A-Za-z0-9-])([A-Z]{4}\d{7})(?![A-Za-z0-9-])")
# PO TB : 8 chiffres zero-paddes (ex 00017281). On capture aussi les variantes
# explicitement etiquetees "PO".
RE_PO_LABELLED = re.compile(r"(?:P[\./ ]?O|purchase\s*order)[^0-9]{0,12}(\d{6,8})", re.I)
RE_PO_BARE = re.compile(r"\b(0\d{7})\b")
RE_BL_LABELLED = re.compile(
    r"(?:B[\./ ]?L|bill\s*of\s*lading|booking|document)\s*(?:n[o°.]|number|#)?\s*[:\-]?\s*([A-Z0-9][A-Z0-9\-]{5,})",
    re.I,
)
RE_INVOICE = re.compile(r"(?:invoice|facture)\s*(?:n[o°.]|number|#)?\s*[:\-]?\s*([A-Z0-9][A-Z0-9\-/]{3,})", re.I)


def extract_text(pdf_path: Path, ocr_lang: str = "eng+fra") -> str:
    """Texte du PDF : pdfplumber d'abord, OCR (pytesseract) si scan."""
    import pdfplumber  # local import: dépendance optionnelle isolée

    parts: list[str] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            parts.append(page.extract_text() or "")
    text = "\n".join(parts).strip()
    if len(text) >= 30:
        return text
    logger.warning("[OCR] %s : texte vide/insuffisant -> bascule OCR.", pdf_path.name)
    return _ocr(pdf_path, ocr_lang)


def _ocr(pdf_path: Path, ocr_lang: str) -> str:
    """Fallback OCR. Requiert tesseract + poppler installés sur le poste."""
    try:
        import pytesseract
        from pdf2image import convert_from_path
    except ImportError as exc:  # pragma: no cover
        logger.error(
            "[OCR] Dépendances manquantes (%s). Installer : "
            "pip install pytesseract pdf2image + tesseract-ocr + poppler.", exc,
        )
        return ""
    out: list[str] = []
    for img in convert_from_path(str(pdf_path), dpi=300):
        out.append(pytesseract.image_to_string(img, lang=ocr_lang))
    return "\n".join(out).strip()


def _to_iso(raw: str) -> Optional[str]:
    """Normalise une date FR/EN vers ISO YYYY-MM-DD. None si non reconnue."""
    raw = raw.strip()
    m = re.match(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})$", raw)  # 2026-06-05
    if m:
        y, mo, d = map(int, m.groups())
        return _safe_date(y, mo, d)
    m = re.match(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})$", raw)  # 05/06/2026
    if m:
        d, mo, y = (int(x) for x in m.groups())
        y += 2000 if y < 100 else 0
        return _safe_date(y, mo, d)
    m = re.match(r"(\d{1,2})[-\s]([A-Za-z]{3})[A-Za-z]*[-\s,]*(\d{2,4})$", raw)  # 05 Jun 2026
    if m:
        d = int(m.group(1)); mo = MONTHS.get(m.group(2).lower()); y = int(m.group(3))
        y += 2000 if y < 100 else 0
        return _safe_date(y, mo, d) if mo else None
    return None


def _safe_date(y: int, mo: int, d: int) -> Optional[str]:
    try:
        return date(y, mo, d).isoformat()
    except ValueError:
        return None


def _find_labelled_date(text: str, labels: tuple[str, ...]) -> Optional[str]:
    """Cherche une date proche d'un label (ETD, ETA, on board...)."""
    date_pat = r"(\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}|\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-\s][A-Za-z]{3,9}[-\s,]*\d{2,4})"
    for lab in labels:
        m = re.search(lab + r"[^0-9A-Za-z]{0,15}" + date_pat, text, re.I)
        if m:
            iso = _to_iso(m.group(1))
            if iso:
                return iso
    return None


def parse_bl(text: str) -> dict:
    """Extrait les champs expédition d'un texte de BL. Champs absents -> None."""
    containers = sorted(set(RE_CONTAINER.findall(text)))
    pos = sorted(set(RE_PO_LABELLED.findall(text)) | set(RE_PO_BARE.findall(text)))
    pos = [p.zfill(8) for p in pos]  # PO TB sur 8 chiffres

    transitaire = next((f for f in KNOWN_FORWARDERS if f in text.upper()), None)
    bl_m = RE_BL_LABELLED.search(text)
    inv_m = RE_INVOICE.search(text)

    return {
        "n_conteneur": containers[0] if containers else None,
        "n_conteneurs_tous": containers or None,   # multi-conteneurs éventuels
        "n_bl": bl_m.group(1) if bl_m else None,
        "etd_reel": _find_labelled_date(text, ("ETD", "on board", "shipped on board", "départ", "sailing")),
        "eta": _find_labelled_date(text, ("ETA", "arrival", "arrivée")),
        "transitaire": transitaire,
        "n_facture": inv_m.group(1) if inv_m else None,
        "lieu_livraison": None,   # TODO: dépend du gabarit BL réel (port de déchargement)
        "po_numbers": pos or None,
    }


def parse_file(pdf_path: Path, ocr_lang: str = "eng+fra") -> dict:
    text = extract_text(pdf_path, ocr_lang)
    rec = parse_bl(text)
    rec["source_fichier"] = pdf_path.name
    logger.info("[PARSE] %s -> conteneur=%s bl=%s etd=%s eta=%s pos=%s",
                pdf_path.name, rec["n_conteneur"], rec["n_bl"],
                rec["etd_reel"], rec["eta"], rec["po_numbers"])
    return rec


def main() -> int:
    ap = argparse.ArgumentParser(description="Parseur BL PDF -> JSON ot_transport.")
    ap.add_argument("--file", type=str, help="Un PDF.")
    ap.add_argument("--folder", type=str, help="Dossier de PDF (récursif).")
    ap.add_argument("--out", type=str, default="", help="Fichier JSON de sortie (sinon stdout).")
    ap.add_argument("--ocr-lang", type=str, default="eng+fra")
    args = ap.parse_args()

    paths: list[Path] = []
    if args.file:
        paths = [Path(args.file)]
    elif args.folder:
        paths = sorted(Path(args.folder).rglob("*.pdf"))
    else:
        ap.error("Fournir --file ou --folder.")

    records = [parse_file(p, args.ocr_lang) for p in paths]
    payload = json.dumps(records, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(payload, encoding="utf-8")
        logger.info("[SUCCES] %d enregistrement(s) -> %s", len(records), args.out)
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
