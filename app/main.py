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

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
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

# Bornes des endpoints de rapports qualite : sans LIMIT, la requete balayait
# les tables entieres jointes a achat.commande.
RAPPORTS_LIMIT_DEFAUT = 200
RAPPORTS_LIMIT_MAX = 1000

# Au-dela, un retard n'est plus un retard mais une anomalie de donnee (ETD mal
# saisi, commande fantome). On les isole dans un seau dedie au lieu de les
# faire disparaitre du classement : ce sont justement les cas a regarder.
SEUIL_RETARD_ABERRANT_JOURS = 180

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
    if Config.AUTH_MODE == "entra":
        logger.info(
            "[INFO] Authentification deleguee a la plateforme Entra ID "
            "(mode heberge) -- aucune cle applicative attendue."
        )
    elif not Config.API_KEY:
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
    allow_headers=["Content-Type", "X-API-Key", "X-MS-CLIENT-PRINCIPAL-NAME"],
)


@app.middleware("http")
async def revalider_html(request, call_next):
    """Oblige le navigateur a revalider la page a chaque chargement.

    StaticFiles n'envoie que ETag et Last-Modified. Sans Cache-Control, Chrome
    garde index.html en cache par heuristique : le 25/09, un correctif deploye
    restait invisible chez Marlene. no-cache ne supprime pas le cache, il impose
    la revalidation (304 si la page n'a pas change, donc sans surcout).
    """
    response = await call_next(request)
    if response.headers.get("content-type", "").startswith("text/html"):
        response.headers["Cache-Control"] = "no-cache"
    return response


# -- Securite ------------------------------------------------------------------
# Deux contextes d'execution, deux barrieres, jamais les deux desactivees.
#
#   AUTH_MODE=apikey (poste metier, dev local) : la cle X-API-Key est exigee sur
#   les ecritures, fail-closed si la cle n'est pas configuree cote serveur.
#
#   AUTH_MODE=entra (application hebergee en Azure, decision du 03/09/2026) :
#   l'authentification de plateforme App Service redirige tout visiteur non
#   authentifie vers le login Microsoft 365. L'utilisateur est donc deja connu
#   quand la requete arrive, et Azure injecte son identite dans les en-tetes
#   X-MS-CLIENT-PRINCIPAL-NAME / -ID. On refuse quand meme l'ecriture si ces
#   en-tetes sont absents : cela signifierait que l'authentification de
#   plateforme est desactivee ou contournee, et le silence serait pire que
#   l'erreur.
def require_utilisateur(
    x_api_key: str = Header(default=""),
    x_ms_client_principal_name: str = Header(default=""),
    x_ms_client_principal_id: str = Header(default=""),
) -> str:
    """
    Autorise une ecriture et retourne l'identifiant de l'auteur.

    Junior Tip : FastAPI convertit le nom de l'argument en nom d'en-tete HTTP
    (les tirets bas deviennent des tirets), donc `x_ms_client_principal_name`
    lit bien l'en-tete `X-MS-CLIENT-PRINCIPAL-NAME` pose par App Service.

    Returns:
        Identite de l'auteur, a tracer dans les tables d'annotation.
    Raises:
        HTTPException: 503 si le serveur est mal configure, 401 si l'appelant
            n'est pas authentifie.
    """
    if Config.AUTH_MODE == "entra":
        identite = x_ms_client_principal_name or x_ms_client_principal_id
        if not identite:
            raise HTTPException(
                status_code=401,
                detail="Non authentifie : aucune identite Microsoft 365 transmise par la plateforme.",
            )
        return identite

    if Config.AUTH_MODE != "apikey":
        raise HTTPException(
            status_code=503,
            detail=f"AUTH_MODE invalide cote serveur : {Config.AUTH_MODE!r}. Valeurs admises : apikey, entra.",
        )

    if not Config.API_KEY:
        raise HTTPException(status_code=503, detail="Ecriture desactivee : API_KEY non configuree cote serveur.")
    if not secrets.compare_digest(x_api_key, Config.API_KEY):
        raise HTTPException(status_code=401, detail="Cle API invalide ou absente (header X-API-Key).")
    return "poste-metier"


# Nom historique conserve : les dependances des endpoints d'ecriture le citent.
require_api_key = require_utilisateur


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


def normaliser_po(po: Any) -> str:
    """PO sans espaces ni zeros de tete : Sylob ecrit 0181325, l'IMPORT 181325."""
    return str(po or "").strip().lstrip("0")


# Ecart maximal entre la creation Sylob et la date de commande IMPORT pour
# rattacher un PO a la bonne societe (les numeros se repetent entre GDD, SE, Cie).
MAX_ECART_JOURS_SOCIETE = 180


def intitules_commande_sylob(conn: Any, pos: list[Any]) -> dict[str, str]:
    """
    Intitule de la commande dans Sylob (commande_reference), par PO normalise.

    Besoin metier (Antho, 05/10/2026) : les promotions et operations sont portees
    par l'intitule de la commande Sylob ("OP SYSTEM U 2026", "OP TOP CHEF 2026"),
    pas par une source a part. Sylob est la source de verite ; la colonne
    op_client_appro de l'IMPORT n'est qu'une recopie manuelle, gardee en repli.

    Junior Tip : la lecture se fait dans un SAVEPOINT. Sans droit SELECT sur la
    copie MyReport (droit perdu a chaque recreation de table par l'ETL MyReport),
    la requete echoue ; le savepoint annule cette seule requete et laisse la
    transaction utilisable pour le reste de l'endpoint.

    Returns:
        {po_normalise: intitule}, vide si la copie MyReport est illisible.
    """
    cles = sorted({normaliser_po(p) for p in pos if normaliser_po(p)})
    if not cles:
        return {}
    table = f'"{Config.MYREPORT_SCHEMA}"."{Config.MYREPORT_TABLE_COMMANDES}"'
    sql = text(f"""
        SELECT DISTINCT ON (po) po, intitule
        FROM (
            SELECT LTRIM(TRIM(c.po_number::text), '0') AS po,
                   NULLIF(TRIM(m.commande_reference), '') AS intitule,
                   ABS(m.commande_creee_le::date - c.date_commande) AS ecart
            FROM {SCHEMA}.commande c
            JOIN {table} m
              ON LTRIM(TRIM(m.commande_numero_de_la_commande), '0')
               = LTRIM(TRIM(c.po_number::text), '0')
            WHERE LTRIM(TRIM(c.po_number::text), '0') = ANY(:pos)
        ) x
        WHERE intitule IS NOT NULL AND (ecart IS NULL OR ecart <= :max_ecart)
        ORDER BY po, ecart NULLS LAST
    """)
    try:
        with conn.begin_nested():
            rows = conn.execute(
                sql, {"pos": cles, "max_ecart": MAX_ECART_JOURS_SOCIETE}).fetchall()
        return {po: intitule for po, intitule in rows}
    except Exception as exc:
        logger.warning("[ATTENTION] Intitules Sylob illisibles dans %s (%s), essai du pont "
                       "achat.fn_myreport_intitules_commande", table, str(exc).splitlines()[0])
    # Pont SECURITY DEFINER (sql/20261005_pont_lecture_myreport_fuseau.sql), en
    # attendant le default privilege du proprietaire MyReport.
    try:
        with conn.begin_nested():
            rows = conn.execute(
                text("SELECT po, intitule FROM achat.fn_myreport_intitules_commande(:pos, :max_ecart)"),
                {"pos": cles, "max_ecart": MAX_ECART_JOURS_SOCIETE}).fetchall()
        return {po: intitule for po, intitule in rows}
    except Exception as exc:
        logger.warning("[ATTENTION] Pont MyReport indisponible, repli sur l'IMPORT (%s)",
                       str(exc).splitlines()[0])
        return {}


