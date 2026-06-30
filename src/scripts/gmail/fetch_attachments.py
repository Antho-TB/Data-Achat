# -*- coding: utf-8 -*-
"""
=============================================================================
FETCH PIECES JOINTES GMAIL - PLAN A (API Gmail)
=============================================================================

Récupération des pièces jointes Gmail du service Achats TB Groupe vers le disque.

Contexte : le connecteur MCP Gmail expose les noms et identifiants des pièces
jointes mais ne permet PAS d'en télécharger le contenu. Or le process Achats est
"email-first" : proformas, BL, PO et factures fournisseurs vivent dans les PDF
joints. Ce script comble le trou en utilisant directement l'API Gmail.

Stratégie : on cible une boîte unique (poste Marlène, en copie quasi-systématique
des fils fournisseurs), filtrée par label + présence de pièce jointe. Chaque PJ est
déposée sur le partage réseau dans une arborescence déterministe, et un manifeste
JSON garantit l'idempotence (aucun re-téléchargement). L'ingestion DWH lit ensuite
les fichiers déposés -- ce script ne touche jamais PostgreSQL (séparation des
responsabilités : fetch != load).

C'est le "Plan A" (cf. plan_action.md). Le "Plan B" est un workflow n8n équivalent.

Prérequis (à faire une fois, demain sur le poste cible) :
  1. Console Google Cloud > activer l'API Gmail sur un projet.
  2. Créer un identifiant OAuth "Application de bureau" > télécharger credentials.json.
  3. Déposer credentials.json dans config/ (chemin GMAIL_CREDENTIALS_PATH).
  4. Premier lancement : un navigateur s'ouvre, Marlène consent (scope lecture seule),
     un token.json est mis en cache pour les exécutions suivantes (tâche planifiée).

Usage :
  python -m src.scripts.gmail.fetch_attachments --dry-run        # liste sans télécharger
  python -m src.scripts.gmail.fetch_attachments --since 2025-09-01
  python -m src.scripts.gmail.fetch_attachments                  # incrémental (manifeste)
"""
from __future__ import annotations

import argparse
import base64
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

# Scope minimal : lecture seule. On ne demande JAMAIS plus que nécessaire
# (principe du moindre privilège -- une PJ se lit, elle ne s'écrit pas côté Gmail).
GMAIL_SCOPES: list[str] = ["https://www.googleapis.com/auth/gmail.readonly"]

# Extensions de PJ pertinentes pour les Achats (on ignore les signatures images,
# logos inline, etc. qui polluent sans valeur métier).
ALLOWED_EXTENSIONS: set[str] = {".pdf", ".xlsx", ".xls", ".csv", ".docx", ".doc"}


# --------------------------------------------------------------------------- #
# Configuration                                                               #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class GmailConfig:
    """
    Paramètres du fetch, surchargés par variables d'environnement (config/.env).

    Junior Tip : un dataclass frozen=True est immuable -- une fois construit, on ne
    peut plus modifier ses champs. C'est volontaire : la config se lit au démarrage
    et ne doit jamais muter en cours d'exécution (évite les bugs d'état partagé).
    """

    label: str = "Achats/Fournisseurs"
    credentials_path: Path = field(
        default_factory=lambda: _root() / "config" / "credentials.json"
    )
    token_path: Path = field(
        default_factory=lambda: _root() / "config" / "token.json"
    )
    # Destination des PJ. En prod = partage réseau ; en test = dossier local.
    pj_dir: Path = field(default_factory=lambda: _root() / "data" / "PJ")
    manifest_path: Path = field(
        default_factory=lambda: _root() / "data" / "PJ" / "_manifest.json"
    )
    # Borne basse par défaut si aucun --since ni manifeste (campagne IMPORT 2026).
    default_since: str = "2025-09-01"

    @staticmethod
    def from_env() -> "GmailConfig":
        """Construit la config en appliquant les variables d'environnement si présentes."""
        import os

        from dotenv import load_dotenv

        load_dotenv(dotenv_path=_root() / "config" / ".env")

        def _path(env: str, default: Path) -> Path:
            raw = os.getenv(env)
            return Path(raw) if raw else default

        base = GmailConfig()
        return GmailConfig(
            label=os.getenv("GMAIL_LABEL", base.label),
            credentials_path=_path("GMAIL_CREDENTIALS_PATH", base.credentials_path),
            token_path=_path("GMAIL_TOKEN_PATH", base.token_path),
            pj_dir=_path("GMAIL_PJ_DIR", base.pj_dir),
            manifest_path=_path("GMAIL_PJ_DIR", base.pj_dir) / "_manifest.json"
            if os.getenv("GMAIL_PJ_DIR")
            else base.manifest_path,
            default_since=os.getenv("GMAIL_SINCE", base.default_since),
        )


