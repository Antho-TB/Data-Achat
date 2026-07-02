# -*- coding: utf-8 -*-
"""
[ETL]
=============================================================================
INDEXATION Drive qualite (Inspection/Results of analysis) -> achat.qualite_doc
=============================================================================
Tache #5 (docs/plan_action.md) : crawl du Drive TB/GDD (Purchasing orders/PO.../
Inspection + Results of analysis) pour indexer les rapports (lien FAIL->PDF).

Perimetre de CETTE version : liste manuelle des fichiers deja crawles via le
connecteur Drive (POC, 2 PO TB profondement explores le 02/07 -- voir
docs/sources_gsheet_drive.md #1/#2). PAS un crawler automatique -- le
connecteur Drive MCP n'est utilisable qu'en conversation interactive, pas
depuis un script Python autonome sur le poste (pas de credentials Drive
API locales). Passage a l'echelle : soit etendre RECORDS ci-dessous a chaque
nouvelle session (copier les fichiers trouves), soit -- cible prod -- crawler
directement le serveur `\\Srv-files-pom\...\ANALYSES ET INSPECTIONS` en local
(os.walk, plus de limite de session).

Extraction chrome/durete (achat.qualite_analyse, option B du profil) : PAS
FAITE ICI. Le texte SPECTRO renvoye par le connecteur Drive est aplati (perd
la correspondance colonne/valeur) et pdfplumber (qui lit les coordonnees du
PDF et resout ce probleme) n'a pas pu etre valide en session (sandbox Linux
indisponible le 02/07). A refaire avec pdfplumber sur les PDF en local
(poste ou serveur prod) avant de peupler qualite_analyse -- ne jamais
inserer un chrome%/durete non fiable, pire qu'une absence de donnee.

Usage (poste, VPN) :
    python -m src.scripts.etl.load_qualite_doc_drive --dry-run
    python -m src.scripts.etl.load_qualite_doc_drive --commit
"""
from __future__ import annotations

import argparse
import logging

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s -- %(message)s")
logger = logging.getLogger("load_qualite_doc_drive")

# Fichiers reperes le 02/07 sur 2 PO TB (pilote) -- cf. docs/sources_gsheet_drive.md
RECORDS: list[dict] = [
    # PO 00181325 -- Results of analysis / Semi-production samples (stade SP)
    dict(drive_file_id="1w6NoxKrfmdW1Cd0Fe4Pefna-R0gL9Tbm",
         fichier="PO181325 SP lg herit fromage 3 p éch3 DK CA183435.pdf",
         po_number="00181325", stade="SP", ref_rapport="CA183435", echantillon="3", composant=None),
    dict(drive_file_id="1Yp9djozvGl9snUbXjuJk-Gk7OP-lm77D",
         fichier="PO181325 SP lg herit foie gras 3p éch3 manche CA183435.pdf",
         po_number="00181325", stade="SP", ref_rapport="CA183435", echantillon="3", composant="manche"),
    dict(drive_file_id="1bmqlGuYuk7II18gxEO2ZcxJMYw2VF22Z",
         fichier="PO181325 SP lg herit fromage 3 p éch2 tartineur DK CA183435.pdf",
         po_number="00181325", stade="SP", ref_rapport="CA183435", echantillon="2", composant="tartineur"),
    dict(drive_file_id="1ccjD6WKgoCu6ewgSeLJiezw6S0FU8VhS",
         fichier="PO181325 SP lg herit foie gras 3p éch1 DK CA183435.pdf",
         po_number="00181325", stade="SP", ref_rapport="CA183435", echantillon="1", composant=None),
    dict(drive_file_id="1MKU3z2oijN9PoBPnLpERNcuMx3ODwIlj",
         fichier="PO181325 SP lg herit foie gras 3p éch2 DK CA183435.pdf",
         po_number="00181325", stade="SP", ref_rapport="CA183435", echantillon="2", composant=None),
    dict(drive_file_id="1R5_CDkw8k8a_2AyjFnyNCT7hsHVd3UKO",
         fichier="PO181325 SP lg herit fromage 3 p éch 1 couperet DK CA183435.pdf",
         po_number="00181325", stade="SP", ref_rapport="CA183435", echantillon="1", composant="couperet"),
    # PO 00182875 -- Results of analysis / Raw material (stade MAT)
    dict(drive_file_id="1WNy6Mf8zOCp66pyK0n76mBtpf1O-HssW",
         fichier="PO182875 MAT 420-2mm open vert DK CA183447 NC.pdf",  # suffixe NC = Non Conforme (releve filename)
         po_number="00182875", stade="MAT", ref_rapport="CA183447", echantillon=None, composant=None),
    dict(drive_file_id="19nBiwfONSGxNZGt704baXXmjUTeMSlrj",
         fichier="PO182875 MAT 430-1,5 mm open vert DF  DS TS  CA183447.pdf",
         po_number="00182875", stade="MAT", ref_rapport="CA183447", echantillon=None, composant=None),
]

SOURCE = "Drive TB (POC, crawl manuel 02/07 -- pilote 2 PO, cf. docs/sources_gsheet_drive.md)"


def build_rows() -> list[dict]:
    rows = []
    for r in RECORDS:
        rows.append({
            "drive_file_id": r["drive_file_id"],
            "po_number": r["po_number"],
            "societe": "TB",
            "type": "analyse",
            "stade": r["stade"],
            "ref_rapport": r["ref_rapport"],
            "composant": r.get("composant"),
            "echantillon": r.get("echantillon"),
            "fichier": r["fichier"],
            "drive_url": f"https://drive.google.com/file/d/{r['drive_file_id']}/view",
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
            logger.info("%s %s | PO%s stade=%s ref=%s -- %s",
                        row["drive_file_id"], "(simule)" if dry_run else "upsert",
                        row["po_number"], row["stade"], row["ref_rapport"], row["fichier"])
            if dry_run:
                continue
            conn.execute(text("""
                INSERT INTO achat.qualite_doc
                    (drive_file_id, po_number, societe, type, stade, ref_rapport,
                     composant, echantillon, fichier, drive_url, source_fichier, charge_le)
                VALUES
                    (:drive_file_id, :po_number, :societe, :type, :stade, :ref_rapport,
                     :composant, :echantillon, :fichier, :drive_url, :source_fichier, NOW())
                ON CONFLICT (drive_file_id) DO UPDATE SET
                    po_number = EXCLUDED.po_number,
                    societe = EXCLUDED.societe,
                    type = EXCLUDED.type,
                    stade = EXCLUDED.stade,
                    ref_rapport = EXCLUDED.ref_rapport,
                    composant = EXCLUDED.composant,
                    echantillon = EXCLUDED.echantillon,
                    fichier = EXCLUDED.fichier,
                    drive_url = EXCLUDED.drive_url,
                    source_fichier = EXCLUDED.source_fichier,
                    charge_le = NOW()
            """), row)
            n += 1
        if dry_run:
            conn.rollback()
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description="Indexation Drive qualite -> achat.qualite_doc (pilote).")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--commit", action="store_true")
    args = ap.parse_args()

    rows = build_rows()
    logger.info("[INFO] %d fichier(s) a indexer (pilote 2 PO).", len(rows))
    if not args.dry_run and not args.commit:
        logger.info("Utiliser --dry-run ou --commit.")
        return 0
    n = load(rows, dry_run=args.dry_run)
    if args.dry_run:
        logger.info("[DRY-RUN] %d ligne(s) simulee(s) -- ROLLBACK, rien n'est ecrit.", len(rows))
    else:
        logger.info("[SUCCÈS] %d ligne(s) chargee(s) dans achat.qualite_doc.", n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