# Types de fiche Sylob qui concernent un achat : non-conformite a la reception
# et non-conformite transporteur. Les fiches de production (NCP), d'audit ou
# d'environnement ne se rattachent pas a une commande fournisseur.
TYPES_FICHE_NCR_ACHAT = ("NCR", "NCT")


def non_conformites_mail(conn: Any, pos: list[Any]) -> list[dict[str, Any]]:
    """
    Non-conformites encore ouvertes, captees dans le corps des mails par la tache
    Cowork (achat.qualite_decision).

    Une non-conformite est ouverte quand la DERNIERE decision d'un stade, pour un
    PO et un article, est "non_conforme" : un "conforme" posterieur au meme stade
    la referme (reprise, remplacement des defectueux).

    Returns:
        Une ligne par (po normalise, code_article, stade) ouvert. code_article vaut
        None quand la decision porte sur tout le PO.
    """
    cles = sorted({normaliser_po(p) for p in pos if normaliser_po(p)})
    if not cles:
        return []
    return rows_to_dicts(conn.execute(text(f"""
        SELECT po, code_article, stade, date_info, motif, acteur
        FROM (
            SELECT DISTINCT ON (LTRIM(TRIM(d.po_number), '0'), d.code_article, d.stade)
                   LTRIM(TRIM(d.po_number), '0') AS po, NULLIF(TRIM(d.code_article), '') AS code_article,
                   d.stade, d.decision, d.date_info, d.motif, d.acteur
            FROM {SCHEMA}.qualite_decision d
            WHERE LTRIM(TRIM(d.po_number), '0') = ANY(:pos) AND d.decision IS NOT NULL
            ORDER BY LTRIM(TRIM(d.po_number), '0'), d.code_article, d.stade,
                     d.date_info DESC NULLS LAST, d.created_at DESC
        ) x
        WHERE decision = 'non_conforme'
    """), {"pos": cles}))


def fiches_ncr_sylob(conn: Any, codes_article: list[Any]) -> list[dict[str, Any]]:
    """
    Fiches de non-conformite Sylob (reception, transporteur) des articles donnes,
    lues dans la copie MyReport.

    Peu de fiches concernent l'import (4 depuis 2025 au 06/10/2026) : les
    non-conformites import se traitent par mail. La fiche Sylob reste la
    reference officielle quand elle existe.

    Junior Tip : meme SAVEPOINT que intitules_commande_sylob. Sans droit sur la
    copie MyReport, on renvoie une liste vide au lieu de casser l'endpoint.
    """
    codes = sorted({str(c).strip() for c in codes_article if c and str(c).strip()})
    if not codes:
        return []
    table = f'"{Config.MYREPORT_SCHEMA}"."{Config.MYREPORT_TABLE_NCR}"'
    sql = text(f"""
        SELECT f.fnc_code_fiche_non_conformite AS code_fiche,
               f.article_code_article AS code_article,
               f.database_name AS societe,
               f.type_fnc_code_type_non_conformite AS type_fiche,
               f.fnc_date_de_declaration::date AS date_declaration,
               f.fnc_etat_d_avancement AS etat,
               f.libelle_defaut_non_conformite AS defaut,
               f.fnc_description_constat AS constat,
               f.frn_raison_sociale AS fournisseur
        FROM {table} f
        WHERE f.article_code_article = ANY(:codes)
          AND f.type_fnc_code_type_non_conformite = ANY(:types)
        ORDER BY f.fnc_date_de_declaration DESC NULLS LAST
    """)
    try:
        with conn.begin_nested():
            return rows_to_dicts(conn.execute(
                sql, {"codes": codes, "types": list(TYPES_FICHE_NCR_ACHAT)}))
    except Exception as exc:
        logger.warning("[ATTENTION] Fiches NCR Sylob illisibles dans %s (%s)",
                       table, str(exc).splitlines()[0])
        return []


