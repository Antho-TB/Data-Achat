# -*- coding: utf-8 -*-
"""
[ETL]
=============================================================================
CRAWL DRIVE API -- Qualite (Inspection + Results of analysis) -> achat.qualite_doc
=============================================================================
Suite du pilote manuel (load_qualite_doc_drive.py, 8 fichiers / 2 PO indexes
a la main via le connecteur MCP Drive, utilisable en session interactive
seulement). Ce script utilise l'API Google Drive directement (googleapiclient),
via le MEME client OAuth que le Plan A Gmail (src/utils/google_auth.py, scope
drive.readonly ajoute le 02/07) -- pas de session Claude requise, executable
en tache planifiee comme fetch_attachments.py.

Arbitrage 02/07 (docs/plan_action.md, section "Suites pilote Drive qualite") :
API Drive (pas service account/domain-wide delegation) suffit ici -- lecture
seule du Drive de l'utilisateur consentant (Marlene), pas de Drive tiers a
impersonner.

Perimetre : indexation uniquement (achat.qualite_doc). L'extraction des
mesures (chrome, conformite) reste un pipeline separe (load_qualite_analyse_ocr.py) ;
priorite business actee 02/07 = la decision conforme/non-conforme, pas la
valeur brute du chrome -- cf. plan_action.md.

Prerequis (a faire une fois, cote Antho/Marlene) :
  1. Activer "Google Drive API" sur le MEME projet GCP que le Plan A Gmail
     (Console Google Cloud > APIs & Services > Library).
  2. Supprimer config/token.json si un token Gmail-only existe deja (le
     nouveau scope drive.readonly doit etre consenti, cf. google_auth.py).
  3. Renseigner DRIVE_QUALITE_ROOT_ID dans config/.env (ID du dossier racine
     Drive contenant les sous-dossiers PO -- visible dans l'URL Drive du
     dossier : .../folders/<ID>).

Limites connues (best-effort, a valider manuellement si le parsing echoue) :
  - Le nom de PO est extrait du nom de dossier/fichier (regex "PO(\\d+)").
  - stade (SP/MAT/BAT) et ref_rapport (CA\\d+) extraits par regex sur le nom
    de fichier -- pattern verifie sur les 8 fichiers du pilote manuel
    uniquement. Un fichier au nommage different sera charge avec des champs
    NULL plutot que d'inventer une valeur (log en [ATTENTION]).
  - composant (manche, tartineur, couperet...) : PAS extrait automatiquement
    (texte libre trop variable) -- reste NULL ici, contrairement au pilote
    manuel qui l'avait releve a la main.

Usage (poste, VPN si besoin d'ecrire en DB) :
    python -m src.scripts.etl.crawl_drive_qualite --dry-run
    python -m src.scripts.etl.crawl_drive_qualite --commit
"""
from __future__ import annotations

import argparse
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s -- %(message)s")
logger = logging.getLogger("crawl_drive_qualite")

# Sous-dossiers cibles a l'interieur de chaque dossier PO (nommage observe sur
# le pilote 02/07 -- a ajuster si un autre libelle apparait en prod).
TARGET_SUBFOLDERS = {"Inspection", "Results of analysis"}

FOLDER_MIME = "application/vnd.google-apps.folder"

# Regex derivees des 8 fichiers du pilote manuel (load_qualite_doc_drive.py).
RE_PO = re.compile(r"PO\s?0*?(\d{5,8})", re.IGNORECASE)
RE_STADE = re.compile(r"\b(SP|MAT|BAT)\b")
RE_REF_RAPPORT = re.compile(r"\b(CA\d+)\b", re.IGNORECASE)
RE_ECHANTILLON = re.compile(r"[ée]ch\s?(\d+)", re.IGNORECASE)

SOURCE = "Drive TB -- crawl API (crawl_drive_qualite.py, cf. docs/plan_action.md item 7)"


@dataclass(frozen=True)
class CrawlConfig:
    """Config surchargee par variables d'environnement (config/.env)."""

    root_folder_id: str = ""
    credentials_path: Path = field(default_factory=lambda: _root() / "config" / "credentials.json")
    token_path: Path = field(default_factory=lambda: _root() / "config" / "token.json")

    @staticmethod
    def from_env() -> "CrawlConfig":
        import os
        from dotenv import load_dotenv

        load_dotenv(dotenv_path=_root() / "config" / ".env")
        return CrawlConfig(
            root_folder_id=os.getenv("DRIVE_QUALITE_ROOT_ID", ""),
            credentials_path=Path(os.getenv("GMAIL_CREDENTIALS_PATH", str(_root() / "config" / "credentials.json"))),
            token_path=Path(os.getenv("GMAIL_TOKEN_PATH", str(_root() / "config" / "token.json"))),
        )


def _root() -> Path:
    return Path(__file__).resolve().parent.parent.parent.parent