def _root() -> Path:
    """Racine du projet (src/scripts/gmail/ -> remonter de 3 niveaux)."""
    return Path(__file__).resolve().parent.parent.parent.parent


# --------------------------------------------------------------------------- #
# Authentification Gmail                                                       #
# --------------------------------------------------------------------------- #
def build_service(cfg: GmailConfig):
    """
    Construit le client Gmail authentifié (OAuth installed-app, token mis en cache).

    Junior Tip : le flux "installed app" ouvre un navigateur au premier lancement
    pour le consentement utilisateur, puis stocke un refresh_token dans token.json.
    Les lancements suivants (tâche planifiée) rafraîchissent le token sans interaction
    -- c'est ce qui rend l'automatisation possible sans ressaisie.

    Returns:
        Ressource googleapiclient prête (service.users().messages()...).
    Raises:
        FileNotFoundError: Si credentials.json est absent (prérequis non rempli).
    """
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds: Credentials | None = None
    if cfg.token_path.exists():
        creds = Credentials.from_authorized_user_file(str(cfg.token_path), GMAIL_SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info("[INFO] Token expiré -- rafraîchissement silencieux")
            creds.refresh(Request())
        else:
            if not cfg.credentials_path.exists():
                raise FileNotFoundError(
                    f"credentials.json introuvable : {cfg.credentials_path}. "
                    "Voir les prérequis OAuth en tête de fichier."
                )
            logger.info("[INFO] Consentement OAuth requis -- ouverture du navigateur")
            flow = InstalledAppFlow.from_client_secrets_file(
                str(cfg.credentials_path), GMAIL_SCOPES
            )
            creds = flow.run_local_server(port=0)
        cfg.token_path.write_text(creds.to_json(), encoding="utf-8")
        logger.info("[SUCCÈS] Token mis en cache : %s", cfg.token_path)

    return build("gmail", "v1", credentials=creds, cache_discovery=False)


# --------------------------------------------------------------------------- #
# Manifeste (idempotence)                                                      #
# --------------------------------------------------------------------------- #
def load_manifest(path: Path) -> dict[str, dict]:
    """Charge le manifeste des PJ déjà téléchargées (clé = message_id:attachment_id)."""
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            logger.warning("[ATTENTION] Manifeste corrompu -- réinitialisation")
    return {}


def save_manifest(path: Path, manifest: dict[str, dict]) -> None:
    """Persiste le manifeste (création du dossier parent si besoin)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #
def _slugify(value: str, max_len: int = 60) -> str:
    """
    Nettoie une chaîne pour un usage en nom de fichier/dossier (Windows-safe).

    Junior Tip : Windows interdit \\ / : * ? \" < > | dans les noms de fichiers.
    On les remplace par '_' et on tronque, sinon le dépôt sur le partage réseau
    \\\\Srv-files-pom\\... échouera silencieusement sur les sujets de mail à rallonge.
    """
    value = re.sub(r"[\\/:*?\"<>|\r\n\t]+", "_", value).strip(" ._")
    value = re.sub(r"_+", "_", value)
    return value[:max_len] or "sans_objet"


def _headers_to_dict(headers: list[dict]) -> dict[str, str]:
    """Transforme la liste d'en-têtes Gmail en dict {nom_minuscule: valeur}."""
    return {h["name"].lower(): h.get("value", "") for h in headers}


def _msg_date(internal_date_ms: str) -> str:
    """Convertit internalDate (ms epoch) en 'YYYYMMDD' pour le préfixe fichier."""
    ts = int(internal_date_ms) / 1000
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y%m%d")


@dataclass
class FetchStats:
    """Compteurs de fin de run (pour le log de synthèse)."""

    messages: int = 0
    attachments_seen: int = 0
    downloaded: int = 0
    skipped_existing: int = 0
    skipped_extension: int = 0
    errors: int = 0


# --------------------------------------------------------------------------- #
# Cœur du fetch                                                                #
# --------------------------------------------------------------------------- #
def fetch_attachments(
    cfg: GmailConfig,
    since: str | None = None,
    dry_run: bool = False,
    query_override: str | None = None,
) -> FetchStats:
    """
    Parcourt les messages du label cible et télécharge les PJ pertinentes.

    Args:
        cfg: Configuration (label, chemins, destination).
        since: Date basse 'YYYY-MM-DD' (sinon manifeste vide -> cfg.default_since).
        dry_run: Si True, journalise les PJ candidates sans rien écrire sur disque.
    Returns:
        FetchStats avec les compteurs du run.
    """
    service = build_service(cfg)
    manifest = load_manifest(cfg.manifest_path)
    stats = FetchStats()

    effective_since = since or cfg.default_since
    # Base du filtre : soit une requête libre (--query, ex. ciblage par expéditeur),
    # soit le label configuré. Dans les deux cas on ajoute has:attachment + after.
    base = query_override.strip() if query_override else f"label:{cfg.label}"
    query = f"{base} has:attachment after:{effective_since.replace('-', '/')}"
    logger.info("[INFO] Requête Gmail : %s", query)
    if dry_run:
        logger.info("[INFO] Mode DRY-RUN -- aucun fichier ne sera écrit")

    messages = _list_all_messages(service, query)
    logger.info("[INFO] %d message(s) correspondant au filtre", len(messages))

    for meta in messages:
        stats.messages += 1
        try:
            _process_message(service, cfg, meta["id"], manifest, stats, dry_run)
        except Exception as exc:  # noqa: BLE001 -- on isole l'échec d'un message
            stats.errors += 1
            logger.error("[ÉCHEC] Message %s : %s", meta["id"], exc)

    if not dry_run:
        save_manifest(cfg.manifest_path, manifest)

    logger.info(
        "[SUCCÈS] Terminé -- msg=%d, PJ vues=%d, téléchargées=%d, "
        "déjà présentes=%d, ext ignorées=%d, erreurs=%d",
        stats.messages,
        stats.attachments_seen,
        stats.downloaded,
        stats.skipped_existing,
        stats.skipped_extension,
        stats.errors,
    )
    return stats


def _list_all_messages(service, query: str) -> list[dict]:
    """Pagine la liste des messages correspondant à la requête (gère nextPageToken)."""
    out: list[dict] = []
    page_token: str | None = None
    while True:
        resp = (
            service.users()
            .messages()
            .list(userId="me", q=query, pageToken=page_token, maxResults=100)
            .execute()
        )
        out.extend(resp.get("messages", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            return out


def _process_message(
    service,
    cfg: GmailConfig,
    message_id: str,
    manifest: dict[str, dict],
    stats: FetchStats,
    dry_run: bool,
) -> None:
    """Télécharge les PJ pertinentes d'un message donné."""
    msg = service.users().messages().get(userId="me", id=message_id, format="full").execute()
    headers = _headers_to_dict(msg.get("payload", {}).get("headers", []))
    date_prefix = _msg_date(msg.get("internalDate", "0"))
    sender = _slugify(headers.get("from", "inconnu"), 30)
    subject = _slugify(headers.get("subject", "sans_objet"), 50)

    for part in _iter_parts(msg.get("payload", {})):
        filename = part.get("filename") or ""
        body = part.get("body", {})
        attachment_id = body.get("attachmentId")
        if not filename or not attachment_id:
            continue

        stats.attachments_seen += 1
        ext = Path(filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            stats.skipped_extension += 1
            continue

        key = f"{message_id}:{attachment_id}"
        if key in manifest:
            stats.skipped_existing += 1
            continue

        target = cfg.pj_dir / date_prefix[:6] / f"{date_prefix}_{sender}_{subject}_{_slugify(filename, 70)}"
        if dry_run:
            logger.info("[INFO] (dry-run) -> %s", target.name)
            stats.downloaded += 1
            continue

        data = (
            service.users()
            .messages()
            .attachments()
            .get(userId="me", messageId=message_id, id=attachment_id)
            .execute()
        )
        raw = base64.urlsafe_b64decode(data["data"].encode("utf-8"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        manifest[key] = {
            "filename": filename,
            "saved_as": str(target),
            "from": headers.get("from", ""),
            "subject": headers.get("subject", ""),
            "fetched_at": datetime.now(tz=timezone.utc).isoformat(),
        }
        stats.downloaded += 1
        logger.info("[SUCCÈS] PJ -> %s", target.name)


def _iter_parts(payload: dict):
    """
    Parcours récursif des parties MIME d'un message (PJ imbriquées incluses).

    Junior Tip : un mail multipart est un arbre. Les PJ peuvent être à la racine
    ou nichées dans un sous-multipart (mail transféré, forward de forward...).
    Sans récursion, on rate les PJ des mails transférés -- fréquent côté Achats
    (Andréa forwarde le fournisseur à Marlène).
    """
    yield payload
    for part in payload.get("parts", []) or []:
        yield from _iter_parts(part)


# --------------------------------------------------------------------------- #
# Entrée CLI                                                                   #
# --------------------------------------------------------------------------- #
def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch des PJ Gmail Achats TB Groupe")
    parser.add_argument("--since", help="Date basse YYYY-MM-DD (défaut : manifeste/config)")
    parser.add_argument(
        "--query",
        help="Requête Gmail libre (remplace le label), ex. 'from:qualitairsea.com'",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Liste les PJ candidates sans télécharger ni écrire le manifeste",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    cfg = GmailConfig.from_env()
    logger.info("[INFO] Label=%s | Destination=%s", cfg.label, cfg.pj_dir)
    fetch_attachments(cfg, since=args.since, dry_run=args.dry_run, query_override=args.query)


if __name__ == "__main__":
    main()