def rattacher_non_conformites(lignes: list[dict[str, Any]],
                              decisions: list[dict[str, Any]],
                              fiches: list[dict[str, Any]]) -> None:
    """
    Ajoute a chaque ligne de commande ses non-conformites ouvertes :
    - non_conformites : decisions mail du PO, pour cet article ou pour tout le PO ;
    - fiches_ncr : fiches Sylob de l'article declarees a partir de la date de
      commande (une fiche anterieure concerne une autre commande).
    """
    for ligne in lignes:
        po = normaliser_po(ligne.get("po_number"))
        art = str(ligne.get("code_article") or "").strip()
        ligne["non_conformites"] = [
            d for d in decisions
            if d["po"] == po and (d["code_article"] is None or d["code_article"] == art)
        ]
        debut = ligne.get("date_commande")
        ligne["fiches_ncr"] = [
            f for f in fiches
            if f["code_article"] == art
            and (debut is None or f["date_declaration"] is None or f["date_declaration"] >= debut)
        ]


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
            # Le classement reste calcule hors valeurs aberrantes (un retard de
            # 3 ans ecrase tout le graphe), mais on remonte leur nombre pour que
            # le front puisse les signaler au lieu de les cacher.
            r = conn.execute(text(f"""
                SELECT
                    e.fournisseur,
                    MAX(e.jours_retard) FILTER (WHERE e.jours_retard <= :seuil) AS retard_max_jours,
                    COUNT(*) FILTER (WHERE a.statut_retard = 'EN RETARD')       AS nb_articles_en_retard,
                    COUNT(*) FILTER (WHERE e.jours_retard > :seuil)             AS nb_retards_aberrants
                FROM {SCHEMA}.v_retard_expedition e
                LEFT JOIN {SCHEMA}.v_retard_article a
                    ON a.code_article = e.code_article AND a.fournisseur = e.fournisseur
                WHERE e.fournisseur IS NOT NULL
                GROUP BY e.fournisseur
                HAVING MAX(e.jours_retard) FILTER (WHERE e.jours_retard <= :seuil) IS NOT NULL
                ORDER BY retard_max_jours DESC
                LIMIT 5
            """), {"seuil": SEUIL_RETARD_ABERRANT_JOURS})
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
                        COALESCE(p.ean13, n.ean13, p.ean14_pcb, '') AS ean_edi,
                        {SQL_ETD_EFF}              AS date_etd,
                        c.eta, c.date_livraison, c.date_reception_sylob, c.date_commande,
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
                    LEFT JOIN {SCHEMA}.produit p ON p.code_article = c.code_article
                    LEFT JOIN {SCHEMA}.article_nomenclature n ON n.code_article = c.code_article
                ) q
                {where}
            """
            total = conn.execute(text(f"SELECT COUNT(*) {base}"), params).scalar()
            r = conn.execute(text(f"""
                SELECT * {base}
                ORDER BY po_number ASC, code_article ASC
                LIMIT :limit OFFSET :offset
            """), params)
            data = rows_to_dicts(r)
            intitules = intitules_commande_sylob(conn, [d["po_number"] for d in data])
            for d in data:
                d["intitule_commande"] = intitules.get(normaliser_po(d.get("po_number")))
            rattacher_non_conformites(
                data,
                non_conformites_mail(conn, [d["po_number"] for d in data]),
                fiches_ncr_sylob(conn, [d["code_article"] for d in data]))
            return {"data": data, "total": int(total or 0),
                    "limit": limit, "offset": offset}
        except Exception as e:
            raise internal_error(e)


class PaiementConteneur(BaseModel):
    """Saisie de la date de paiement pour un conteneur, eventuellement restreinte
    a un fournisseur."""
    # Omis = tout le conteneur, tous fournisseurs confondus (onglet Conteneurs).
    # Renseigne = un seul bloc fournisseur (onglet Previsionnel).
    fournisseur: Optional[str] = None
    # None = effacer la saisie et revenir a la date remontee par l'ETL.
    date_paiement: Optional[date] = None


@app.put("/api/paiement/conteneur/{n_conteneur}")
def set_paiement_conteneur(
    n_conteneur: str,
    payload: PaiementConteneur,
    auteur: str = Depends(require_utilisateur),
):
    """
    Renseigne la date de paiement de toutes les lignes d'un conteneur pour un
    fournisseur donne.

    Marlene raisonne par conteneur : elle solde un BL entier aupres d'un
    fournisseur, pas ligne article par ligne article. La saisie se fait donc au
    grain conteneur x fournisseur, mais le STOCKAGE reste au grain ligne
    (po_number, code_article) dans achat.commande_annotation, comme l'ETD et le
    commentaire. On garde ainsi un seul modele d'annotation, et un paiement
    partiel reste corrigeable ligne a ligne plus tard.

    achat.commande n'est jamais modifiee ici : elle appartient a l'ETL
    (full-refresh). C'est achat.v_previsionnel qui arbitre, via
    COALESCE(saisie, valeur ETL).

    Envoyer date_paiement = null efface la saisie et redonne la main a l'ETL.

    Junior Tip : l'auteur est recu en parametre, pas via `dependencies=[...]`.
    Cette seconde forme execute bien le controle d'acces mais jette sa valeur
    de retour : jusqu'au 05/10, updated_by restait vide sur toute saisie.
    """
    engine = get_engine()
    params: dict[str, Any] = {"cont": n_conteneur}
    filtre_frs = ""
    if payload.fournisseur:
        filtre_frs = " AND fournisseur = :frs"
        params["frs"] = payload.fournisseur

    with engine.begin() as conn:
        try:
            lignes = conn.execute(text(f"""
                SELECT po_number, code_article FROM {SCHEMA}.commande
                WHERE n_conteneur = :cont
                  AND statut <> 'Annulée'
                  {filtre_frs}
            """), params).fetchall()

            if not lignes:
                cible = payload.fournisseur or "tous fournisseurs"
                raise HTTPException(
                    status_code=404,
                    detail=f"Aucune ligne active pour {cible} "
                           f"sur le conteneur {n_conteneur}.")

            conn.execute(text(f"""
                INSERT INTO {SCHEMA}.commande_annotation
                    (po_number, code_article, date_paiement, updated_by, updated_at)
                VALUES (:po, :art, :dt, :auteur, NOW())
                ON CONFLICT (po_number, code_article)
                DO UPDATE SET date_paiement = EXCLUDED.date_paiement,
                              updated_by    = EXCLUDED.updated_by,
                              updated_at    = NOW()
            """), [{"po": po, "art": art, "dt": payload.date_paiement, "auteur": auteur}
                   for po, art in lignes])

            logger.info("[SUCCES] Paiement %s sur %d ligne(s) du conteneur %s / %s par %s.",
                        payload.date_paiement or "efface", len(lignes),
                        n_conteneur, payload.fournisseur or "tous fournisseurs", auteur)
            return {"ok": True, "lignes_maj": len(lignes),
                    "n_conteneur": n_conteneur, "fournisseur": payload.fournisseur,
                    "date_paiement": payload.date_paiement}
        except HTTPException:
            raise
        except Exception as e:
            raise internal_error(e)


@app.put("/api/commandes/{po_number}/{code_article}")
def annotate_commande(
    po_number: str,
    code_article: str,
    payload: CommandeAnnotation,
    auteur: str = Depends(require_utilisateur),
):
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

    sets, params = [], {"po": po_number, "art": code_article, "auteur": auteur}
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
                INSERT INTO {SCHEMA}.commande_annotation
                    (po_number, code_article, {cols}, updated_by)
                VALUES (:po, :art, {vals}, :auteur)
                ON CONFLICT (po_number, code_article)
                DO UPDATE SET {updates}, updated_by = EXCLUDED.updated_by, updated_at = NOW()
            """), params)
            logger.info("[SUCCES] Annotation %s sur %s/%s par %s.", cols, po_number, code_article, auteur)
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
    """Historique complet des prix d'achat, fusionné depuis l'IMPORT et Sylob.

    C'est le besoin numéro 1 du service Achats : savoir en deux secondes combien
    on a payé la dernière fois avant de négocier avec le fournisseur.

    Refonte du 23/09/2026 après la démo du 22/09. Deux limites se cumulaient et
    se masquaient l'une l'autre. Un plafond de 3 commandes par article, et le
    fait que Sylob n'était consulté QUE si achat.commande ne renvoyait rien.
    Résultat : dès qu'un article existait dans le périmètre IMPORT, son
    historique s'arrêtait à juin 2024, alors que Sylob le connaît depuis 2013.
    C'est ce que Marlène a signalé en démo, et ce n'était pas un défaut
    d'affichage mais de requête.

    Les deux sources sont désormais fusionnées, sans plafond, dédoublonnées sur
    (code_article, po_number). Chaque ligne porte sa `provenance`, import ou
    sylob, car hors périmètre IMPORT la devise peut ne pas être le dollar.

    Le chemin d'appel réel du front est /api/fournisseurs/all/historique-prix
    avec un code_article : le segment "all" est alors ignoré, la recherche est
    volontairement globale, tous fournisseurs confondus (retour métier 07/07),
    pour permettre la comparaison de prix entre fournisseurs.
    """
    engine = get_engine()
    params: dict[str, Any] = {}

    # Perimetre d'articles a historiser. C'est le pivot de toute la fonction :
    # le rapprochement entre l'IMPORT et Sylob se fait par CODE ARTICLE et
    # jamais par fournisseur. Mesure du 23/09/2026 : 580 des 593 articles
    # tarifes de achat.commande existent aussi dans Sylob, alors qu'un seul nom
    # de fournisseur sur 29 concorde entre les deux ("HONGXING" cote IMPORT
    # contre "JIEYANG HONGXING STAINLESS STEEL PRODUCTS MANUFACTORY (HX)" cote
    # Sylob). Le code frn_codes de achat.fournisseur_ca ne comble pas l'ecart
    # non plus : il donne 00001217 pour HONGXING quand la vue Sylob donne
    # 00000922. Toute jointure par fournisseur est donc a proscrire tant que ce
    # pont n'a pas ete instruit.
    if code_article:
        # CAST(... AS text) et non :code_article::text : le double deux-points du
        # cast PostgreSQL entre en collision avec la syntaxe des parametres
        # nommes de SQLAlchemy, qui rend un "syntax error at or near :".
        cte_articles = "SELECT CAST(:code_article AS text) AS code_article"
        params["code_article"] = code_article
    elif fournisseur.lower() == "all":
        raise HTTPException(
            status_code=400,
            detail="Le fournisseur 'all' exige un code_article : préciser ?code_article=...",
        )
    else:
        # Vue fournisseur : on part de ses articles connus du perimetre IMPORT,
        # puis on remonte tout leur historique, y compris chez d'autres
        # fournisseurs. Arbitre avec Antho le 23/09, et conforme au retour
        # metier du 07/07 qui veut la comparaison de prix entre fournisseurs.
        cte_articles = (f"SELECT DISTINCT code_article FROM {SCHEMA}.commande "
                        "WHERE fournisseur = :fournisseur AND code_article IS NOT NULL")
        params["fournisseur"] = fournisseur

    with engine.connect() as conn:
        try:
            # Fusion des deux sources, plus aucun plafond de 3 commandes par
            # article (demande de Marlene en demo le 22/09 : "remonter toutes
            # les dernieres commandes"). achat.commande couvre juin 2024 a
            # aujourd'hui, achat.historique_prix_sylob remonte a 2013.
            #
            # Dedoublonnage sur (code_article, po_number), avec priorite a la
            # ligne IMPORT : c'est celle que le service Achats a saisie et
            # rapprochee, Sylob n'en est que le reflet comptable.
            r = conn.execute(text(f"""
                WITH articles AS ({cte_articles}),
                import AS (
                    SELECT c.po_number, c.code_article, c.designation, c.fournisseur,
                           c.prix_unitaire AS prix, c.quantite::numeric AS quantite,
                           c.date_commande AS date_mail,
                           NULL::text AS societe, FALSE AS devise_etrangere,
                           NULL::numeric AS prix_unitaire_eur, NULL::text AS unite,
                           'import'::text AS provenance
                    FROM {SCHEMA}.commande c
                    JOIN articles a ON a.code_article = c.code_article
                    WHERE c.prix_unitaire IS NOT NULL
                ),
                sylob AS (
                    SELECT h.po_number, h.code_article, h.designation, h.fournisseur,
                           h.prix_unitaire AS prix, h.quantite::numeric AS quantite,
                           h.date_commande AS date_mail,
                           h.societe, h.devise_etrangere, h.prix_unitaire_eur, h.unite,
                           'sylob'::text AS provenance
                    FROM {SCHEMA}.historique_prix_sylob h
                    JOIN articles a ON a.code_article = h.code_article
                ),
                fusion AS (
                    SELECT * FROM import
                    UNION ALL
                    SELECT s.* FROM sylob s
                    WHERE NOT EXISTS (
                        SELECT 1 FROM import i
                        WHERE i.code_article = s.code_article
                          AND i.po_number IS NOT DISTINCT FROM s.po_number
                    )
                )
                SELECT f.po_number, f.code_article,
                       COALESCE(p.designation_fr, f.designation) AS designation_fr,
                       p.designation_en,
                       COALESCE(p.designation_fr, p.designation_en, f.designation) AS designation,
                       p.ean13,
                       f.fournisseur, f.prix, f.quantite, f.date_mail,
                       f.societe, f.devise_etrangere, f.prix_unitaire_eur, f.unite,
                       f.provenance
                FROM fusion f
                LEFT JOIN {SCHEMA}.produit p ON p.code_article = f.code_article
                ORDER BY f.code_article, f.date_mail DESC NULLS LAST
            """), params)
            lignes = rows_to_dicts(r)
            logger.info("[INFO] Historique prix (%s) : %d ligne(s) fusionnees",
                        code_article or fournisseur, len(lignes))
            return {"source": "fusion", "data": lignes}
        except Exception as e:
            raise internal_error(e)


