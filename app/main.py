"""
ERP Achat TB Groupe -- API FastAPI
POC : tous les endpoints dans ce fichier. Prod : decomposer en routers/ par domaine.

Modele de donnees (DWH = source de verite, decision 2026-06-10) :
- achat.commande            : rechargee par l'ETL Excel (full-refresh) -- JAMAIS editee ici
- achat.commande_annotation : saisies utilisateur (statut force, ETD, commentaire),
                              jointe par cle metier (po_number, code_article)
- ETD effectif = COALESCE(etd_reel, etd_confirme)
- Retard calcule PAR ARTICLE, les statuts 'Livree'/'Annulee' ne sont jamais en retard
"""
import logging
import secrets
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import text

from app.database import check_connection, get_engine
from src.utils.config_manager import Config

# -- Logging (ASCII pur : la console Windows cp850 corrompt les tirets cadratins) --
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s -- %(message)s",
)
for _noisy in ("azure.core.pipeline", "azure.identity", "urllib3", "sqlalchemy.engine"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

SCHEMA = Config.PG_SCHEMA

# Expression SQL de l'ETD effectif et du statut retard calcule
SQL_ETD_EFF = "COALESCE(c.etd_reel, c.etd_confirme)"
SQL_STATUT_RETARD = f"""
COALESCE(a.statut_retard,
    CASE
        WHEN c.statut IN ('Livrée', 'Annulée')      THEN 'CLOTUREE'
        WHEN {SQL_ETD_EFF} IS NULL                  THEN 'INCONNU'
        WHEN {SQL_ETD_EFF} < CURRENT_DATE           THEN 'EN RETARD'
        ELSE 'DANS LES DELAIS'
    END
)"""


# -- Lifespan ------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    if not check_connection():
        logger.error("[ECHEC] Impossible de joindre PostgreSQL au demarrage.")
    else:
        logger.info("[SUCCES] API ERP Achat prete -- schema : %s", SCHEMA)
    if not Config.API_KEY:
        logger.warning(
            "[ATTENTION] API_KEY absente de config/.env -- "
            "les endpoints d'ecriture sont desactives (fail-closed)."
        )
    yield
    logger.info("Arret API ERP Achat.")


app = FastAPI(title="FUSEAU -- ERP Achat TB Groupe", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=Config.CORS_ORIGINS,
    allow_methods=["GET", "PUT"],
    allow_headers=["Content-Type", "X-API-Key"],
)


# -- Securite ------------------------------------------------------------------
def require_api_key(x_api_key: str = Header(default="")) -> None:
    """Protege les endpoints d'ecriture. Fail-closed si API_KEY non configuree."""
    if not Config.API_KEY:
        raise HTTPException(status_code=503, detail="Ecriture desactivee : API_KEY non configuree cote serveur.")
    if not secrets.compare_digest(x_api_key, Config.API_KEY):
        raise HTTPException(status_code=401, detail="Cle API invalide ou absente (header X-API-Key).")


def internal_error(exc: Exception) -> HTTPException:
    """Log complet cote serveur, message generique cote client (pas de fuite SQL)."""
    logger.error("[ECHEC] Erreur interne : %s", exc, exc_info=True)
    return HTTPException(status_code=500, detail="Erreur interne. Consulter les logs serveur.")


# -- Pydantic models -----------------------------------------------------------
class CommandeAnnotation(BaseModel):
    statut_retard: Optional[str] = None
    date_etd: Optional[date] = None
    commentaire: Optional[str] = None


class ArtworkUpdate(BaseModel):
    statut_artwork: Optional[str] = None
    responsable: Optional[str] = None
    commentaire: Optional[str] = None


STATUTS_RETARD = ["EN RETARD", "DANS LES DELAIS", "INCONNU", "CLOTUREE"]
# Statuts natifs du fichier IMPORT (col N) + statuts de cloture ERP
STATUTS_ARTWORK = [
    "Aucun", "A envoyer", "Envoyé", "Attente Clarisse", "Attente Carrefour",
    "Validé", "Archivé",
]


# -- Helper --------------------------------------------------------------------
def rows_to_dicts(result) -> list[dict[str, Any]]:
    """Convertit un ResultProxy SQLAlchemy en liste de dicts JSON-serialisables."""
    cols = result.keys()
    rows = []
    for row in result:
        d = {}
        for k, v in zip(cols, row):
            d[k] = v.isoformat() if isinstance(v, (datetime, date)) else v
        rows.append(d)
    return rows


# ==============================================================================
# KPIs -- Dashboard
# ==============================================================================
@app.get("/api/kpis")
def get_kpis():
    """Indicateurs recapitulatifs. Graceful degradation par bloc, mais loggee."""
    engine = get_engine()
    kpis: dict[str, Any] = {}

    with engine.connect() as conn:
        try:
            r = conn.execute(text(f"""
                WITH lignes AS (
                    SELECT c.*, {SQL_ETD_EFF} AS etd_eff,
                           a.statut_retard AS statut_force
                    FROM {SCHEMA}.commande c
                    LEFT JOIN {SCHEMA}.commande_annotation a
                        ON a.po_number = c.po_number AND a.code_article = c.code_article
                )
                SELECT
                    COUNT(*)                                          AS total_lignes,
                    COUNT(DISTINCT po_number)                         AS total_po,
                    COUNT(DISTINCT fournisseur)                       AS nb_fournisseurs,
                    COUNT(*) FILTER (
                        WHERE COALESCE(statut_force,
                            CASE WHEN statut IN ('Livrée','Annulée') THEN 'X'
                                 WHEN etd_eff < CURRENT_DATE THEN 'EN RETARD' END
                        ) = 'EN RETARD')                              AS lignes_en_retard,
                    COUNT(*) FILTER (
                        WHERE statut NOT IN ('Livrée','Annulée')
                          AND etd_eff >= CURRENT_DATE)                AS lignes_dans_delais,
                    -- total_prix est un SUMIF par PO repete sur chaque ligne Excel :
                    -- on ne le somme JAMAIS ligne a ligne (surcompte massif).
                    -- Valeur ligne = PU*qte ; lignes de frais (article NULL) = total_prix.
                    ROUND(COALESCE(SUM(
                        CASE WHEN code_article IS NULL THEN COALESCE(total_prix, 0)
                             ELSE COALESCE(prix_unitaire * quantite, 0) END), 0), 2) AS valeur_totale
                FROM lignes
            """))
            row = r.fetchone()
            kpis.update({
                "total_lignes":       int(row[0] or 0),
                "total_po":           int(row[1] or 0),
                "nb_fournisseurs":    int(row[2] or 0),
                "lignes_en_retard":   int(row[3] or 0),
                "lignes_dans_delais": int(row[4] or 0),
                "valeur_totale":      float(row[5] or 0),
            })
        except Exception as e:
            conn.rollback()  # purge la transaction avortee avant le bloc suivant
            logger.warning("[ATTENTION] KPI commande indisponible : %s", e)
            kpis.update({
                "total_lignes": 0, "total_po": 0, "nb_fournisseurs": 0,
                "lignes_en_retard": 0, "lignes_dans_delais": 0, "valeur_totale": 0,
            })

        try:
            r = conn.execute(text(f"""
                SELECT fournisseur, COUNT(*) AS retards
                FROM {SCHEMA}.v_retard_article
                WHERE statut_retard = 'EN RETARD' AND fournisseur IS NOT NULL
                GROUP BY fournisseur
                ORDER BY retards DESC
                LIMIT 5
            """))
            kpis["top_retards_fournisseurs"] = rows_to_dicts(r)
        except Exception as e:
            conn.rollback()
            logger.warning("[ATTENTION] KPI top retards indisponible : %s", e)
            kpis["top_retards_fournisseurs"] = []

        try:
            r = conn.execute(text(f"""
                SELECT
                    COUNT(*)                                                      AS total_artwork,
                    COUNT(*) FILTER (WHERE statut_artwork IN ('Envoyé','Validé')) AS valides,
                    COUNT(*) FILTER (WHERE statut_artwork IN
                        ('A envoyer','Attente Clarisse','Attente Carrefour'))     AS en_attente
                FROM {SCHEMA}.artwork
            """))
            row = r.fetchone()
            kpis.update({
                "artwork_total":      int(row[0] or 0),
                "artwork_valides":    int(row[1] or 0),
                "artwork_en_attente": int(row[2] or 0),
            })
        except Exception as e:
            conn.rollback()
            logger.warning("[ATTENTION] KPI artwork indisponible : %s", str(e).splitlines()[0])
            kpis.update({"artwork_total": 0, "artwork_valides": 0, "artwork_en_attente": 0})

        try:
            r = conn.execute(text(f"SELECT MAX(date_mail) FROM {SCHEMA}.historique_prix"))
            val = r.scalar()
            kpis["derniere_maj_prix"] = val.isoformat() if val else None
        except Exception as e:
            conn.rollback()
            logger.warning("[ATTENTION] KPI historique_prix indisponible (table a creer, P4) : %s",
                           str(e).splitlines()[0])
            kpis["derniere_maj_prix"] = None

    return kpis


# ==============================================================================
# Commandes
# ==============================================================================
@app.get("/api/commandes")
def get_commandes(
    fournisseur: Optional[str] = Query(None),
    statut: Optional[str] = Query(None),
    po_number: Optional[str] = Query(None),
    code_article: Optional[str] = Query(None),
    limit: int = Query(200, le=1000),
    offset: int = Query(0, ge=0),
):
    engine = get_engine()
    filters = []
    params: dict[str, Any] = {"limit": limit, "offset": offset}

    if fournisseur:
        filters.append("LOWER(fournisseur) LIKE :fournisseur")
        params["fournisseur"] = f"%{fournisseur.lower()}%"
    if statut:
        filters.append("statut_retard = :statut")
        params["statut"] = statut
    if po_number:
        filters.append("po_number = :po_number")
        params["po_number"] = po_number
    if code_article:
        filters.append("LOWER(code_article) LIKE :code_article")
        params["code_article"] = f"%{code_article.lower()}%"

    where = ("WHERE " + " AND ".join(filters)) if filters else ""

    with engine.connect() as conn:
        try:
            base = f"""
                FROM (
                    SELECT
                        c.po_number, c.code_article, c.fournisseur, c.designation,
                        c.prix_unitaire, c.quantite, c.statut,
                        {SQL_ETD_EFF}              AS date_etd,
                        c.eta, c.date_livraison,
                        {SQL_STATUT_RETARD}        AS statut_retard,
                        a.commentaire,
                        -- Dernier evenement METIER : annotation ERP sinon date du statut
                        -- (c.updated_at = date du run ETL full-refresh, sans valeur metier)
                        COALESCE(a.updated_at::date, c.date_statut) AS derniere_maj
                    FROM {SCHEMA}.commande c
                    LEFT JOIN {SCHEMA}.commande_annotation a
                        ON a.po_number = c.po_number AND a.code_article = c.code_article
                ) q
                {where}
            """
            total = conn.execute(text(f"SELECT COUNT(*) {base}"), params).scalar()
            r = conn.execute(text(f"""
                SELECT * {base}
                ORDER BY date_etd ASC NULLS LAST
                LIMIT :limit OFFSET :offset
            """), params)
            return {"data": rows_to_dicts(r), "total": int(total or 0),
                    "limit": limit, "offset": offset}
        except Exception as e:
            raise internal_error(e)


@app.put("/api/commandes/{po_number}/{code_article}", dependencies=[Depends(require_api_key)])
def annotate_commande(po_number: str, code_article: str, payload: CommandeAnnotation):
    """
    Annotation metier d'une ligne commande (statut force, ETD, commentaire).
    UPSERT dans achat.commande_annotation : achat.commande n'est JAMAIS modifiee
    ici, elle appartient a l'ETL (DWH source de verite, full-refresh).
    """
    if payload.statut_retard is not None and payload.statut_retard not in STATUTS_RETARD:
        raise HTTPException(status_code=400, detail=f"Statut invalide. Valeurs : {STATUTS_RETARD}")

    engine = get_engine()
    with engine.connect() as conn:
        exists = conn.execute(text(f"""
            SELECT 1 FROM {SCHEMA}.commande
            WHERE po_number = :po AND code_article = :art LIMIT 1
        """), {"po": po_number, "art": code_article}).scalar()
    if not exists:
        raise HTTPException(status_code=404, detail="Commande introuvable.")

    sets, params = [], {"po": po_number, "art": code_article}
    for field in ("statut_retard", "date_etd", "commentaire"):
        val = getattr(payload, field)
        if val is not None:
            sets.append(field)
            params[field] = val
    if not sets:
        raise HTTPException(status_code=400, detail="Aucun champ a mettre a jour.")

    cols = ", ".join(sets)
    vals = ", ".join(f":{f}" for f in sets)
    updates = ", ".join(f"{f} = EXCLUDED.{f}" for f in sets)

    with engine.begin() as conn:
        try:
            conn.execute(text(f"""
                INSERT INTO {SCHEMA}.commande_annotation (po_number, code_article, {cols})
                VALUES (:po, :art, {vals})
                ON CONFLICT (po_number, code_article)
                DO UPDATE SET {updates}, updated_at = NOW()
            """), params)
            return {"ok": True, "annotated": f"{po_number}/{code_article}"}
        except Exception as e:
            raise internal_error(e)


# ==============================================================================
# Fournisseurs
# ==============================================================================
@app.get("/api/fournisseurs")
def get_fournisseurs():
    """Stats consolidees par fournisseur (retards par article via v_retard_article)."""
    engine = get_engine()
    with engine.connect() as conn:
        try:
            r = conn.execute(text(f"""
                SELECT
                    c.fournisseur,
                    COUNT(DISTINCT c.po_number)                       AS nb_po,
                    COUNT(DISTINCT c.code_article)                    AS nb_articles,
                    COUNT(DISTINCT v.code_article) FILTER (
                        WHERE v.statut_retard = 'EN RETARD')          AS nb_retards,
                    ROUND(AVG(v.jours_retard) FILTER (
                        WHERE v.statut_retard = 'EN RETARD'), 0)      AS retard_moyen_jours,
                    MAX(COALESCE(c.date_statut, c.date_commande))     AS derniere_activite
                FROM {SCHEMA}.commande c
                LEFT JOIN {SCHEMA}.v_retard_article v
                    ON v.code_article = c.code_article AND v.fournisseur = c.fournisseur
                WHERE c.fournisseur IS NOT NULL
                GROUP BY c.fournisseur
                ORDER BY nb_retards DESC, nb_po DESC
            """))
            return {"data": rows_to_dicts(r)}
        except Exception as e:
            raise internal_error(e)


@app.get("/api/fournisseurs/{fournisseur}/historique-prix")
def get_historique_prix(fournisseur: str, code_article: Optional[str] = None):
    """Historique des prix : table dediee si presente, sinon fallback achat.commande."""
    engine = get_engine()
    params: dict[str, Any] = {"fournisseur": fournisseur}
    article_filter = ""
    if code_article:
        article_filter = "AND code_article = :code_article"
        params["code_article"] = code_article

    with engine.connect() as conn:
        try:
            r = conn.execute(text(f"""
                SELECT po_number, code_article, fournisseur, prix, date_mail
                FROM {SCHEMA}.historique_prix
                WHERE fournisseur = :fournisseur {article_filter}
                ORDER BY date_mail DESC
                LIMIT 100
            """), params)
            return {"source": "historique_prix", "data": rows_to_dicts(r)}
        except Exception as e:
            # rollback OBLIGATOIRE : une requete echouee avorte la transaction
            # de la connexion, le fallback echouerait en InFailedSqlTransaction
            conn.rollback()
            logger.info("[INFO] historique_prix indisponible -- fallback commande (%s)",
                        str(e).splitlines()[0])

        try:
            r = conn.execute(text(f"""
                SELECT po_number, code_article, fournisseur,
                       prix_unitaire AS prix, date_commande AS date_mail
                FROM {SCHEMA}.commande
                WHERE fournisseur = :fournisseur {article_filter}
                  AND prix_unitaire IS NOT NULL
                ORDER BY date_commande DESC NULLS LAST
                LIMIT 100
            """), params)
            return {"source": "commande_fallback", "data": rows_to_dicts(r)}
        except Exception as e:
            raise internal_error(e)


# ==============================================================================
# Artwork
# ==============================================================================
@app.get("/api/artwork")
def get_artwork(statut: Optional[str] = None, code_article: Optional[str] = None):
    engine = get_engine()
    filters = []
    params: dict[str, Any] = {}

    if statut:
        filters.append("statut_artwork = :statut")
        params["statut"] = statut
    if code_article:
        filters.append("LOWER(code_article) LIKE :code_article")
        params["code_article"] = f"%{code_article.lower()}%"

    where = ("WHERE " + " AND ".join(filters)) if filters else ""

    with engine.connect() as conn:
        try:
            r = conn.execute(text(f"""
                SELECT * FROM {SCHEMA}.artwork
                {where}
                ORDER BY updated_at DESC
                LIMIT 1000
            """), params)
            return {"data": rows_to_dicts(r)}
        except Exception as e:
            if "does not exist" in str(e):
                return {"data": [], "warning": "Table achat.artwork non encore creee (P5 plan action)"}
            raise internal_error(e)


@app.put("/api/artwork/{artwork_id}", dependencies=[Depends(require_api_key)])
def update_artwork(artwork_id: int, payload: ArtworkUpdate):
    if payload.statut_artwork is not None and payload.statut_artwork not in STATUTS_ARTWORK:
        raise HTTPException(status_code=400, detail=f"Statut invalide. Valeurs : {STATUTS_ARTWORK}")

    engine = get_engine()
    updates, params = [], {"id": artwork_id}
    for field in ("statut_artwork", "responsable", "commentaire"):
        val = getattr(payload, field)
        if val is not None:
            updates.append(f"{field} = :{field}")
            params[field] = val
    if not updates:
        raise HTTPException(status_code=400, detail="Aucun champ a mettre a jour.")

    set_clause = ", ".join(updates) + ", updated_at = NOW()"
    with engine.begin() as conn:
        try:
            result = conn.execute(text(f"""
                UPDATE {SCHEMA}.artwork SET {set_clause} WHERE id = :id
            """), params)
            if result.rowcount == 0:
                raise HTTPException(status_code=404, detail="Artwork introuvable.")
            return {"ok": True, "updated": result.rowcount}
        except HTTPException:
            raise
        except Exception as e:
            raise internal_error(e)


# ==============================================================================
# Previsionnel
# ==============================================================================
@app.get("/api/previsionnel")
def get_previsionnel():
    """Agregation planning : livraisons attendues par mois (ETD effectif)."""
    engine = get_engine()
    with engine.connect() as conn:
        try:
            r = conn.execute(text(f"""
                SELECT
                    TO_CHAR({SQL_ETD_EFF}, 'YYYY-MM')       AS mois,
                    c.fournisseur,
                    COUNT(DISTINCT c.po_number)              AS nb_po,
                    COUNT(*)                                 AS nb_articles,
                    SUM(c.quantite)                          AS total_quantite,
                    -- cf. KPI valeur_totale : total_prix = SUMIF par PO, jamais somme ligne a ligne
                    ROUND(SUM(CASE WHEN c.code_article IS NULL THEN COALESCE(c.total_prix, 0)
                                   ELSE COALESCE(c.prix_unitaire * c.quantite, 0) END), 2) AS valeur
                FROM {SCHEMA}.commande c
                WHERE {SQL_ETD_EFF} IS NOT NULL
                  AND {SQL_ETD_EFF} >= CURRENT_DATE - INTERVAL '1 month'
                  AND c.statut NOT IN ('Livrée', 'Annulée')
                GROUP BY 1, 2
                ORDER BY 1, 3 DESC
            """))
            planning = rows_to_dicts(r)

            # Prochaines arrivees = lignes NON livrees/annulees attendues d'ici J+30.
            # Date d'arrivee estimee = ETA (arrivee port) si connue, sinon ETD effectif.
            # Les lignes EN RETARD restent visibles (un retard non livre va arriver) --
            # borne basse large (J-120) pour ecarter seulement les tres vieux dossiers.
            r2 = conn.execute(text(f"""
                SELECT c.po_number, c.code_article, c.fournisseur,
                       COALESCE(c.eta, {SQL_ETD_EFF}) AS date_etd,
                       c.eta, c.quantite, c.prix_unitaire,
                       {SQL_STATUT_RETARD} AS statut
                FROM {SCHEMA}.commande c
                LEFT JOIN {SCHEMA}.commande_annotation a
                    ON a.po_number = c.po_number AND a.code_article = c.code_article
                WHERE c.statut NOT IN ('Livrée', 'Annulée')
                  AND COALESCE(c.eta, {SQL_ETD_EFF})
                      BETWEEN CURRENT_DATE - 120 AND CURRENT_DATE + 30
                ORDER BY 4 ASC
                LIMIT 100
            """))
            prochaines = rows_to_dicts(r2)

            return {"planning_mensuel": planning, "prochaines_arrivees": prochaines}
        except Exception as e:
            raise internal_error(e)


# ==============================================================================
# Sante
# ==============================================================================
@app.get("/api/health")
def health():
    db_ok = check_connection()
    return {
        "status": "ok" if db_ok else "degraded",
        "db": "connected" if db_ok else "unreachable",
        "schema": SCHEMA,
        "write_enabled": bool(Config.API_KEY),
    }


@app.get("/api/qualite")
def get_qualite(
    fournisseur: Optional[str] = None,
    resultat: Optional[str] = None,
    code_article: Optional[str] = None,
):
    """Liste le suivi qualite par produit (checkpoints, inspection DEKRA, NCR)."""
    engine = get_engine()
    filters: list[str] = []
    params: dict[str, Any] = {}
    if fournisseur:
        filters.append("LOWER(fournisseur) LIKE :f")
        params["f"] = f"%{fournisseur.lower()}%"
    if resultat:
        filters.append("resultat_inspection = :r")
        params["r"] = resultat
    if code_article:
        filters.append("LOWER(code_article) LIKE :c")
        params["c"] = f"%{code_article.lower()}%"
    where = ("WHERE " + " AND ".join(filters)) if filters else ""
    with engine.connect() as conn:
        try:
            r = conn.execute(text(f"""
                SELECT * FROM {SCHEMA}.qualite
                {where}
                ORDER BY date_inspection DESC NULLS LAST
                LIMIT 1000
            """), params)
            return {"data": rows_to_dicts(r)}
        except Exception as e:
            if "does not exist" in str(e):
                return {"data": [], "warning": "Table achat.qualite non encore creee -- lancer l'ETL"}
            raise internal_error(e)


@app.get("/api/qualite/fournisseurs")
def get_qualite_fournisseurs():
    """Evaluation qualite agregee par fournisseur (taux FAIL, NCR, receptions NC)."""
    engine = get_engine()
    with engine.connect() as conn:
        try:
            r = conn.execute(text(f"""
                SELECT * FROM {SCHEMA}.v_qualite_fournisseur
                LIMIT 500
            """))
            return {"data": rows_to_dicts(r)}
        except Exception as e:
            if "does not exist" in str(e):
                return {"data": [], "warning": "Vue v_qualite_fournisseur absente -- lancer l'ETL"}
            raise internal_error(e)


# -- Servir le frontend statique ------------------------------------------------
_frontend = Path(__file__).parent.parent / "frontend"
if _frontend.exists():
    app.mount("/", StaticFiles(directory=str(_frontend), html=True), name="frontend")