def build_drive_service(cfg: CrawlConfig):
    """Client Drive authentifie (meme token que Gmail, scope drive.readonly)."""
    from googleapiclient.discovery import build

    from src.utils.google_auth import get_credentials

    creds = get_credentials(cfg.credentials_path, cfg.token_path)
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _list_children(service, folder_id: str) -> list[dict]:
    """Liste les enfants directs d'un dossier Drive (id, name, mimeType), pagine."""
    out: list[dict] = []
    page_token: str | None = None
    query = f"'{folder_id}' in parents and trashed = false"
    while True:
        resp = (
            service.files()
            .list(
                q=query,
                fields="nextPageToken, files(id, name, mimeType)",
                pageToken=page_token,
                pageSize=200,
            )
            .execute()
        )
        out.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            return out


def _parse_filename(po_from_folder: str | None, filename: str) -> dict:
    """
    Extrait po_number/stade/ref_rapport/echantillon du nom de fichier (best-effort).

    Junior Tip : on ne devine JAMAIS un champ absent -- si une regex ne matche
    pas, le champ reste None et un [ATTENTION] est logue pour revue manuelle,
    plutot que d'inserer une valeur fausse en base (meme discipline que
    load_qualite_analyse_ocr.py sur hardness_hrc/conformite).
    """
    m_po = RE_PO.search(filename)
    po_number = (m_po.group(1).zfill(8) if m_po else None) or po_from_folder
    m_stade = RE_STADE.search(filename)
    m_ref = RE_REF_RAPPORT.search(filename)
    m_ech = RE_ECHANTILLON.search(filename)
    return {
        "po_number": po_number,
        "stade": m_stade.group(1).upper() if m_stade else None,
        "ref_rapport": m_ref.group(1).upper() if m_ref else None,
        "echantillon": m_ech.group(1) if m_ech else None,
    }


def crawl(service, root_folder_id: str) -> list[dict]:
    """
    Parcourt root_folder_id -> [dossiers PO] -> [Inspection | Results of analysis]
    -> fichiers, et construit les lignes achat.qualite_doc.

    Args:
        service: Client Drive v3 authentifie.
        root_folder_id: ID du dossier racine (config DRIVE_QUALITE_ROOT_ID).
    Returns:
        Liste de dicts prets pour build_rows()/load() (meme forme que
        load_qualite_doc_drive.py).
    """
    rows: list[dict] = []
    po_folders = [f for f in _list_children(service, root_folder_id) if f["mimeType"] == FOLDER_MIME]
    logger.info("[INFO] %d dossier(s) PO trouve(s) sous la racine.", len(po_folders))

    for po_folder in po_folders:
        m_po = RE_PO.search(po_folder["name"])
        po_from_folder = m_po.group(1).zfill(8) if m_po else None
        subfolders = [f for f in _list_children(service, po_folder["id"]) if f["mimeType"] == FOLDER_MIME]

        for sub in subfolders:
            if sub["name"] not in TARGET_SUBFOLDERS:
                continue
            files = [f for f in _list_children(service, sub["id"]) if f["mimeType"] != FOLDER_MIME]
            for f in files:
                if not f["name"].lower().endswith(".pdf"):
                    continue
                parsed = _parse_filename(po_from_folder, f["name"])
                if not parsed["ref_rapport"]:
                    logger.warning("[ATTENTION] ref_rapport non extrait -- %s (dossier %s)", f["name"], po_folder["name"])
                rows.append({
                    "drive_file_id": f["id"],
                    "po_number": parsed["po_number"],
                    "societe": "TB",
                    "type": "analyse",
                    "stade": parsed["stade"],
                    "ref_rapport": parsed["ref_rapport"],
                    "composant": None,  # cf. limites connues -- pas extrait automatiquement
                    "echantillon": parsed["echantillon"],
                    "fichier": f["name"],
                    "drive_url": f"https://drive.google.com/file/d/{f['id']}/view",
                    "source_fichier": SOURCE,
                })
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="Crawl Drive API -> achat.qualite_doc (remplace le pilote manuel).")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--commit", action="store_true")
    args = ap.parse_args()

    cfg = CrawlConfig.from_env()
    if not cfg.root_folder_id:
        logger.error("[ÉCHEC] DRIVE_QUALITE_ROOT_ID non configuré (config/.env).")
        return 1

    service = build_drive_service(cfg)
    rows = crawl(service, cfg.root_folder_id)
    logger.info("[INFO] %d fichier(s) qualite trouve(s) au total.", len(rows))

    if not args.dry_run and not args.commit:
        logger.info("Utiliser --dry-run ou --commit.")
        return 0

    # Reutilise le load() deja valide de load_qualite_doc_drive.py (meme UPSERT,
    # meme schema achat.qualite_doc) -- pas de duplication de SQL.
    from src.scripts.etl.load_qualite_doc_drive import load

    n = load(rows, dry_run=args.dry_run)
    if args.dry_run:
        logger.info("[DRY-RUN] %d ligne(s) simulee(s) -- ROLLBACK, rien n'est ecrit.", len(rows))
    else:
        logger.info("[SUCCÈS] %d ligne(s) chargee(s) dans achat.qualite_doc.", n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