@app.get("/api/produit/{code_article}")
def get_produit(code_article: str):
    """Fiche article a 360 degres -- decision metier 21/07 (plan_action.md,
    point 6) : l'onglet Article doit fusionner achat.produit (referentiel
    enrichi Matrice + Sylob V25, enrich_dimensions.py), achat.article_nomenclature
    (+ composants si lot multiple, Matrice TB Import), le statut artwork
    (achat.v_artwork, gsheet Clarisse) et l'historique qualite -- pas juste
    l'historique prix comme avant. Tout est deja en base, jamais expose par
    aucun endpoint jusqu'ici (verifie le 22/07)."""
    engine = get_engine()
    with engine.connect() as conn:
        try:
            produit = rows_to_dicts(conn.execute(
                text(f"SELECT * FROM {SCHEMA}.produit WHERE code_article = :c"),
                {"c": code_article}))
            nomenclature = rows_to_dicts(conn.execute(
                text(f"SELECT * FROM {SCHEMA}.article_nomenclature WHERE code_article = :c"),
                {"c": code_article}))
            composants = rows_to_dicts(conn.execute(text(f"""
                SELECT * FROM {SCHEMA}.article_nomenclature_composant
                WHERE code_article = :c ORDER BY position
            """), {"c": code_article}))
            artwork = rows_to_dicts(conn.execute(
                text(f"SELECT * FROM {SCHEMA}.v_artwork WHERE code_article = :c"),
                {"c": code_article}))
            cycle_vie = rows_to_dicts(conn.execute(
                text(f"SELECT * FROM {SCHEMA}.article_cycle_vie WHERE code_article = :c"),
                {"c": code_article}))
            qualite = rows_to_dicts(conn.execute(text(f"""
                SELECT po_number, fournisseur, matiere, semi_production, echantillon_conformite,
                       production_bat, date_inspection, resultat_inspection, ref_rapport, reception, ncr
                FROM {SCHEMA}.qualite WHERE code_article = :c
                ORDER BY date_inspection DESC NULLS LAST
            """), {"c": code_article}))
            # LIKE ancré : voir /api/qualite/rapports, un motif '%code%' ramenait
            # les rapports d'autres articles dont le nom de fichier contenait la
            # séquence de chiffres.
            params_doc = {"c": code_article, "c_prefix": f"{code_article}%",
                          "limit": RAPPORTS_LIMIT_DEFAUT}
            qualite_docs = rows_to_dicts(conn.execute(text(f"""
                SELECT DISTINCT d.* FROM {SCHEMA}.qualite_doc d
                LEFT JOIN {SCHEMA}.commande c ON LTRIM(c.po_number, '0') = LTRIM(d.po_number, '0')
                WHERE c.code_article = :c OR d.fichier LIKE :c_prefix
                ORDER BY d.charge_le DESC LIMIT :limit
            """), params_doc))
            qualite_analyses = rows_to_dicts(conn.execute(text(f"""
                SELECT DISTINCT a.* FROM {SCHEMA}.qualite_analyse a
                LEFT JOIN {SCHEMA}.commande c ON LTRIM(c.po_number, '0') = LTRIM(a.po_number, '0')
                WHERE c.code_article = :c OR a.sample_name LIKE :c_prefix
                ORDER BY a.charge_le DESC LIMIT :limit
            """), params_doc))

            fiches_ncr = fiches_ncr_sylob(conn, [code_article])

            if not (produit or nomenclature or artwork or cycle_vie or qualite or qualite_docs or qualite_analyses or fiches_ncr):
                return {"data": None, "warning": "Article introuvable (aucune donnee produit/nomenclature/artwork/qualite)."}

            return {"data": {
                "produit": produit[0] if produit else None,
                "nomenclature": nomenclature[0] if nomenclature else None,
                "composants": composants,
                "artwork": artwork[0] if artwork else None,
                "cycle_vie": cycle_vie[0] if cycle_vie else None,
                "qualite": qualite,
                "qualite_docs": qualite_docs,
                "qualite_analyses": qualite_analyses,
                "fiches_ncr": fiches_ncr,
            }}
        except Exception as e:
            raise internal_error(e)


@app.get("/api/qualite/rapports")
def get_qualite_rapports(
    code_article: Optional[str] = Query(None),
    po_number: Optional[str] = Query(None),
    limit: int = Query(RAPPORTS_LIMIT_DEFAUT, ge=1, le=RAPPORTS_LIMIT_MAX),
):
    """Rapports d'inspection et d'analyse qualite rattachés à un code_article ou un po_number.

    Au moins un des deux filtres est obligatoire : sans filtre, la requête
    balayait les deux tables entières jointes à achat.commande, sans LIMIT.
    """
    if not code_article and not po_number:
        raise HTTPException(
            status_code=400,
            detail="Préciser au moins un filtre : code_article ou po_number.",
        )

    engine = get_engine()
    with engine.connect() as conn:
        try:
            filters_doc = []
            filters_ana = []
            params: dict[str, Any] = {"limit": limit}
            if code_article:
                # LIKE ancré en début de chaîne : un '%code%' non ancré ramenait
                # les rapports d'articles sans rapport dès que le code était
                # court, et interdisait tout usage d'index (seq scan).
                filters_doc.append("(c.code_article = :code_article OR d.fichier LIKE :code_prefix)")
                filters_ana.append("(c.code_article = :code_article OR a.sample_name LIKE :code_prefix)")
                params["code_article"] = code_article
                params["code_prefix"] = f"{code_article}%"
            if po_number:
                # PO compares sans zeros de tete : 6 chiffres dans l'IMPORT,
                # 8 sur le Drive. La comparaison stricte ne trouvait rien.
                filters_doc.append("LTRIM(d.po_number, '0') = LTRIM(:po_number, '0')")
                filters_ana.append("LTRIM(a.po_number, '0') = LTRIM(:po_number, '0')")
                params["po_number"] = po_number

            where_doc = "WHERE " + " AND ".join(filters_doc)
            where_ana = "WHERE " + " AND ".join(filters_ana)

            docs = rows_to_dicts(conn.execute(text(f"""
                SELECT DISTINCT d.* FROM {SCHEMA}.qualite_doc d
                LEFT JOIN {SCHEMA}.commande c ON LTRIM(c.po_number, '0') = LTRIM(d.po_number, '0')
                {where_doc} ORDER BY d.charge_le DESC LIMIT :limit
            """), params))
            analyses = rows_to_dicts(conn.execute(text(f"""
                SELECT DISTINCT a.* FROM {SCHEMA}.qualite_analyse a
                LEFT JOIN {SCHEMA}.commande c ON LTRIM(c.po_number, '0') = LTRIM(a.po_number, '0')
                {where_ana} ORDER BY a.charge_le DESC LIMIT :limit
            """), params))
            return {"docs": docs, "analyses": analyses}
        except Exception as e:
            raise internal_error(e)


