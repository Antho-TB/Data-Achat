# -*- coding: utf-8 -*-
"""
[ETL]
=============================================================================
PARSE QUALITÉ #1/#2 -- nom de fichier rapport + extraction texte SPECTRO
=============================================================================

Deux briques (décision 30/06 B) :
- `parse_filename` : décode le nom d'un rapport (PO, stade, échantillon, réf CA…)
  -> record achat.qualite_doc (le `type` analyse/inspection vient du DOSSIER, pas
  du nom : « DK » figure aussi sur les analyses).
- `parse_spectro` : extrait les champs FIABLES du texte d'un rapport labo SPECTRO
  (réf, date mesure, sample name, dureté HRC, conformité, norme) -> qualite_analyse.
  `cr_pct` (chrome) est BEST-EFFORT sur texte aplati ; extraction fiable = tables
  pdfplumber sur le PDF réel (poste). Voir docs/profil_inspections_analyses.md.

EN pour le code, FR pour le métier. Parsing pur, aucune écriture DB ici.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

RE_PO = re.compile(r"PO\s*0*(\d{4,8})", re.I)
RE_CA = re.compile(r"(?<![A-Za-z0-9])(CA\d{4,})(?![A-Za-z0-9])", re.I)
RE_STADE = re.compile(r"\b(SP|MAT|PROD|PP|FT)\b")
RE_ECH = re.compile(r"[eé]ch\.?\s*(\d+)", re.I)
RE_DT = re.compile(r"(\d{2})/(\d{2})/(\d{4})\s+(\d{2}:\d{2}:\d{2})")
RE_HRC = re.compile(r"(\d{1,2}(?:[.,]\d+)?)\s*HRC", re.I)
# Code article TB : 8 chiffres isoles. Utilisee par parse_filename ; le
# litteral equivalent y etait recompile a chaque appel en doublon de cette
# constante, qui n'etait elle jamais utilisee.
RE_CODE_ARTICLE = re.compile(r"(?<!\d)(\d{8})(?!\d)")


def _ressemble_a_une_date(valeur: str) -> bool:
    """Ecarte les suites de 8 chiffres qui sont en realite des dates YYYYMMDD."""
    if len(valeur) != 8:
        return False
    annee, mois, jour = int(valeur[:4]), int(valeur[4:6]), int(valeur[6:])
    return 2000 <= annee <= 2099 and 1 <= mois <= 12 and 1 <= jour <= 31


def parse_filename(title: str, type_doc: Optional[str] = None,
                   societe: Optional[str] = None) -> dict:
    """Décode un nom de rapport qualité. `type_doc`/`societe` viennent du dossier."""
    po = RE_PO.search(title)
    ca = RE_CA.search(title)
    stade = RE_STADE.search(title)
    ech = RE_ECH.search(title)

    po_val = po.group(1).zfill(8) if po else None
    art_val = None
    for a in RE_CODE_ARTICLE.findall(title):
        # Ecarter le PO lui-meme et les dates compactees (20260715) : sinon la
        # date du rapport passait pour un code article.
        if po_val and a in (po.group(1), po_val):
            continue
        if _ressemble_a_une_date(a):
            continue
        art_val = a
        break

    return {
        "po_number": po_val,
        "ref_rapport": ca.group(1).upper() if ca else None,
        "code_article": art_val,
        "stade": stade.group(1) if stade else None,
        "echantillon": ech.group(1) if ech else None,
        "type": type_doc,
        "societe": societe,
        "fichier": title,
    }


def resolve_code_article_from_po(po_number: str, engine=None) -> list[str]:
    """
    Rapproche un numéro de PO avec les code_article associés dans achat.commande.

    Sert de repli quand le nom du rapport ne porte pas de code article
    exploitable : le PO, lui, est presque toujours présent.

    Args:
        po_number: numéro de PO extrait du nom de fichier.
        engine: moteur SQLAlchemy, résolu automatiquement si absent.
    Returns:
        Codes article rattachés au PO, liste vide si aucun ou en cas d'échec.
    """
    if not po_number:
        return []
    if engine is None:
        try:
            from app.database import get_engine
            engine = get_engine()
        except Exception as exc:
            logger.warning("[ATTENTION] Connexion indisponible pour résoudre le PO %s : %s",
                           po_number, exc)
            return []
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            r = conn.execute(text(
                "SELECT DISTINCT code_article FROM achat.commande "
                "WHERE po_number = :po AND code_article IS NOT NULL"
            ), {"po": str(po_number).zfill(8)})
            return [row[0] for row in r.fetchall()]
    except Exception as exc:
        # Un except silencieux rendait une panne SQL indiscernable d'un PO
        # réellement sans article rattaché.
        logger.warning("[ATTENTION] Résolution du code article impossible pour le PO %s : %s",
                       po_number, exc)
        return []


def _after(label: str, text: str, window: int = 60) -> Optional[str]:
    """Retourne le 1er fragment non vide après un label (texte SPECTRO aplati)."""
    m = re.search(re.escape(label), text, re.I)
    if not m:
        return None
    tail = text[m.end():m.end() + window]
    for part in re.split(r"\n+", tail):
        part = part.strip()
        if part:
            return part
    return None


def parse_spectro(text: str) -> dict:
    """Champs fiables d'un rapport labo SPECTRO. cr_pct = best-effort."""
    ca = RE_CA.search(text)
    dt = RE_DT.search(text)
    date_mesure = None
    if dt:
        d, mo, y, hms = dt.groups()
        date_mesure = f"{y}-{mo}-{d}T{hms}"

    sample = _after("Sample Name", text)
    # dureté : après "Hardness (HRC)" ; « /NA » ou non numérique -> None
    hardness = None
    h = RE_HRC.search(text)
    if h:
        hardness = float(h.group(1).replace(",", "."))
    else:
        after_h = _after("Hardness (HRC)", text, 20)
        if after_h and re.match(r"^\d{1,2}([.,]\d+)?$", after_h):
            hardness = float(after_h.replace(",", "."))

    low = text.lower()
    norme = "Alimentarité acier inox (décret 1976)" if "décret 1976" in low or "decret 1976" in low else None
    conformite = None
    if re.search(r"non[\s-]*conform", low):
        conformite = "Non conforme"
    elif "conformity" in low or "conforme" in low:
        conformite = "Conforme"

    # chrome : best-effort -- 1re valeur plausible d'inox [11.5, 20] proche d'un "Cr"
    cr = None
    mcr = re.search(r"\bCr\b", text)
    if mcr:
        for v in re.findall(r"\b(1[1-9](?:[.,]\d+)?|20(?:[.,]0+)?)\b", text[mcr.end():mcr.end() + 400]):
            f = float(v.replace(",", "."))
            if 11.5 <= f <= 20.0:
                cr = f
                break

    return {
        "ref_rapport": ca.group(1).upper() if ca else None,
        "sample_name": sample,
        "hardness_hrc": hardness,
        "cr_pct": cr,
        "conformite": conformite,
        "norme": norme,
        "date_mesure": date_mesure,
    }
