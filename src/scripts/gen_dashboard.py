# -*- coding: utf-8 -*-
"""
[DATA ENGINEERING]
Régénération du dashboard HTML Achats TB Groupe avec données fraîches depuis PostgreSQL.

Stratégie : au lieu de générer un nouveau fichier HTML depuis un template, ce script
injecte directement un bloc `var D={...}` dans le dashboard existant. Cette approche
"HTML-in-place" préserve tous les styles, scripts et personnalisations du dashboard
sans nécessiter de moteur de template (Jinja2, etc.). Les données sont sérialisées
en JSON et substituées via regex dans le bloc script dédié.
Conçu pour être appelé après chaque exécution du pipeline ETL principal.

Usage :
    python -m src.scripts.gen_dashboard
"""
from __future__ import annotations

import json
import logging
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)

# Chemin racine du projet (deux niveaux au-dessus de ce fichier)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_PATH = PROJECT_ROOT / "dashboard_achats.html"

_STATUTS_TERMINES = {"Livrée", "Annulée", "Payée", "Livree", "Annulee", "Payee"}

SQL_COMMANDES = """
    SELECT
        po_number, men_number, intermediaire, fournisseur,
        code_article, designation, quantite, prix_unitaire, total_prix,
        statut, date_statut, date_commande,
        etd_confirme, etd_reel, eta, date_livraison,
        n_bl, n_conteneur, retard_jours
    FROM achat.commande
    ORDER BY date_commande DESC NULLS LAST
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_str(v: Any) -> str:
    """
    Convertit une valeur pandas en str propre, en remplaçant NaN/NaT par une chaîne vide.

    Junior Tip : `v != v` est le test NaN le plus rapide en Python -- NaN est la seule
    valeur pour laquelle l'égalité avec elle-même est False (norme IEEE 754).
    On teste aussi les représentations textuelles car pd.read_sql peut produire
    des strings "nan" ou "NaT" selon la version de pandas et le driver psycopg2.

    Args:
        v: Valeur quelconque issue d'un DataFrame pandas.
    Returns:
        Représentation str propre, chaîne vide si valeur manquante.
    """
    if v is None:
        return ""
    if isinstance(v, float) and v != v:  # NaN IEEE 754 -- seule valeur != elle-même
        return ""
    s = str(v)
    return "" if s in ("nan", "NaT", "None", "NaN") else s


def _safe_num(v: Any) -> float | None:
    """
    Convertit en float, retourne None si NaN/None/non convertible.

    Args:
        v: Valeur quelconque (int, float, str, None...).
    Returns:
        float ou None.
    """
    if v is None:
        return None
    try:
        f = float(v)
        return None if f != f else f
    except (TypeError, ValueError):
        return None


def _fmt_date(v: Any) -> str:
    """
    Formate une date YYYY-MM-DD en DD/MM/YYYY pour affichage dans le dashboard.

    Args:
        v: Date au format ISO (str, date, datetime ou None).
    Returns:
        Date au format DD/MM/YYYY, chaîne vide si non convertible.
    """
    if v is None:
        return ""
    s = _safe_str(v)
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    return f"{m.group(3)}/{m.group(2)}/{m.group(1)}" if m else s


def _first_etd(row: pd.Series) -> Any:
    """
    Retourne la première valeur ETD non nulle (confirme > réel) pour un PO donné.

    ETD confirme est la date contractuelle avec le fournisseur ; ETD réel est
    la date effective de départ du port. On affiche confirme en priorité car
    c'est la référence de suivi commerciale jusqu'à ce que le réel soit connu.

    Args:
        row: Ligne du DataFrame commandes.
    Returns:
        Valeur ETD (date ou None).
    """
    for col in ("etd_confirme", "etd_reel"):
        val = row.get(col)
        if val is not None and not pd.isna(val):
            return val
    return None


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

def _build_commandes(df: pd.DataFrame) -> list[dict[str, Any]]:
    result = []
    for _, r in df.iterrows():
        result.append({
            "po":       _safe_str(r["po_number"]),
            "interm":   _safe_str(r["intermediaire"]),
            "frs":      _safe_str(r["fournisseur"]),
            "ref":      _safe_str(r["code_article"]),
            "desig":    _safe_str(r["designation"]),
            "qty":      _safe_num(r["quantite"]),
            "pu":       _safe_num(r["prix_unitaire"]),
            "total":    _safe_num(r["total_prix"]),
            "statut":   _safe_str(r["statut"]),
            "date_cmd": _fmt_date(r["date_commande"]),
            "etd":      _fmt_date(_first_etd(r)),
            "eta":      _fmt_date(r["eta"] if not pd.isna(r["eta"]) else None),
            "bl":       _safe_str(r["n_bl"]),
            "ctn":      _safe_str(r["n_conteneur"]),
            "retard":   _safe_num(r["retard_jours"]),
        })
    return result


def _build_statuts(df: pd.DataFrame) -> list[dict[str, Any]]:
    po_statut = df.drop_duplicates("po_number")["statut"]
    return [{"s": s, "n": int(n)} for s, n in po_statut.value_counts().items()]


def _build_fournisseurs(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Top 10 fournisseurs par CA (dédup par PO)."""
    ca_by_po: dict[str, dict[str, Any]] = {}
    for _, r in df.iterrows():
        po = _safe_str(r["po_number"])
        frs = _safe_str(r["fournisseur"])
        t = _safe_num(r["total_prix"]) or 0.0
        if po not in ca_by_po or ca_by_po[po]["ca"] < t:
            ca_by_po[po] = {"frs": frs, "ca": t}

    agg: dict[str, dict[str, Any]] = {}
    for v in ca_by_po.values():
        f = v["frs"]
        if not f:
            continue
        if f not in agg:
            agg[f] = {"ca": 0.0, "n": 0}
        agg[f]["ca"] += v["ca"]
        agg[f]["n"] += 1

    return sorted(
        [{"f": f, "ca": round(v["ca"], 2), "n": v["n"]} for f, v in agg.items()],
        key=lambda x: x["ca"],
        reverse=True,
    )[:10]