class FicheExportRequest(BaseModel):
    data: dict[str, Any] = Field(default_factory=dict)
    items: list[dict[str, Any]] = Field(default_factory=list)
    # References equivalentes (coloris, menagere/vrac), plan_action.md §3.8.
    # Optionnel : un client qui ne l'envoie pas garde l'export d'avant.
    equivalents: list[dict[str, Any]] = Field(default_factory=list)


@app.post("/api/fiche-achat/export-excel")
def export_fiche_excel(req: FicheExportRequest):
    """Exporte la Fiche Achat actuelle au format Excel (.xlsx) conforme au modèle FOR-ACH-03-12."""
    try:
        from src.utils.export_fiche_excel import generate_fiche_excel_bytes
        excel_bytes = generate_fiche_excel_bytes(req.data, req.items, req.equivalents)
        supplier = req.data.get("supplier") or "TB"
        po = req.data.get("po_number") or req.data.get("code_article") or "EXPORT"
        filename = f"Fiche_Achat_{supplier}_{po}.xlsx".replace(" ", "_")
        return Response(
            content=excel_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )
    except Exception as e:
        raise internal_error(e)


@app.get("/api/search/article")
def search_article(q: str = "", limit: int = 10):
    """Recherche article transverse. Source SYLOB (public.articles3),
    achat.produit et achat.commande en complément. Accepte désignation, EAN/EDI
    et code article. Retourne des candidats distincts."""
    q = (q or "").strip()
    if not q:
        return {"data": [], "count": 0}
    lim = max(1, min(int(limit or 10), 50))
    like = "%" + q + "%"
    engine = get_engine()
    results = {}

    with engine.connect() as conn:
        # 1. Tentative SYLOB public.articles3
        try:
            conds = ["code_article = :q"]
            if len(q) >= 2:
                conds.append("(designation ILIKE :like OR libelle ILIKE :like)")
            if q.isdigit() and len(q) >= 4:
                conds.append("(code_gtin_13 ILIKE :like OR identifiant_edi ILIKE :like OR identifiant_edi2 ILIKE :like "
                             "OR sup_ean14_pcb ILIKE :like OR sup_ean14_spcb ILIKE :like OR sup_ean14_palette ILIKE :like)")
            where = " OR ".join(conds)
            sql = text(
                "SELECT code_article, "
                "COALESCE(MAX(designation) FILTER (WHERE libelle_langue ILIKE 'fran%'), MAX(designation)) AS designation, "
                "MAX(code_gtin_13) AS ean13, MAX(identifiant_edi) AS edi "
                "FROM public.articles3 WHERE " + where + " "
                "GROUP BY code_article ORDER BY designation LIMIT :lim"
            )
            with conn.begin_nested():
                rows = rows_to_dicts(conn.execute(sql, {"q": q, "like": like, "lim": lim}))
            for r in rows:
                if r.get("code_article"):
                    results[r["code_article"]] = r
        except Exception as e:
            # Verifie le 28/07 puis le 05/10 : le role applicatif n'a PAS le droit
            # SELECT sur public.articles3, perdu a chaque recreation de la table
            # par l'ETL MyReport. Logue en WARNING pour que le manque se voie.
            logger.warning("[ATTENTION] public.articles3 inaccessible, essai du pont "
                           "achat.fn_myreport_recherche_article (%s)", str(e).splitlines()[0])
            # 1 bis. Pont SECURITY DEFINER (sql/20261005_pont_lecture_myreport_fuseau.sql),
            # tant que le default privilege du proprietaire MyReport n'est pas pose.
            try:
                with conn.begin_nested():
                    rows = rows_to_dicts(conn.execute(
                        text("SELECT * FROM achat.fn_myreport_recherche_article(:q, :lim)"),
                        {"q": q, "lim": lim}))
                for r in rows:
                    if r.get("code_article"):
                        results[r["code_article"]] = r
            except Exception as e_pont:
                logger.warning("[ATTENTION] Pont MyReport indisponible, repli sur achat.produit (%s)",
                               str(e_pont).splitlines()[0])

        # 2. Complément achat.produit
        try:
            sql_p = text(f"""
                SELECT code_article, COALESCE(designation_fr, designation_en) AS designation, ean13
                FROM {SCHEMA}.produit
                WHERE code_article ILIKE :like OR designation_fr ILIKE :like OR designation_en ILIKE :like OR ean13 ILIKE :like
                LIMIT :lim
            """)
            rows_p = rows_to_dicts(conn.execute(sql_p, {"q": q, "like": like, "lim": lim}))
            for r in rows_p:
                if r.get("code_article") and r["code_article"] not in results:
                    results[r["code_article"]] = r
        except Exception as e:
            conn.rollback()
            logger.warning("[ATTENTION] Erreur search achat.produit : %s", e)

        # 3. Complément achat.commande
        try:
            sql_c = text(f"""
                SELECT DISTINCT code_article, designation
                FROM {SCHEMA}.commande
                WHERE code_article ILIKE :like OR designation ILIKE :like
                LIMIT :lim
            """)
            rows_c = rows_to_dicts(conn.execute(sql_c, {"like": like, "lim": lim}))
            for r in rows_c:
                if r.get("code_article") and r["code_article"] not in results:
                    results[r["code_article"]] = r
        except Exception as e:
            conn.rollback()
            logger.warning("[ATTENTION] Erreur search achat.commande : %s", e)

    out = list(results.values())[:lim]
    return {"data": out, "count": len(out)}

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
                    MAX(COALESCE(ot.etd_reel, c.etd_reel, c.etd_confirme)) AS etd,
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

            # B/L en attente ou bloques + paiement, groupes par CONTENEUR puis
            # FOURNISSEUR (retours metier : "groupes par conteneur puis fournisseur"
            # ET "vue deja-paye par fournisseur ET conteneur/BL" -- une seule vue
            # groupee sert les 2 besoins, pas 2 requetes redondantes). "En attente" =
            # pas encore livre OU pas encore paye ; "bloque" = en retard ET pas
            # encore parti (meme definition que la carte Actions prioritaires).
            #
            # Correction 28/07 : le filtre excluait tout ce qui etait 'Livree', donc
            # une marchandise recue mais NON PAYEE disparaissait du tableau alors
            # que l'histogramme de cash au-dessus l'affichait toujours, et que la
            # carte Actions prioritaires du dashboard la citait nommement. Cas
            # rencontre : CMAU8355260, PO 165368 GUANGWEI, livre le 08/06 et
            # 103 059 $US encore dus. Le trou s'est elargi le jour ou le
            # rapprochement des receptions Sylob a bascule 47 PO de plus en
            # 'Livree'. On garde donc une ligne des qu'elle n'est pas livree OU
            # qu'il reste a payer.
            #
            # Provenance (retour Marlene 29/07) : les montants de ce tableau
            # viennent EXCLUSIVEMENT de achat.commande (IMPORT 2026.xlsx +
            # Sylob). Le maritime et Gmail n'alimentent que le BL, l'ETD/ETA et
            # le n° de facture -- aucun montant n'est extrait des pieces
            # jointes a ce jour. On expose donc n_bl ET n_facture pour que
            # l'interface puisse distinguer un montant corrobore par une liasse
            # documentaire d'un montant qui ne repose que sur le fichier IMPORT
            # (que le metier doit justement cesser d'utiliser).
            #
            # BL (retour Marlene 29/07, "les numeros de BL ne remontent plus") :
            # ot_transport.n_bl ne porte que le BL PRINCIPAL, et il est vide sur
            # tous les conteneurs venus du fichier serveur du transitaire, qui
            # est une copie reduite a 14 colonnes SANS colonne BL. La liste
            # complete vit dans achat.ot_transport_bl. On prend donc le relais
            # sur cette table quand ot_transport est muette.
            # ATTENTION : ot_transport_bl est au grain (conteneur, BL), un
            # conteneur en porte plusieurs. La joindre en LEFT JOIN
            # multiplierait les lignes de commande et gonflerait COUNT(*) comme
            # SUM(valeur). D'ou la sous-requete scalaire, qui ne peut pas
            # dupliquer de ligne.
            bl_bloques = rows_to_dicts(conn.execute(text(f"""
                SELECT
                    c.n_conteneur,
                    -- BL du fournisseur, par ordre de fiabilite (BUG-001, 25/09) :
                    -- 1. l'IMPORT, saisi par Marlene au grain du fournisseur ;
                    -- 2. la liste du suivi transitaire ;
                    -- 3. ot_transport.n_bl, seulement s'il a la forme d'un BL.
                    -- Le lecteur de PJ Gmail y range des n° de PO ou des mots
                    -- ("becomes", "GUANGWEI") : 44 conteneurs ouverts sur 100
                    -- affichaient un BL faux ou vide alors que l'IMPORT l'avait.
                    COALESCE(
                        MAX(NULLIF(NULLIF(TRIM(c.n_bl), ''), '/')),
                        (SELECT MIN(b.n_bl) FROM {SCHEMA}.ot_transport_bl b
                          WHERE b.n_conteneur = c.n_conteneur),
                        MAX(ot.n_bl) FILTER (WHERE ot.n_bl ~ '^[A-Z]{4,5}[0-9]{7,8}$')
                    )                                         AS n_bl,
                    (SELECT COUNT(*) FROM {SCHEMA}.ot_transport_bl b
                      WHERE b.n_conteneur = c.n_conteneur)     AS nb_bl,
                    MAX(ot.n_facture)                         AS n_facture,
                    c.fournisseur,
                    COUNT(DISTINCT c.po_number)                AS nb_po,
                    COUNT(*)                                   AS nb_articles,
                    ROUND(SUM(CASE WHEN c.code_article IS NULL THEN COALESCE(c.total_prix, 0)
                                   ELSE COALESCE(c.prix_unitaire * c.quantite, 0) END), 2) AS valeur,
                    MAX(COALESCE(ot.etd_reel, c.etd_reel, c.etd_confirme)) AS etd,
                    MAX(ot.eta)                                AS eta,
                    COUNT(*) FILTER (WHERE v.est_en_retard AND NOT v.est_parti) AS nb_bloques,
                    BOOL_OR(v.est_en_retard AND NOT v.est_parti)               AS est_bloque,
                    COUNT(*) FILTER (WHERE v.est_a_payer_en_retard)                       AS nb_a_payer_retard,
                    COUNT(*) FILTER (WHERE v.est_a_payer AND NOT v.est_a_payer_en_retard) AS nb_a_payer,
                    COUNT(*) FILTER (WHERE NOT v.est_a_payer)                             AS nb_paye,
                    ROUND(SUM(CASE WHEN v.est_a_payer THEN v.montant ELSE 0 END), 2)      AS valeur_a_payer,
                    -- Date de paiement du bloc, pour pre-remplir la saisie inline.
                    -- NULL si le bloc n'est pas integralement solde.
                    MAX(v.date_paiement) FILTER (WHERE NOT v.est_a_payer)  AS date_paiement,
                    BOOL_OR(v.paiement_saisi_manuellement)                 AS paiement_saisi
                FROM {SCHEMA}.commande c
                LEFT JOIN {SCHEMA}.ot_transport ot ON ot.n_conteneur = c.n_conteneur
                LEFT JOIN {SCHEMA}.v_previsionnel v ON v.id = c.id
                -- " /" est la saisie IMPORT d'une ligne sans conteneur : elle
                -- formait un faux conteneur "/" dans la liste.
                WHERE NULLIF(NULLIF(TRIM(c.n_conteneur), ''), '/') IS NOT NULL
                  AND c.statut <> 'Annulée'
                GROUP BY c.n_conteneur, c.fournisseur
                -- Une ligne "Payée" sans reste du est soldee, comme une "Livrée".
                HAVING BOOL_OR(c.statut NOT IN ('Livrée', 'Payée') OR v.est_a_payer)
                ORDER BY c.n_conteneur, nb_bloques DESC
            """)))

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
                            WHEN (COALESCE(ot.etd_reel, c.etd_reel, c.etd_confirme) + 15) <  CURRENT_DATE      THEN '1. En retard'
                            WHEN (COALESCE(ot.etd_reel, c.etd_reel, c.etd_confirme) + 15) <= CURRENT_DATE + 30 THEN '2. <= 30 j'
                            WHEN (COALESCE(ot.etd_reel, c.etd_reel, c.etd_confirme) + 15) <= CURRENT_DATE + 60 THEN '3. 31-60 j'
                            WHEN (COALESCE(ot.etd_reel, c.etd_reel, c.etd_confirme) + 15) <= CURRENT_DATE + 90 THEN '4. 61-90 j'
                            ELSE '5. > 90 j'
                        END AS tranche
                    FROM {SCHEMA}.commande c
                    LEFT JOIN {SCHEMA}.ot_transport ot ON ot.n_conteneur = c.n_conteneur
                    WHERE c.statut <> 'Annulée' AND c.date_paiement IS NULL
                      AND COALESCE(ot.etd_reel, c.etd_reel, c.etd_confirme) IS NOT NULL
                ) t
                GROUP BY tranche
                ORDER BY tranche
            """)))

            # Meme echeancier, ventile par MOIS d'echeance x CONTENEUR (retour metier
            # 23/07 : "decoupe les barres histogramme par conteneur, pour se rendre
            # compte de la valeur par conteneur par mois") -- alimente un bar chart
            # empile (1 barre par mois, 1 segment par conteneur).
            cash_par_mois_conteneur = rows_to_dicts(conn.execute(text(f"""
                SELECT
                    TO_CHAR((COALESCE(ot.etd_reel, c.etd_reel, c.etd_confirme) + 15), 'YYYY-MM') AS mois,
                    COALESCE(NULLIF(NULLIF(TRIM(c.n_conteneur), ''), '/'), 'Sans conteneur') AS n_conteneur,
                    ROUND(SUM(CASE WHEN c.code_article IS NULL THEN COALESCE(c.total_prix, 0)
                                   ELSE COALESCE(c.prix_unitaire * c.quantite, 0) END), 2) AS valeur_totale,
                    ROUND(SUM(CASE WHEN c.date_paiement IS NULL THEN
                                   (CASE WHEN c.code_article IS NULL THEN COALESCE(c.total_prix, 0)
                                         ELSE COALESCE(c.prix_unitaire * c.quantite, 0) END)
                                   ELSE 0 END), 2) AS valeur_a_payer
                FROM {SCHEMA}.commande c
                LEFT JOIN {SCHEMA}.ot_transport ot ON ot.n_conteneur = c.n_conteneur
                WHERE c.statut <> 'Annulée'
                  AND COALESCE(ot.etd_reel, c.etd_reel, c.etd_confirme) IS NOT NULL
                GROUP BY 1, 2
                ORDER BY 1, 2
            """)))

            return {
                "planning_mensuel": planning,
                "par_conteneur": par_conteneur,
                "bl_par_conteneur_fournisseur": bl_bloques,
                "cash_echeances": cash,
                "cash_par_mois_conteneur": cash_par_mois_conteneur,
                "donnees_maj": _derniere_maj_commande(),
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
            # Axe PAIEMENT par conteneur (retour metier : "vue deja paye par
            # conteneur/BL") -- reutilise v_previsionnel.est_a_payer(_en_retard),
            # deja calcule ligne a ligne, agrege ici au grain conteneur.
            agg = f"""
                SELECT c.n_conteneur,
                       COUNT(DISTINCT c.po_number) AS nb_po,
                       -- Numeros de PO du conteneur (BUG-003) : retrouver la
                       -- commande a partir du BL ou du conteneur sans quitter
                       -- l'onglet.
                       string_agg(DISTINCT c.po_number::text, ' · '
                                  ORDER BY c.po_number::text)  AS po_list,
                       COUNT(*)                    AS nb_articles,
                       ROUND(SUM(CASE WHEN c.code_article IS NULL THEN COALESCE(c.total_prix, 0)
                                      ELSE COALESCE(c.prix_unitaire * c.quantite, 0) END), 2) AS valeur,
                       COUNT(*) FILTER (WHERE v.est_a_payer_en_retard)          AS nb_a_payer_retard,
                       COUNT(*) FILTER (WHERE v.est_a_payer AND NOT v.est_a_payer_en_retard) AS nb_a_payer,
                       COUNT(*) FILTER (WHERE NOT v.est_a_payer)               AS nb_paye,
                       -- Date de paiement du conteneur, pour pre-remplir la
                       -- saisie inline. NULL si le conteneur n'est pas
                       -- integralement solde.
                       MAX(v.date_paiement) FILTER (WHERE NOT v.est_a_payer)    AS date_paiement,
                       BOOL_OR(v.paiement_saisi_manuellement)                   AS paiement_saisi
                FROM {SCHEMA}.commande c
                LEFT JOIN {SCHEMA}.v_previsionnel v ON v.id = c.id
                WHERE c.statut <> 'Annulée' AND c.n_conteneur IS NOT NULL AND c.n_conteneur <> ''
                GROUP BY c.n_conteneur
            """
            # Un conteneur groupe plusieurs fournisseurs, chacun editant son BL :
            # on agrege la table fille plutot que de n'exposer que le principal.
            liste = rows_to_dicts(conn.execute(text(f"""
                SELECT ot.n_conteneur,
                       COALESCE(
                           (SELECT string_agg(b.n_bl, ' · ' ORDER BY b.n_bl)
                            FROM {SCHEMA}.ot_transport_bl b
                            WHERE b.n_conteneur = ot.n_conteneur),
                           -- Repli sur l'IMPORT, puis sur ot.n_bl s'il a la
                           -- forme d'un BL (voir bl_bloques, BUG-001).
                           (SELECT string_agg(DISTINCT TRIM(c.n_bl), ' · ')
                            FROM {SCHEMA}.commande c
                            WHERE c.n_conteneur = ot.n_conteneur
                              AND NULLIF(NULLIF(TRIM(c.n_bl), ''), '/') IS NOT NULL),
                           CASE WHEN ot.n_bl ~ '^[A-Z]{4,5}[0-9]{7,8}$' THEN ot.n_bl END
                       ) AS n_bl,
                       COALESCE(
                           NULLIF((SELECT count(*) FROM {SCHEMA}.ot_transport_bl b
                                   WHERE b.n_conteneur = ot.n_conteneur), 0),
                           NULLIF((SELECT count(DISTINCT TRIM(c.n_bl)) FROM {SCHEMA}.commande c
                                   WHERE c.n_conteneur = ot.n_conteneur
                                     AND NULLIF(NULLIF(TRIM(c.n_bl), ''), '/') IS NOT NULL), 0),
                           CASE WHEN ot.n_bl ~ '^[A-Z]{4,5}[0-9]{7,8}$' THEN 1 ELSE 0 END
                       ) AS nb_bl,
                       ot.transport AS navire, ot.transitaire,
                       ot.lieu_livraison AS destinataire,
                       ot.etd_reel AS etd, ot.eta, ot.date_livraison,
                       COALESCE(a.nb_po, 0) AS nb_po, a.po_list,
                       COALESCE(a.nb_articles, 0) AS nb_articles,
                       COALESCE(a.valeur, 0) AS valeur,
                       COALESCE(a.nb_a_payer_retard, 0) AS nb_a_payer_retard,
                       COALESCE(a.nb_a_payer, 0)        AS nb_a_payer,
                       COALESCE(a.nb_paye, 0)           AS nb_paye,
                       a.date_paiement,
                       COALESCE(a.paiement_saisi, FALSE) AS paiement_saisi,
                       COALESCE(s.nb_changements_eta, 0)       AS nb_changements_eta,
                       COALESCE(s.nb_changements_livraison, 0) AS nb_changements_livraison,
                       s.couleur_eta, s.couleur_livraison
                FROM {SCHEMA}.ot_transport ot
                LEFT JOIN ({agg}) a ON a.n_conteneur = ot.n_conteneur
                LEFT JOIN {SCHEMA}.v_ot_transport_suivi s ON s.n_conteneur = ot.n_conteneur
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
        # Empreinte du code REELLEMENT servi, pas de celui qu'on croit avoir
        # deploye. C'est ce que le pipeline compare au commit qu'il vient de
        # publier : sans cette comparaison, un controle de sante valide
        # l'ancienne version quand le conteneur n'a pas ete recycle.
        "commit": Config.COMMIT_DEPLOYE,
        # Deux facons d'autoriser l'ecriture, et le mode heberge n'utilise PAS
        # de cle : la plateforme Entra injecte l'identite de l'appelant, que
        # require_utilisateur accepte telle quelle. Ne regarder que l'API_KEY
        # faisait donc annoncer "ecriture desactivee" par une API ou l'ecriture
        # marche, ce qui envoie chercher une panne qui n'existe pas.
        "write_enabled": Config.AUTH_MODE == "entra" or bool(Config.API_KEY),
        "donnees_maj": _derniere_maj_commande() if db_ok else None,
        # Le frontend en deduit s'il doit demander une cle avant d'ecrire. En
        # mode entra, l'identite vient de la plateforme et la cle est ignoree.
        "auth_mode": Config.AUTH_MODE,
    }


