# -*- coding: utf-8 -*-
"""
[API]
=============================================================================
API ERP ACHAT - FUSEAU (FastAPI)
=============================================================================

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
    valideur: Optional[str] = None
    commentaire: Optional[str] = None
    commentaire_andrea: Optional[str] = None
    commentaire_clarisse_thomas: Optional[str] = None


STATUTS_RETARD = ["EN RETARD", "DANS LES DELAIS", "INCONNU", "CLOTUREE"]
# Decision 22/07 : le statut artwork s'inspire UNIQUEMENT du gsheet Clarisse
# ("LIS-CON-28-0 Suivi des artworks-import"), qui n'a que 2 onglets = 2 etats.
# Abandon complet des anciens statuts issus de l'Excel IMPORT (col N) --
# "A traiter"/"Envoye"/"Attente Clarisse"/"Attente Carrefour"/"Attente
# Polyflame"/"Archive" ne reflétaient JAMAIS le gsheet, cf.
# sql/20260722_artwork_gsheet_only.sql.
STATUTS_ARTWORK = ["En attente", "Validé"]


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

    # DWH injoignable (VPN nomade non monte) : degrade proprement plutot que 500.
    try:
        conn_cm = engine.connect()
    except Exception as e:
        logger.warning("[ATTENTION] DWH injoignable au calcul des KPI (VPN ?) : %s", e)
        return {
            "db_offline": True,
            "total_lignes": 0, "total_po": 0, "nb_fournisseurs": 0,
            "lignes_en_retard": 0, "lignes_dans_delais": 0, "lignes_inconnu": 0,
            "lignes_livrees": 0, "valeur_totale": 0,
            "top_retards_fournisseurs": [],
        }

    with conn_cm as conn:
        try:
            r = conn.execute(text(f"""
                WITH lignes AS (
                    SELECT c.*, {SQL_ETD_EFF} AS etd_eff,
                           a.statut_retard AS statut_force
                    FROM {SCHEMA}.commande c
                    LEFT JOIN {SCHEMA}.commande_annotation a
                        ON a.po_number = c.po_number AND a.code_article = c.code_article
                    LEFT JOIN {SCHEMA}.acompte ac ON ac.po_number = c.po_number
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
                    -- Lignes ni closes ni datees (ETD reel/confirme absents des deux) --
                    -- avant ce compteur elles disparaissaient silencieusement du dashboard
                    -- (total_lignes ne recollait pas a en_retard + dans_delais). Retour
                    -- metier Point Achat : rendre ce statut visible plutot qu'implicite.
                    COUNT(*) FILTER (
                        WHERE statut NOT IN ('Livrée','Annulée')
                          AND etd_eff IS NULL)                        AS lignes_inconnu,
                    COUNT(*) FILTER (WHERE statut = 'Livrée')          AS lignes_livrees,
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
                "lignes_inconnu":     int(row[5] or 0),
                "lignes_livrees":     int(row[6] or 0),
                "valeur_totale":      float(row[7] or 0),
            })
        except Exception as e:
            conn.rollback()  # purge la transaction avortee avant le bloc suivant
            logger.warning("[ATTENTION] KPI commande indisponible : %s", e)
            kpis.update({
                "total_lignes": 0, "total_po": 0, "nb_fournisseurs": 0,
                "lignes_en_retard": 0, "lignes_dans_delais": 0, "lignes_inconnu": 0,
                "lignes_livrees": 0, "valeur_totale": 0,
            })

        try:
            # Retour metier 21/07 : le nb d'articles EN RETARD n'est pas parlant
            # (77 articles ne dit rien du niveau de gravite). On classe plutot par
            # retard MAXI constate a la commande (v_retard_expedition, figue,
            # grain PO x article) -- "quel est le pire retard vu chez ce fournisseur ?".
            # nb_articles_en_retard conserve en info secondaire (tooltip).
            r = conn.execute(text(f"""
                SELECT
                    e.fournisseur,
                    MAX(e.jours_retard)                                   AS retard_max_jours,
                    COUNT(*) FILTER (WHERE a.statut_retard = 'EN RETARD')  AS nb_articles_en_retard
                FROM {SCHEMA}.v_retard_expedition e
                LEFT JOIN {SCHEMA}.v_retard_article a
                    ON a.code_article = e.code_article AND a.fournisseur = e.fournisseur
                WHERE e.fournisseur IS NOT NULL
                GROUP BY e.fournisseur
                ORDER BY retard_max_jours DESC
                LIMIT 5
            """))
            kpis["top_retards_fournisseurs"] = rows_to_dicts(r)
        except Exception as e:
            conn.rollback()
            logger.warning("[ATTENTION] KPI top retards indisponible : %s", e)
            kpis["top_retards_fournisseurs"] = []

        try:
            # v_artwork = achat.artwork_statut (miroir du gsheet Clarisse),
            # decision 22/07 : plus aucun lien avec l'Excel IMPORT, donc plus
            # que 2 statuts possibles (cf. STATUTS_ARTWORK, sql/20260722_*).
            r = conn.execute(text(f"""
                SELECT
                    COUNT(*)                                             AS total_artwork,
                    COUNT(*) FILTER (WHERE statut_artwork = 'Validé')     AS valides,
                    COUNT(*) FILTER (WHERE statut_artwork = 'En attente') AS en_attente
                FROM {SCHEMA}.v_artwork
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
                        c.prix_unitaire, c.quantite, c.statut, c.n_conteneur,
                        {SQL_ETD_EFF}              AS date_etd,
                        c.eta, c.date_livraison,
                        {SQL_STATUT_RETARD}        AS statut_retard,
                        -- Axes metier ORTHOGONAUX (issus de v_previsionnel) : paiement,
                        -- logistique, inspection. Permettent le cross-tab et l'OTD cote UI
                        -- sans reconflater le statut unique.
                        v.est_a_payer, v.est_a_payer_en_retard,
                        v.est_parti, v.est_livre, v.est_en_retard, v.est_en_inspection,
                        a.commentaire,
                        ac.montant_acompte AS acompte,
                          c.op_client_appro,
                        -- Dernier evenement METIER : annotation ERP sinon date du statut
                        -- (c.updated_at = date du run ETL full-refresh, sans valeur metier)
                        COALESCE(a.updated_at::date, c.date_statut) AS derniere_maj,
                        CASE
                            WHEN a.updated_at IS NOT NULL THEN
                                'Modifie manuellement'
                                || COALESCE(' par ' || a.updated_by, '')
                                || CASE WHEN a.statut_retard IS NOT NULL
                                        THEN ' : statut retard force a "' || a.statut_retard || '"' ELSE '' END
                                || CASE WHEN a.date_etd IS NOT NULL
                                        THEN ' : ETD forcee au ' || to_char(a.date_etd, 'DD/MM/YYYY') ELSE '' END
                                || CASE WHEN a.commentaire IS NOT NULL
                                        THEN ' : commentaire "' || a.commentaire || '"' ELSE '' END
                            WHEN c.statut IS NOT NULL THEN
                                'Statut logistique passe a "' || c.statut || '" (mise a jour automatique ETL)'
                            ELSE 'Mise a jour automatique du statut logistique'
                        END AS type_dernier_evt
                    FROM {SCHEMA}.commande c
                    LEFT JOIN {SCHEMA}.commande_annotation a
                        ON a.po_number = c.po_number AND a.code_article = c.code_article
                    LEFT JOIN {SCHEMA}.acompte ac ON ac.po_number = c.po_number
                    LEFT JOIN {SCHEMA}.v_previsionnel v ON v.id = c.id
                ) q
                {where}
            """
            total = conn.execute(text(f"SELECT COUNT(*) {base}"), params).scalar()
            r = conn.execute(text(f"""
                SELECT * {base}
                ORDER BY po_number ASC, code_article ASC
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
                    -- Retard moyen FIGE (etd_reel - etd_confirme, plancher 0),
                    -- 12 mois glissants -- definition metier 07/07 (v_retard_fournisseur).
                    MAX(rf.retard_moyen_jours)                       AS retard_moyen_jours,
                    MAX(COALESCE(c.date_statut, c.date_commande))     AS derniere_activite,
                    MAX(ca.ca_3ans)                                   AS ca_3ans
                FROM {SCHEMA}.commande c
                LEFT JOIN {SCHEMA}.v_retard_article v
                    ON v.code_article = c.code_article AND v.fournisseur = c.fournisseur
                LEFT JOIN {SCHEMA}.v_retard_fournisseur rf
                    ON rf.fournisseur = c.fournisseur
                LEFT JOIN {SCHEMA}.fournisseur_ca ca ON ca.fournisseur = c.fournisseur
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
    params: dict[str, Any] = {}
    
    if code_article:
        # Recherche globale par article, tous fournisseurs confondus (retour metier 07/07)
        where_clause_h = "WHERE h.code_article = :code_article"
        where_clause = "WHERE code_article = :code_article"
        params["code_article"] = code_article
    else:
        # Recherche limitee au fournisseur
        where_clause_h = "WHERE h.fournisseur = :fournisseur"
        where_clause = "WHERE fournisseur = :fournisseur"
        params["fournisseur"] = fournisseur

    with engine.connect() as conn:
        try:
            # LEFT JOIN produit : libelle metier (designation) au lieu du seul
            # code article brut -- retour utilisateur demo du 07/07 (Antho).
            r = conn.execute(text(f"""
                SELECT h.po_number, h.code_article, COALESCE(p.designation_fr, p.designation_en) AS designation, h.fournisseur, h.prix, h.date_mail
                FROM {SCHEMA}.historique_prix h
                LEFT JOIN {SCHEMA}.produit p ON p.code_article = h.code_article
                {where_clause_h}
                ORDER BY h.date_mail DESC
                LIMIT 100
            """), params)
            return {"source": "historique_prix", "data": rows_to_dicts(r)}
        except Exception as e:
            conn.rollback()
            logger.info("[INFO] historique_prix indisponible -- fallback commande (%s)", str(e).splitlines()[0])

        try:
            # 3 dernieres commandes PAR ARTICLE (besoin metier : evolution recente du prix).
            # ROW_NUMBER fenetre par code_article, on garde les 3 plus recentes.
            # LEFT JOIN produit : libelle metier (designation) -- retour demo 07/07.
            r = conn.execute(text(f"""
                SELECT t.po_number, t.code_article, COALESCE(p.designation_fr, p.designation_en) AS designation, t.fournisseur, t.prix, t.date_mail
                FROM (
                    SELECT po_number, code_article, fournisseur,
                           prix_unitaire AS prix, date_commande AS date_mail,
                           ROW_NUMBER() OVER (PARTITION BY code_article
                                              ORDER BY date_commande DESC NULLS LAST) AS rn
                    FROM {SCHEMA}.commande
                    {where_clause}
                      AND prix_unitaire IS NOT NULL
                ) t
                LEFT JOIN {SCHEMA}.produit p ON p.code_article = t.code_article
                WHERE rn <= 3
                ORDER BY t.code_article, t.date_mail DESC NULLS LAST
            """), params)
            return {"source": "commande_fallback", "data": rows_to_dicts(r)}
        except Exception as e:
            raise internal_error(e)

@app.get("/api/artwork")
def get_artwork(code_article: Optional[str] = None):
    # Decision 22/07 : v_artwork = achat.artwork_statut (gsheet Clarisse),
    # cle = code_article. Le filtre "fournisseur" a ete retire : il n'a
    # jamais eu de sens ici (le gsheet ne connait pas de fournisseur), c'etait
    # un reliquat de l'ancienne vue basee sur achat.artwork/commande.
    engine = get_engine()
    filters = []
    params: dict[str, Any] = {}

    if code_article:
        filters.append("LOWER(code_article) LIKE :code_article")
        params["code_article"] = f"%{code_article.lower()}%"

    where = ("WHERE " + " AND ".join(filters)) if filters else ""

    with engine.connect() as conn:
        try:
            r = conn.execute(text(f"""
                SELECT * FROM {SCHEMA}.v_artwork
                {where}
                ORDER BY updated_at DESC
                LIMIT 1000
            """), params)
            return {"data": rows_to_dicts(r)}
        except Exception as e:
            if "does not exist" in str(e):
                return {"data": [], "warning": "Table achat.artwork_statut non encore creee"}
            raise internal_error(e)


@app.put("/api/artwork/{code_article}", dependencies=[Depends(require_api_key)])
def update_artwork(code_article: str, payload: ArtworkUpdate):
    # Cle = code_article (PK reelle de achat.artwork_statut), plus l'id serial
    # de achat.artwork : depuis le 22/07 ce endpoint edite le miroir du gsheet
    # Clarisse, pas le pipeline commande/PO.
    if payload.statut_artwork is not None and payload.statut_artwork not in STATUTS_ARTWORK:
        raise HTTPException(status_code=400, detail=f"Statut invalide. Valeurs : {STATUTS_ARTWORK}")

    engine = get_engine()
    updates, params = [], {"code_article": code_article}
    for field in ("statut_artwork", "valideur", "commentaire", "commentaire_andrea", "commentaire_clarisse_thomas"):
        val = getattr(payload, field)
        if val is not None:
            updates.append(f"{field} = :{field}")
            params[field] = val
    if not updates:
        raise HTTPException(status_code=400, detail="Aucun champ a mettre a jour.")

    set_clause = ", ".join(updates) + ", charge_le = NOW()"
    with engine.begin() as conn:
        try:
            result = conn.execute(text(f"""
                UPDATE {SCHEMA}.artwork_statut SET {set_clause} WHERE code_article = :code_article
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

            # NOTE 21/07 : l'ancien bloc 'prochaines_arrivees' (bug ETD/ETA -- la colonne
            # affichait ETA sous le libelle ETD) a ete retire. La logistique d'arrivee
            # vit desormais dans l'onglet Conteneurs (voir /api/conteneurs, grain reel
            # ETD/ETA/livraison sans ambiguite).

            # Regroupement par CONTENEUR (unite reelle d'expedition et de paiement).
            # Grain = commande.n_conteneur (porte les lignes article + la valeur),
            # enrichi par ot_transport (ETD reel / ETA / navire / transitaire / BL /
            # destinataire, source maritime). On ne garde que les conteneurs encore
            # en transit (au moins une ligne non livree/annulee).
            r3 = conn.execute(text(f"""
                SELECT
                    c.n_conteneur,
                    MAX(ot.n_bl)                             AS n_bl,
                    MAX(ot.transport)                        AS navire,
                    MAX(ot.transitaire)                      AS transitaire,
                    MAX(ot.lieu_livraison)                   AS destinataire,
                    MAX(COALESCE(ot.etd_reel, c.etd_confirme)) AS etd,
                    MAX(ot.eta)                              AS eta,
                    MAX(ot.date_livraison)                   AS date_livraison,
                    COUNT(DISTINCT c.po_number)              AS nb_po,
                    COUNT(*)                                 AS nb_articles,
                    ROUND(SUM(CASE WHEN c.code_article IS NULL THEN COALESCE(c.total_prix, 0)
                                   ELSE COALESCE(c.prix_unitaire * c.quantite, 0) END), 2) AS valeur
                FROM {SCHEMA}.commande c
                LEFT JOIN {SCHEMA}.ot_transport ot ON ot.n_conteneur = c.n_conteneur
                WHERE c.n_conteneur IS NOT NULL AND c.n_conteneur <> ''
                  AND c.statut <> 'Annulée'
                GROUP BY c.n_conteneur
                HAVING BOOL_OR(c.statut NOT IN ('Livrée', 'Annulée'))
                ORDER BY MAX(COALESCE(ot.eta, ot.etd_reel, c.etd_confirme)) ASC NULLS LAST
            """))
            par_conteneur = rows_to_dicts(r3)

            # Echeancier de paiement (financier / achat de dollar).
            # Regle metier 07/07 : le paiement se declenche au BL, avec 15 j de
            # tolerance -> date d'echeance = ETD reel (BL) sinon ETD confirme, + 15 j.
            # On ventile le RESTANT DU (lignes non payees, hors annulees) par tranche.
            cash = rows_to_dicts(conn.execute(text(f"""
                SELECT tranche,
                       ROUND(SUM(montant), 2) AS montant,
                       COUNT(*)               AS nb
                FROM (
                    SELECT
                        CASE WHEN c.code_article IS NULL THEN COALESCE(c.total_prix, 0)
                             ELSE COALESCE(c.prix_unitaire * c.quantite, 0) END AS montant,
                        CASE
                            WHEN (COALESCE(ot.etd_reel, c.etd_confirme) + 15) <  CURRENT_DATE      THEN '1. En retard'
                            WHEN (COALESCE(ot.etd_reel, c.etd_confirme) + 15) <= CURRENT_DATE + 30 THEN '2. <= 30 j'
                            WHEN (COALESCE(ot.etd_reel, c.etd_confirme) + 15) <= CURRENT_DATE + 60 THEN '3. 31-60 j'
                            WHEN (COALESCE(ot.etd_reel, c.etd_confirme) + 15) <= CURRENT_DATE + 90 THEN '4. 61-90 j'
                            ELSE '5. > 90 j'
                        END AS tranche
                    FROM {SCHEMA}.commande c
                    LEFT JOIN {SCHEMA}.ot_transport ot ON ot.n_conteneur = c.n_conteneur
                    WHERE c.statut <> 'Annulée' AND c.date_paiement IS NULL
                      AND COALESCE(ot.etd_reel, c.etd_confirme) IS NOT NULL
                ) t
                GROUP BY tranche
                ORDER BY tranche
            """)))

            return {
                "planning_mensuel": planning,
                "par_conteneur": par_conteneur,
                "cash_echeances": cash,
            }
        except Exception as e:
            raise internal_error(e)


# ==============================================================================
# Conteneurs (suivi logistique)
# ==============================================================================
@app.get("/api/conteneurs")
def get_conteneurs():
    """Suivi des conteneurs : liste complete (ot_transport enrichi par commande) +
    previsionnel des arrivees par mois sur le mois courant et les 3 suivants.

    Le conteneur est l'unite reelle d'expedition ET de paiement (le BL declenche
    le paiement). On agrege la valeur des lignes commande rattachees a chaque
    conteneur pour donner la lecture financiere par arrivee.
    """
    engine = get_engine()
    with engine.connect() as conn:
        try:
            agg = f"""
                SELECT c.n_conteneur,
                       COUNT(DISTINCT c.po_number) AS nb_po,
                       COUNT(*)                    AS nb_articles,
                       ROUND(SUM(CASE WHEN c.code_article IS NULL THEN COALESCE(c.total_prix, 0)
                                      ELSE COALESCE(c.prix_unitaire * c.quantite, 0) END), 2) AS valeur
                FROM {SCHEMA}.commande c
                WHERE c.statut <> 'Annulée' AND c.n_conteneur IS NOT NULL AND c.n_conteneur <> ''
                GROUP BY c.n_conteneur
            """
            liste = rows_to_dicts(conn.execute(text(f"""
                SELECT ot.n_conteneur, ot.n_bl, ot.transport AS navire, ot.transitaire,
                       ot.lieu_livraison AS destinataire,
                       ot.etd_reel AS etd, ot.eta, ot.date_livraison,
                       COALESCE(a.nb_po, 0) AS nb_po, COALESCE(a.nb_articles, 0) AS nb_articles,
                       COALESCE(a.valeur, 0) AS valeur
                FROM {SCHEMA}.ot_transport ot
                LEFT JOIN ({agg}) a ON a.n_conteneur = ot.n_conteneur
                ORDER BY COALESCE(ot.eta, ot.etd_reel) DESC NULLS LAST
            """)))

            # Previsionnel des arrivees (ETA) : mois courant + 3 suivants.
            previsionnel_m3 = rows_to_dicts(conn.execute(text(f"""
                SELECT TO_CHAR(ot.eta, 'YYYY-MM') AS mois,
                       COUNT(*)                   AS nb_conteneurs,
                       ROUND(SUM(COALESCE(a.valeur, 0)), 2) AS valeur
                FROM {SCHEMA}.ot_transport ot
                LEFT JOIN ({agg}) a ON a.n_conteneur = ot.n_conteneur
                WHERE ot.eta >= date_trunc('month', CURRENT_DATE)
                  AND ot.eta <  date_trunc('month', CURRENT_DATE) + INTERVAL '4 months'
                GROUP BY 1 ORDER BY 1
            """)))

            return {"liste": liste, "previsionnel_m3": previsionnel_m3}
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
            # LEFT JOIN qualite_doc (lien Drive du rapport, via ref_rapport) et
            # qualite_analyse (conformite labo -- chrome/durete) -- retour metier
            # 23/06 : cliquer sur un FAIL doit ouvrir le rapport Drive correspondant.
            r = conn.execute(text(f"""
                SELECT q.*, doc.drive_url, an.conformite
                FROM {SCHEMA}.qualite q
                LEFT JOIN LATERAL (
                    SELECT d.drive_url FROM {SCHEMA}.qualite_doc d
                    WHERE d.ref_rapport = q.ref_rapport AND d.drive_url IS NOT NULL
                    LIMIT 1
                ) doc ON true
                LEFT JOIN LATERAL (
                    SELECT STRING_AGG(DISTINCT a.conformite, ', ') AS conformite
                    FROM {SCHEMA}.qualite_analyse a
                    WHERE a.ref_rapport = q.ref_rapport
                ) an ON true
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


@app.get("/api/previsionnel/mesures")
def get_previsionnel_mesures():
    """Mesures previsionnelles par phase (achete/a payer/en inspection/parti/en retard/livre)
    + ventilation par fournisseur. S'appuie sur la vue achat.v_previsionnel."""
    engine = get_engine()
    phases = [
        ("achete", "est_achete"), ("a_payer", "est_a_payer"),
        ("a_payer_en_retard", "est_a_payer_en_retard"),
        ("en_inspection", "est_en_inspection"), ("parti", "est_parti"),
        ("en_retard", "est_en_retard"), ("livre", "est_livre"),
    ]
    select_phase = ", ".join(
        f"COUNT(*) FILTER (WHERE {col}) AS n_{key}, "
        f"COALESCE(ROUND(SUM(montant) FILTER (WHERE {col}), 2), 0) AS m_{key}"
        for key, col in phases
    )
    with engine.connect() as conn:
        try:
            row = conn.execute(text(f"SELECT {select_phase} FROM {SCHEMA}.v_previsionnel")).mappings().first()
            mesures = [
                {"phase": key, "count": int(row[f"n_{key}"] or 0), "montant": float(row[f"m_{key}"] or 0)}
                for key, _ in phases
            ]
            frs = conn.execute(text(f"""
                SELECT fournisseur,
                       COUNT(*) FILTER (WHERE est_a_payer)       AS a_payer,
                       COUNT(*) FILTER (WHERE est_en_inspection) AS en_inspection,
                       COUNT(*) FILTER (WHERE est_parti)         AS parti,
                       COUNT(*) FILTER (WHERE est_en_retard)     AS en_retard,
                       COALESCE(ROUND(SUM(montant) FILTER (WHERE est_en_retard), 2), 0) AS montant_retard
                FROM {SCHEMA}.v_previsionnel
                WHERE fournisseur IS NOT NULL
                GROUP BY fournisseur
                ORDER BY en_retard DESC, montant_retard DESC
                LIMIT 100
            """))
            return {"mesures": mesures, "par_fournisseur": rows_to_dicts(frs)}
        except Exception as e:
            if "does not exist" in str(e):
                return {"mesures": [], "par_fournisseur": [],
                        "warning": "Vue achat.v_previsionnel absente -- lancer l'ETL"}
            raise internal_error(e)


# -- Servir le frontend statique ------------------------------------------------
_frontend = Path(__file__).parent.parent / "frontend"
if _frontend.exists():
    app.mount("/", StaticFiles(directory=str(_frontend), html=True), name="frontend")