def _build_prix(df: pd.DataFrame) -> list[dict[str, Any]]:
    desig_map: dict[str, str] = {}
    result = []
    for _, r in df.iterrows():
        ref = _safe_str(r["code_article"])
        pu = _safe_num(r["prix_unitaire"])
        if not ref or pu is None:
            continue
        desig_map.setdefault(ref, _safe_str(r["designation"]))
        result.append({
            "c":  ref,
            "d":  desig_map[ref],
            "dt": _fmt_date(r["date_commande"]),
            "f":  _safe_str(r["fournisseur"]),
            "pu": pu,
            "q":  _safe_num(r["quantite"]),
        })
    return result


def _build_en_cours(df: pd.DataFrame) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    for _, r in df.iterrows():
        statut = _safe_str(r["statut"])
        if statut in _STATUTS_TERMINES:
            continue
        po = _safe_str(r["po_number"])
        if not po or po in seen:
            continue
        seen[po] = {
            "po":  po,
            "f":   _safe_str(r["fournisseur"]),
            "s":   statut,
            "etd": _fmt_date(_first_etd(r)),
            "eta": _fmt_date(r["eta"] if not pd.isna(r["eta"]) else None),
            "ret": _safe_num(r["retard_jours"]),
            "ctn": _safe_str(r["n_conteneur"]),
        }
    return list(seen.values())


# ---------------------------------------------------------------------------
# Injection HTML
# ---------------------------------------------------------------------------

