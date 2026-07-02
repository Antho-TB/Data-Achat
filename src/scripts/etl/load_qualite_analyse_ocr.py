# -*- coding: utf-8 -*-
"""
=============================================================================
EXTRACTION mesures SPECTRO (chrome) -> achat.qualite_analyse
=============================================================================
Suite du pilote qualite_doc (load_qualite_doc_drive.py). Les PDF SPECTRO se
sont reveles etre des PDF SANS COUCHE TEXTE (234 images par page, 0 caractere
-- verifie via pdfplumber page.chars/page.images) : l'hypothese initiale
"texte natif extractible sans OCR" (docs/sources_gsheet_drive.md #1/#2)
etait FAUSSE. Pipeline retenu (02/07, valide sur le sandbox Linux -- Windows
MCP bloque par verrouillage de poste au moment du test) :
  1. Telecharger le PDF (connecteur Drive, session interactive uniquement)
  2. Rendre la page en image 300dpi (pdfplumber page.to_image)
  3. OCR (tesseract --psm 6, deja installe sur le sandbox)
  4. Le chrome (%) est la 6e valeur de la ligne moyenne '<x>'/'<>' du premier
     bloc de 10 colonnes -- verifie contre la valeur de reference connue
     (13.36% sur CA183435, cf. docs/sources_gsheet_drive.md) et cross-valide
     par coherence temporelle (les 8 dates de mesure sont strictement
     croissantes dans l'ordre attendu).

Limites assumees (ne PAS combler par une supposition) :
  - hardness_hrc : NULL partout ici -- ces 8 echantillons affichent tous
    'Hardness (HRC) = /NA' (non teste). A brancher des qu'un rapport avec
    durete reelle sera crawle.
  - conformite : NULL -- le champ 'Conformity' du rapport est rendu comme
    image/case a cocher, pas capture de facon fiable par cet OCR generaliste.
    Necessiterait un OCR cible sur la zone (coordonnees) plutot qu'une
    supposition sur la valeur.
  - Perimetre : 8 fichiers / 2 PO (pilote). Passage a l'echelle : meme
    pipeline (download -> render -> OCR -> parse position 6), a executer
    pour chaque nouveau fichier qualite_doc sans ref_rapport encore dans
    qualite_analyse.

Usage (poste, VPN) :
    python -m src.scripts.etl.load_qualite_analyse_ocr --dry-run
    python -m src.scripts.etl.load_qualite_analyse_ocr --commit
"""
from __future__ import annotations

import argparse
import logging

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s -- %(message)s")
logger = logging.getLogger("load_qualite_analyse_ocr")

# Mesures OCR le 02/07 (pipeline render 300dpi + tesseract --psm 6), position
# 6 de la ligne moyenne du premier bloc d'elements -- cf. docstring.
RECORDS: list[dict] = [
    dict(drive_file_id="1w6NoxKrfmdW1Cd0Fe4Pefna-R0gL9Tbm", ref_rapport="CA183435",
         po_number="00181325", echantillon="3", sample_name="PO181325 SP lg herit fromage 3 p éch3 DK",
         cr_pct=13.36, norme="Décret 1976", date_mesure="2026-06-12 09:29:48"),
    dict(drive_file_id="1Yp9djozvGl9snUbXjuJk-Gk7OP-lm77D", ref_rapport="CA183435",
         po_number="00181325", echantillon="3", sample_name="PO181325 SP lg herit foie gras 3p éch3 manche DK",
         cr_pct=16.79, norme="18-0", date_mesure="2026-06-12 09:47:04"),
    dict(drive_file_id="1bmqlGuYuk7II18gxEO2ZcxJMYw2VF22Z", ref_rapport="CA183435",
         po_number="00181325", echantillon="2", sample_name="PO181325 SP lg herit fromage 3 p éch2 tartineur DK",
         cr_pct=13.29, norme="Décret 1976", date_mesure="2026-06-12 09:26:14"),
    dict(drive_file_id="1ccjD6WKgoCu6ewgSeLJiezw6S0FU8VhS", ref_rapport="CA183435",
         po_number="00181325", echantillon="1", sample_name="PO181325 SP lg herit foie gras 3p éch1 DK",
         cr_pct=13.08, norme="Décret 1976", date_mesure="2026-06-12 09:32:35"),
    dict(drive_file_id="1MKU3z2oijN9PoBPnLpERNcuMx3ODwIlj", ref_rapport="CA183435",
         po_number="00181325", echantillon="2", sample_name="PO181325 SP lg herit foie gras 3p éch2 DK",
         cr_pct=13.13, norme="Décret 1976", date_mesure="2026-06-12 09:43:31"),
    dict(drive_file_id="1R5_CDkw8k8a_2AyjFnyNCT7hsHVd3UKO", ref_rapport="CA183435",
         po_number="00181325", echantillon="1", sample_name="PO181325 SP lg herit fromage 3 p éch1 couperet DK",
         cr_pct=13.37, norme="Décret 1976", date_mesure="2026-06-12 09:24:01"),
    dict(drive_file_id="1WNy6Mf8zOCp66pyK0n76mBtpf1O-HssW", ref_rapport="CA183447",
         po_number="00182875", echantillon=None, sample_name="PO182875 MAT 420-2mm open vert DK (NC)",
         cr_pct=16.10, norme="18-0", date_mesure="2026-06-12 09:51:46"),
    dict(drive_file_id="19nBiwfONSGxNZGt704baXXmjUTeMSlrj", ref_rapport="CA183447",
         po_number="00182875", echantillon=None, sample_name="PO182875 MAT 430-1,5mm open vert DF DS TS",
         cr_pct=16.24, norme="18-0", date_mesure="2026-06-12 09:56:39"),
]