def _derniere_maj_commande() -> Optional[str]:
    """Horodatage du dernier chargement de achat.commande, ou None si illisible.

    achat.commande est rechargee par l'ETL du poste de Marlene. Du 28/07 au
    22/09, elle ne l'a pas ete sans que rien ne le signale : des conteneurs
    payes s'affichaient "A payer (retard)" (BUG-002). L'interface affiche un
    bandeau quand cette date vieillit. Une erreur ne doit jamais faire echouer
    la sonde, dont depend le controle de deploiement.
    """
    try:
        with get_engine().connect() as conn:
            maj = conn.execute(text(f"SELECT MAX(updated_at) FROM {SCHEMA}.commande")).scalar()
        return maj.isoformat() if maj else None
    except Exception:  # noqa: BLE001
        logger.warning("[ATTENTION] Fraicheur de achat.commande illisible.", exc_info=True)
        return None


# Statuts par stade affiches dans l'onglet Qualite (BUG-007, lot 1). L'IMPORT
# ne connait que Conforme / Non recu / Non conforme ; le metier parle de
# "en cours", "conforme", "FAIL". La decision recue par mail (achat.qualite_decision)
# ne remplace la valeur de l'IMPORT que lorsque celui-ci est vide.
STATUT_EN_COURS, STATUT_CONFORME, STATUT_FAIL, STATUT_RECU = "en_cours", "conforme", "fail", "recu"
STADES_QUALITE = {"MAT": "matiere", "SP": "semi_production", "BAT": "production_bat", "RECEP": "reception"}
STADE_DECISION = {"MAT": "MAT", "SP": "SP", "BAT": "BAT", "RECEP": "reception"}