def _inject_data(html: str, json_str: str) -> str:
    """
    Injecte le bloc `var D={...}` dans le HTML en remplaçant le bloc data existant.

    Deux cas sont gérés pour la rétrocompatibilité :
    1. Bloc script inline `<script>var D=...;</script>` (format actuel)
    2. Ancien bloc JSON `<script type="application/json" id="D">` (format legacy)

    Junior Tip : re.DOTALL permet au point "." dans le pattern de matcher
    les sauts de ligne, indispensable quand le JSON est formaté sur plusieurs lignes.

    Args:
        html: Contenu HTML du dashboard (lecture fichier .html).
        json_str: Payload JSON sérialisé à injecter.
    Returns:
        HTML modifié avec le nouveau bloc data.
    """
    new_block = f'<script>var D={json_str};</script>'

    # Cas 1 : bloc <script>var D=...;</script> déjà présent (réinjection)
    result = re.sub(
        r'<script>var D=\{.*?\};</script>',
        lambda _: new_block,
        html,
        flags=re.DOTALL,
    )

    # Cas 2 : ancien bloc JSON type application/json
    if result == html:
        result = re.sub(
            r'<script type="application/json" id="D">.*?</script>',
            lambda _: new_block,
            html,
            flags=re.DOTALL,
        )

    if result == html:
        logger.warning("[ATTENTION] Aucun bloc data trouvé -- injection impossible")
    else:
        logger.info("[SUCCÈS] Bloc data injecté (%d chars)", len(json_str))

    # Remplacer l'appel JSON.parse si encore présent
    result = re.sub(
        r"var D=JSON\.parse\(document\.getElementById\(['\"]D['\"]\)\.textContent\);",
        "// D pre-loaded as JS variable",
        result,
    )
    return result


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def generate(dashboard_path: Path = DASHBOARD_PATH) -> None:
    """
    Régénère le dashboard HTML avec les données fraîches de la DB PostgreSQL.

    Orchestre l'extraction SQL, la construction des KPI/structures JSON,
    la sérialisation et l'injection dans le fichier HTML existant.

    Junior Tip : sys.path.insert(0, ...) en début de fonction (et non en tête
    de module) est un pattern délibéré pour éviter les imports circulaires au
    chargement du module -- config_manager n'est résolu qu'à l'appel de generate().

    Args:
        dashboard_path: Chemin vers le fichier dashboard_achats.html à mettre à jour.
    Returns:
        None
    """
    sys.path.insert(0, str(PROJECT_ROOT))
    from src.utils.config_manager import Config  # noqa: PLC0415

    engine = create_engine(Config.get_pg_url())
    logger.info("[INFO] Extraction achat.commande...")

    with engine.connect() as conn:
        df = pd.read_sql(text(SQL_COMMANDES), conn)

    logger.info("[SUCCÈS] Lignes extraites : %d", len(df))

    commandes   = _build_commandes(df)
    statuts     = _build_statuts(df)
    fournisseurs = _build_fournisseurs(df)
    prix        = _build_prix(df)
    en_cours    = _build_en_cours(df)

    ca_total = sum(
        max((_safe_num(r["total_prix"]) or 0.0) for r in commandes if r["po"] == po)
        for po in {r["po"] for r in commandes}
    )

    logger.info("[INFO] KPIs -- POs: %d | en cours: %d | CA: $%,.0f | frs: %d | prix: %d",
                df["po_number"].nunique(), len(en_cours),
                ca_total, len(fournisseurs), len(prix))

    payload: dict[str, Any] = {
        "commandes":    commandes,
        "statuts":      statuts,
        "fournisseurs": fournisseurs,
        "prix":         prix,
        "en_cours":     en_cours,
        "last_update":  datetime.now().strftime("%d/%m/%Y %H:%M"),
    }

    json_str = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
    logger.info("[INFO] JSON sérialisé : %d chars", len(json_str))

    html = dashboard_path.read_text(encoding="utf-8")
    html_new = _inject_data(html, json_str)
    dashboard_path.write_text(html_new, encoding="utf-8")
    logger.info("[SUCCÈS] Dashboard régénéré : %s (%d chars)", dashboard_path, len(html_new))


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s  -- %(message)s",
    )
    for noisy in ("azure.core.pipeline", "azure.identity", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    generate()


if __name__ == "__main__":
    main()