SOURCE = "Drive TB -- render 300dpi + tesseract OCR (pilote 02/07, cf. docs/plan_action.md item 7)"


def build_rows() -> list[dict]:
    rows = []
    for r in RECORDS:
        rows.append({
            "drive_file_id": r["drive_file_id"],
            "ref_rapport": r["ref_rapport"],
            "po_number": r["po_number"],
            "echantillon": r.get("echantillon"),
            "sample_name": r["sample_name"],
            "hardness_hrc": None,   # /NA sur les 8 echantillons (cf. docstring)
            "cr_pct": r["cr_pct"],
            "conformite": None,     # non capture de facon fiable (cf. docstring)
            "norme": r["norme"],
            "date_mesure": r["date_mesure"],
            "source_fichier": SOURCE,
        })
    return rows


def load(rows: list[dict], dry_run: bool) -> int:
    import sys
    sys.path.insert(0, ".")
    from src.utils.config_manager import Config
    from sqlalchemy import create_engine, text

    engine = create_engine(Config.get_pg_url())
    n = 0
    with engine.begin() as conn:
        for row in rows:
            logger.info("%s %s | ref=%s PO%s -- Cr%%=%s norme=%s",
                        row["drive_file_id"], "(simule)" if dry_run else "upsert",
                        row["ref_rapport"], row["po_number"], row["cr_pct"], row["norme"])
            if dry_run:
                continue
            conn.execute(text("""
                INSERT INTO achat.qualite_analyse
                    (drive_file_id, ref_rapport, po_number, echantillon, sample_name,
                     hardness_hrc, cr_pct, conformite, norme, date_mesure, source_fichier, charge_le)
                VALUES
                    (:drive_file_id, :ref_rapport, :po_number, :echantillon, :sample_name,
                     :hardness_hrc, :cr_pct, :conformite, :norme, :date_mesure, :source_fichier, NOW())
                ON CONFLICT (drive_file_id) DO UPDATE SET
                    ref_rapport = EXCLUDED.ref_rapport,
                    po_number = EXCLUDED.po_number,
                    echantillon = EXCLUDED.echantillon,
                    sample_name = EXCLUDED.sample_name,
                    hardness_hrc = EXCLUDED.hardness_hrc,
                    cr_pct = EXCLUDED.cr_pct,
                    conformite = EXCLUDED.conformite,
                    norme = EXCLUDED.norme,
                    date_mesure = EXCLUDED.date_mesure,
                    source_fichier = EXCLUDED.source_fichier,
                    charge_le = NOW()
            """), row)
            n += 1
        if dry_run:
            conn.rollback()
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description="Charge les mesures SPECTRO (chrome) OCR -> achat.qualite_analyse.")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--commit", action="store_true")
    args = ap.parse_args()

    rows = build_rows()
    logger.info("[INFO] %d mesure(s) a charger (pilote 2 PO / 8 rapports).", len(rows))
    if not args.dry_run and not args.commit:
        logger.info("Utiliser --dry-run ou --commit.")
        return 0
    n = load(rows, dry_run=args.dry_run)
    if args.dry_run:
        logger.info("[DRY-RUN] %d ligne(s) simulee(s) -- ROLLBACK, rien n'est ecrit.", len(rows))
    else:
        logger.info("[SUCCÈS] %d ligne(s) chargee(s) dans achat.qualite_analyse.", n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