def statut_stade(valeur: Optional[str], decision: Optional[str] = None) -> Optional[str]:
    """
    Normalise une valeur de checkpoint qualite de l'IMPORT en statut metier.

    Junior Tip : None veut dire "non applicable" (Aucune, "/", vide), ce qui
    n'est pas la meme chose qu'un stade en cours. L'ecran doit afficher un
    tiret, pas un faux statut, quand le stade ne concerne pas l'article.

    Args:
        valeur: texte brut de la colonne IMPORT (Conforme, Non recu, Analyse...).
        decision: derniere decision mail du stade (conforme / non_conforme).

    Returns:
        en_cours, conforme, fail, recu, ou None si non applicable.
    """
    v = (valeur or "").strip().lower()
    if not v or v in ("aucune", "/", "-"):
        if decision == "non_conforme":
            return STATUT_FAIL
        if decision == "conforme":
            return STATUT_CONFORME
        return None
    if "non conforme" in v or v == "fail":
        return STATUT_FAIL
    if v.startswith(("conforme", "valid", "ok", "oui")):
        return STATUT_CONFORME
    if "non re" in v or v == "analyse":
        return STATUT_EN_COURS
    if "receptionne" in v:
        return STATUT_RECU
    return None


@app.get("/api/qualite")
def get_qualite(
    fournisseur: Optional[str] = None,
    resultat: Optional[str] = None,
    code_article: Optional[str] = None,
):
    """
    Suivi qualite par produit : checkpoints MAT/SP/BAT/RECEP, inspection, NCR.

    Lot 1 de BUG-007 (cadrage docs/20261005_FUSEAU_Cadrage_OngletQualite_BUG007_v1.md) :
    - statuts normalises par stade (statut_mat, statut_sp, statut_bat, statut_recep) ;
    - derniere decision mail par stade, pour l'infobulle ;
    - lien Drive du rapport DEKRA retrouve par le nom de fichier, qui commence
      par la reference DEKRA ("4961649.00-6_Item#_..."), a defaut par PO et article.
      L'ancienne jointure sur qualite_doc.ref_rapport ne trouvait rien : ce champ
      porte une CA, pas une reference DEKRA ;
    - PO compares sans zeros de tete (6 chiffres dans l'IMPORT, 8 sur le Drive).
    """
    engine = get_engine()
    filters: list[str] = []
    params: dict[str, Any] = {}
    if fournisseur:
        filters.append("LOWER(q.fournisseur) LIKE :f")
        params["f"] = f"%{fournisseur.lower()}%"
    if resultat:
        filters.append("q.resultat_inspection = :r")
        params["r"] = resultat
    if code_article:
        filters.append("LOWER(q.code_article) LIKE :c")
        params["c"] = f"%{code_article.lower()}%"
    where = ("WHERE " + " AND ".join(filters)) if filters else ""
    with engine.connect() as conn:
        try:
            r = conn.execute(text(f"""
                SELECT q.*, doc.drive_url, an.conformite, dec.decisions, ana.analyses
                FROM {SCHEMA}.qualite q
                LEFT JOIN LATERAL (
                    SELECT d.drive_url FROM {SCHEMA}.qualite_doc d
                    WHERE d.drive_url IS NOT NULL AND d.type = 'inspection'
                      AND (
                            (q.ref_rapport IS NOT NULL AND d.fichier LIKE q.ref_rapport || '\\_%')
                         OR (LTRIM(d.po_number, '0') = LTRIM(q.po_number, '0')
                             AND d.fichier LIKE '%Item#\\_' || q.code_article || '\\_%')
                      )
                    ORDER BY (q.ref_rapport IS NOT NULL AND d.fichier LIKE q.ref_rapport || '\\_%') DESC,
                             d.charge_le DESC
                    LIMIT 1
                ) doc ON true
                LEFT JOIN LATERAL (
                    SELECT STRING_AGG(DISTINCT a.conformite, ', ') AS conformite
                    FROM {SCHEMA}.qualite_analyse a
                    WHERE a.ref_rapport = q.ref_rapport
                ) an ON true
                LEFT JOIN LATERAL (
                    SELECT jsonb_object_agg(x.stade, jsonb_build_object(
                               'decision', x.decision, 'date', x.date_info,
                               'motif', x.motif, 'acteur', x.acteur, 'nb', x.nb)) AS decisions
                    FROM (
                        SELECT DISTINCT ON (d.stade) d.stade, d.decision, d.date_info,
                               d.motif, d.acteur,
                               COUNT(*) OVER (PARTITION BY d.stade) AS nb
                        FROM {SCHEMA}.qualite_decision d
                        WHERE LTRIM(d.po_number, '0') = LTRIM(q.po_number, '0')
                          AND (d.code_article IS NULL OR d.code_article = q.code_article)
                          AND d.stade IN ('MAT', 'SP', 'BAT', 'reception')
                        ORDER BY d.stade, d.date_info DESC NULLS LAST, d.created_at DESC
                    ) x
                ) dec ON true
                LEFT JOIN LATERAL (
                    SELECT jsonb_object_agg(y.stade, y.drive_url) AS analyses
                    FROM (
                        SELECT DISTINCT ON (d.stade) d.stade, d.drive_url
                        FROM {SCHEMA}.qualite_doc d
                        WHERE d.type = 'analyse' AND d.drive_url IS NOT NULL AND d.stade IS NOT NULL
                          AND LTRIM(d.po_number, '0') = LTRIM(q.po_number, '0')
                        ORDER BY d.stade, d.charge_le DESC
                    ) y
                ) ana ON true
                {where}
                ORDER BY q.date_inspection DESC NULLS LAST
                LIMIT 1000
            """), params)
            rows = rows_to_dicts(r)
            for row in rows:
                decisions = row.get("decisions") or {}
                for stade, col in STADES_QUALITE.items():
                    dec = (decisions.get(STADE_DECISION[stade]) or {}).get("decision")
                    row[f"statut_{stade.lower()}"] = statut_stade(row.get(col), dec)
            return {"data": rows}
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
                       COALESCE(ROUND(SUM(montant) FILTER (WHERE est_en_retard), 2), 0) AS montant_retard,
                       -- Reconciliation avec la liste par conteneur (BUG-001) :
                       -- elle ne montre que les lignes rattachees a un conteneur,
                       -- soit ~10 % du reste du au 25/09. La difference est ici.
                       COALESCE(ROUND(SUM(montant) FILTER (WHERE est_a_payer), 2), 0) AS montant_a_payer,
                       COALESCE(ROUND(SUM(montant) FILTER (
                           WHERE est_a_payer AND NULLIF(NULLIF(TRIM(n_conteneur), ''), '/') IS NULL
                       ), 2), 0) AS montant_a_payer_sans_conteneur
                FROM (SELECT v.*, cc.n_conteneur
                      FROM {SCHEMA}.v_previsionnel v
                      JOIN {SCHEMA}.commande cc ON cc.id = v.id) p
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
