# -*- coding: utf-8 -*-
"""
=============================================================================
ETL ACHATS - CHARGEMENT POSTGRESQL (schema achat)
=============================================================================

Chargement des données transformées dans PostgreSQL (schéma achat) du DWH TB Groupe.

Stratégie : les opérations sont idempotentes et re-exécutables sans risque.
achat.produit utilise un UPSERT (INSERT ... ON CONFLICT DO UPDATE) pour préserver
les enrichissements Sylob ajoutés hors-pipeline. achat.commande utilise un
full-refresh (TRUNCATE + INSERT) car la granularité ligne-article rend l'UPSERT
complexe et le volume reste faible (< 10 000 lignes). achat.ot_transport
(suivi maritime, grain conteneur) utilise un UPSERT sur n_conteneur.
"""
import logging

import pandas as pd
from sqlalchemy import Engine, text

logger = logging.getLogger(__name__)

DDL_SCHEMA = "CREATE SCHEMA IF NOT EXISTS achat;"

DDL_PRODUIT = """
CREATE TABLE IF NOT EXISTS achat.produit (
    code_article         TEXT PRIMARY KEY,
    code_provisoire      TEXT,
    type_circuit         TEXT,
    ean13                TEXT,
    ean14_pcb            TEXT,
    ean14_spcb           TEXT,
    designation_fr       TEXT,
    designation_en       TEXT,
    marque               TEXT,
    gamme                TEXT,
    grande_famille       TEXT,
    fournisseur          TEXT,
    pays_fournisseur     TEXT,
    client_unique        TEXT,
    code_client          TEXT,
    prix_vente           NUMERIC,
    type_lot             TEXT,
    nomenclature         TEXT,
    matiere_lame         TEXT,
    chrome_pct           NUMERIC,
    traitement_thermique TEXT,
    matiere_manche       TEXT,
    finition             TEXT,
    marquage_libelle     TEXT,
    artwork              TEXT,
    poids_uvc_g          NUMERIC,
    longueur_mm          NUMERIC,
    epaisseur_mm         NUMERIC,
    pcb                  INTEGER,
    spcb                 INTEGER,
    inner_qty            INTEGER,
    master_qty           INTEGER,
    longueur_pcb_cm      NUMERIC,
    largeur_pcb_cm       NUMERIC,
    hauteur_pcb_cm       NUMERIC,
    poids_pcb_kg         NUMERIC,
    volume_m3            NUMERIC,
    date_creation        DATE,
    date_maj             DATE,
    updated_at           TIMESTAMPTZ DEFAULT now()
);
"""

DDL_COMMANDE = """
CREATE TABLE IF NOT EXISTS achat.commande (
    id               SERIAL PRIMARY KEY,
    po_number        TEXT,
    men_number       TEXT,
    n_lot            TEXT,
    intermediaire    TEXT,
    fournisseur      TEXT,
    code_article     TEXT,
    designation      TEXT,
    quantite         INTEGER,
    prix_unitaire    NUMERIC,
    total_prix       NUMERIC,
    frais_supp       NUMERIC,
    volume_m3_cmd    NUMERIC,
    statut           TEXT,
    date_statut      DATE,
    date_commande    DATE,
    date_paiement    DATE,
    etd_confirme     DATE,
    etd_reel         DATE,
    eta              DATE,
    date_livraison   DATE,
    lieu_livraison   TEXT,
    n_bl             TEXT,
    n_conteneur      TEXT,
    n_facture        TEXT,
    transitaire      TEXT,
    non_conformite   TEXT,
    retard_jours     INTEGER,
    colis_manquants  TEXT,
    updated_at       TIMESTAMPTZ DEFAULT now()
);
"""

# Contrainte UNIQUE sur la cle metier -- prerequis des upserts et de la jointure
# annotation. Idempotent via le bloc DO (ADD CONSTRAINT n'a pas de IF NOT EXISTS).
DDL_UQ_COMMANDE = """
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_commande_po_article'
    ) THEN
        ALTER TABLE achat.commande
        ADD CONSTRAINT uq_commande_po_article UNIQUE (po_number, code_article);
    END IF;
END $$;
"""

# Annotations metier (statut force, commentaire) -- table separee jointe par cle
# metier pour SURVIVRE au full-refresh de achat.commande. Decision 2026-06-10 :
# ne jamais stocker de saisie utilisateur dans une table rechargee par ETL.
DDL_COMMANDE_ANNOTATION = """
CREATE TABLE IF NOT EXISTS achat.commande_annotation (
    id             SERIAL PRIMARY KEY,
    po_number      TEXT NOT NULL,
    code_article   TEXT NOT NULL,
    statut_retard  TEXT,
    date_etd       DATE,
    commentaire    TEXT,
    updated_by     TEXT,
    updated_at     TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT uq_annotation_po_article UNIQUE (po_number, code_article)
);
"""

# Vue retard PAR ARTICLE. ETD effectif = reel sinon confirme. Les commandes
# livrees ou annulees ne sont jamais "en retard".
DDL_V_RETARD_ARTICLE = """
CREATE OR REPLACE VIEW achat.v_retard_article AS
SELECT
    c.code_article,
    c.fournisseur,
    MAX(COALESCE(c.etd_reel, c.etd_confirme))                    AS date_etd,
    CASE
        WHEN BOOL_AND(c.statut IN ('Livrée','Annulée'))
            THEN MAX(c.date_livraison) - MAX(COALESCE(c.etd_reel, c.etd_confirme))
        WHEN MAX(COALESCE(c.etd_reel, c.etd_confirme)) < CURRENT_DATE
            THEN CURRENT_DATE - MAX(COALESCE(c.etd_reel, c.etd_confirme))
        ELSE NULL
    END                                                          AS jours_retard,
    CASE
        WHEN BOOL_AND(c.statut IN ('Livrée', 'Annulée'))                THEN 'CLOTUREE'
        WHEN MAX(COALESCE(c.etd_reel, c.etd_confirme)) < CURRENT_DATE   THEN 'EN RETARD'
        WHEN MAX(COALESCE(c.etd_reel, c.etd_confirme)) IS NULL          THEN 'INCONNU'
        ELSE 'DANS LES DELAIS'
    END AS statut_retard
FROM achat.commande c
GROUP BY c.code_article, c.fournisseur;
"""

# Suivi artwork (plan P5) -- table EDITEE PAR LE METIER via l'ERP. L'ETL ne fait
# que l'alimenter en insert-only.
DDL_ARTWORK = """
CREATE TABLE IF NOT EXISTS achat.artwork (
    id              SERIAL PRIMARY KEY,
    po_number       TEXT NOT NULL,
    code_article    TEXT NOT NULL,
    designation     TEXT,
    statut_artwork  TEXT DEFAULT 'Aucun',
    responsable     TEXT,
    commentaire     TEXT,
    date_demande    DATE,
    updated_at      TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT uq_artwork_po_article UNIQUE (po_number, code_article)
);
"""

# Suivi maritime / transitaire (manque n7 carto BI) -- table ALIMENTEE PAR ETL.
# Grain = 1 ligne PAR CONTENEUR. Source cible = 2026 SUIVI MARITIME.xlsx (feuille
# CONTENEUR PLEIN) ; en attendant l'acces, bootstrap depuis les valeurs en cache
# de achat.commande (dedup par n_conteneur). Cle de jointure = N Conteneur.
# Acompte verse (source Sylob, 3 societes) -- joint par po_number. Les fournisseurs
# reclament parfois le total en oubliant l'acompte deja verse (besoin metier).
# Cle : commande_numero_de_la_commande (Sylob, 8 zero-padde) = po_number.
DDL_ACOMPTE = """
CREATE TABLE IF NOT EXISTS achat.acompte (
    po_number            TEXT PRIMARY KEY,
    societe              TEXT,
    montant_acompte      NUMERIC,
    pourcentage_acompte  NUMERIC,
    net_a_payer          NUMERIC,
    total_ht             NUMERIC,
    charge_le            TIMESTAMPTZ DEFAULT now()
);
"""

# CA fournisseur cumule (3 ans glissants) -- somme des achats Sylob par fournisseur,
# UNION 3 societes. Mapping nom (achat.commande, texte) <-> frn_code via le join PO.
# Montant en devise commande (USD pour imports). Besoin metier : poids du fournisseur.
DDL_FOURNISSEUR_CA = """
CREATE TABLE IF NOT EXISTS achat.fournisseur_ca (
    fournisseur   TEXT PRIMARY KEY,
    frn_codes     TEXT,
    ca_3ans       NUMERIC,
    nb_commandes  INTEGER,
    charge_le     TIMESTAMPTZ DEFAULT now()
);
"""

DDL_OT_TRANSPORT = """
CREATE TABLE IF NOT EXISTS achat.ot_transport (
    n_conteneur      TEXT PRIMARY KEY,
    etd_reel         DATE,
    eta              DATE,
    date_livraison   TIMESTAMP,
    transport        TEXT,
    transitaire      TEXT,
    n_bl             TEXT,
    n_facture        TEXT,
    lieu_livraison   TEXT,
    source_fichier   TEXT,
    charge_le        TIMESTAMP NOT NULL DEFAULT now()
);
"""

# Droits pour le compte applicatif du poste Marlene (platform_team) -- les tables
# appartiennent au compte Antho, sans GRANT explicite l'ERP affiche 0.
GRANTS_PLATFORM_TEAM = """
GRANT USAGE ON SCHEMA achat TO platform_team;
GRANT SELECT ON ALL TABLES IN SCHEMA achat TO platform_team;
GRANT SELECT, INSERT, UPDATE ON achat.commande_annotation TO platform_team;
GRANT SELECT, INSERT, UPDATE ON achat.artwork TO platform_team;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA achat TO platform_team;
ALTER DEFAULT PRIVILEGES IN SCHEMA achat GRANT SELECT ON TABLES TO platform_team;
"""


def create_tables_if_not_exist(engine: Engine) -> None:
    """
    Cree les tables du schema achat si elles n'existent pas (idempotent).

    Junior Tip : engine.begin() ouvre une transaction DDL. PostgreSQL autorise les
    DDL en transaction (contrairement a MySQL), ce qui garantit l'atomicite : soit
    toutes les tables sont creees, soit aucune.

    Args:
        engine: SQLAlchemy engine connecte a PostgreSQL (schema achat accessible).
    Returns:
        None
    """
    logger.info("[INFO] Creation des tables PostgreSQL (si necessaire)...")
    with engine.begin() as conn:
        conn.execute(text(DDL_PRODUIT))
        conn.execute(text(DDL_COMMANDE))
        conn.execute(text(DDL_COMMANDE_ANNOTATION))
        conn.execute(text(DDL_ARTWORK))
        conn.execute(text(DDL_OT_TRANSPORT))
        conn.execute(text(DDL_ACOMPTE))
        conn.execute(text(DDL_FOURNISSEUR_CA))
        conn.execute(text(DDL_QUALITE))
        conn.execute(text(DDL_V_RETARD_ARTICLE))
        conn.execute(text(DDL_V_QUALITE_FOURNISSEUR))
        conn.execute(text(DDL_V_PREVISIONNEL))
    try:
        with engine.begin() as conn:
            conn.execute(text(GRANTS_PLATFORM_TEAM))
        logger.info("[SUCCES] Grants platform_team appliques.")
    except Exception as exc:  # noqa: BLE001
        logger.warning("[ATTENTION] Grants platform_team non appliques : %s", exc)
    logger.info("[SUCCES] Tables pretes.")


def load_produit(df: pd.DataFrame, engine: Engine) -> int:
    """
    UPSERT de la table achat.produit via table temporaire intermediaire.

    Junior Tip : ON CONFLICT DO UPDATE garantit l'idempotence. EXCLUDED est un
    pseudo-alias PostgreSQL qui designe la ligne candidate ayant provoque le conflit.

    Args:
        df: DataFrame produit transforme (issu de transform_produit).
        engine: SQLAlchemy engine PostgreSQL.
    Returns:
        Nombre de lignes inserees ou mises a jour.
    """
    if df.empty:
        logger.warning("[ATTENTION] DataFrame produit vide -- rien a charger.")
        return 0

    logger.info("[INFO] Chargement produit : %d articles...", len(df))

    cols = [c for c in df.columns if c != "code_article"]
    set_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols)
    set_clause += ", updated_at = now()"

    tmp_table = "achat._tmp_produit"
    with engine.begin() as conn:
        df.to_sql("_tmp_produit", conn, schema="achat",
                  if_exists="replace", index=False, method="multi")
        conn.execute(text(f"""
            INSERT INTO achat.produit ({', '.join(['code_article'] + cols)})
            SELECT {', '.join(['code_article'] + cols)} FROM {tmp_table}
            ON CONFLICT (code_article) DO UPDATE SET {set_clause};
        """))
        conn.execute(text(f"DROP TABLE IF EXISTS {tmp_table};"))

    count = len(df)
    logger.info("[SUCCES] Produit charge : %d articles.", count)
    return count


def load_artwork(df: pd.DataFrame, engine: Engine) -> int:
    """
    Insert-only de achat.artwork (ON CONFLICT DO NOTHING sur la cle metier).

    Junior Tip : ON CONFLICT DO NOTHING est le pendant non-destructif de DO UPDATE,
    ideal quand la base fait foi sur les lignes existantes et que la source ne sert
    qu'a decouvrir les nouveautes.

    Args:
        df: DataFrame issu de transform_artwork().
        engine: SQLAlchemy engine PostgreSQL.
    Returns:
        Nombre de lignes nouvellement inserees.
    """
    if df.empty:
        logger.warning("[ATTENTION] DataFrame artwork vide -- rien a charger.")
        return 0

    logger.info("[INFO] Chargement artwork (insert-only) : %d candidats...", len(df))
    cols = list(df.columns)
    tmp_table = "achat._tmp_artwork"
    with engine.begin() as conn:
        df.to_sql("_tmp_artwork", conn, schema="achat",
                  if_exists="replace", index=False, method="multi")
        result = conn.execute(text(f"""
            INSERT INTO achat.artwork ({', '.join(cols)})
            SELECT {', '.join(cols)} FROM {tmp_table}
            ON CONFLICT (po_number, code_article) DO NOTHING;
        """))
        conn.execute(text(f"DROP TABLE IF EXISTS {tmp_table};"))

    logger.info("[SUCCES] Artwork : %d nouvelle(s) ligne(s) inseree(s).", result.rowcount)
    return result.rowcount


def load_ot_transport(df: pd.DataFrame, engine: Engine) -> int:
    """
    UPSERT de achat.ot_transport par n_conteneur (table temporaire + ON CONFLICT).

    Junior Tip : on UPSERT plutot qu'on TRUNCATE car deux sources alimentent cette
    table (bootstrap commande aujourd'hui, SUIVI MARITIME demain). Le full-refresh
    ferait perdre les conteneurs absents de la source courante.

    Args:
        df: DataFrame issu de transform_ot_transport().
        engine: SQLAlchemy engine PostgreSQL.
    Returns:
        Nombre de lignes upsertees.
    """
    if df.empty:
        logger.warning("[ATTENTION] DataFrame ot_transport vide -- rien a charger.")
        return 0

    logger.info("[INFO] Chargement ot_transport (upsert) : %d conteneur(s)...", len(df))
    cols = [c for c in df.columns if c != "n_conteneur"]
    set_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols)
    set_clause += ", charge_le = now()"

    tmp_table = "achat._tmp_ot_transport"
    with engine.begin() as conn:
        df.to_sql("_tmp_ot_transport", conn, schema="achat",
                  if_exists="replace", index=False, method="multi")
        conn.execute(text(f"""
            INSERT INTO achat.ot_transport ({', '.join(['n_conteneur'] + cols)})
            SELECT {', '.join(['n_conteneur'] + cols)} FROM {tmp_table}
            ON CONFLICT (n_conteneur) DO UPDATE SET {set_clause};
        """))
        conn.execute(text(f"DROP TABLE IF EXISTS {tmp_table};"))

    count = len(df)
    logger.info("[SUCCES] ot_transport charge : %d conteneur(s).", count)
    return count


def load_commande(df: pd.DataFrame, engine: Engine) -> int:
    """
    Full-refresh de la table achat.commande (TRUNCATE + INSERT).

    La granularite ligne-article (plusieurs lignes par PO#) rend l'UPSERT sur
    po_number impossible (non unique) : on recharge tout. RESTART IDENTITY remet
    le compteur SERIAL a 1 pour eviter une derive des ID.

    Junior Tip : engine.begin() garantit que TRUNCATE et INSERT sont dans la meme
    transaction -- si l'INSERT echoue, le TRUNCATE est annule (rollback) et les
    donnees precedentes restent intactes.

    Args:
        df: DataFrame commande transforme (issu de transform_commande).
        engine: SQLAlchemy engine PostgreSQL.
    Returns:
        Nombre de lignes inserees.
    """
    if df.empty:
        logger.warning("[ATTENTION] DataFrame commande vide -- rien a charger.")
        return 0

    logger.info("[INFO] Chargement commande (full-refresh) : %d lignes...", len(df))

    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE achat.commande RESTART IDENTITY;"))
        df.to_sql("commande", conn, schema="achat",
                  if_exists="append", index=False, method="multi")
        conn.execute(text(DDL_UQ_COMMANDE))

    count = len(df)
    logger.info("[SUCCES] Commande chargee : %d lignes.", count)
    return count


# Suivi qualite -- table ALIMENTEE PAR ETL depuis les colonnes qualite de l'IMPORT
# (checkpoints MAT/SP/echantillon/BAT, inspection DEKRA, reception, NCR). Grain
# produit (po_number, code_article). Full-refresh : aucune saisie utilisateur ici.
DDL_QUALITE = """
CREATE TABLE IF NOT EXISTS achat.qualite (
    id                     SERIAL PRIMARY KEY,
    po_number              TEXT NOT NULL,
    code_article           TEXT NOT NULL,
    fournisseur            TEXT,
    designation            TEXT,
    matiere                TEXT,
    semi_production        TEXT,
    echantillon_conformite TEXT,
    production_bat         TEXT,
    date_inspection        DATE,
    resultat_inspection    TEXT,   -- OK / FAIL / NULL (parse du rapport DEKRA)
    ref_rapport            TEXT,
    reception              TEXT,
    ncr                    TEXT,
    charge_le              TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT uq_qualite_po_article UNIQUE (po_number, code_article)
);
"""

# Evaluation qualite PAR FOURNISSEUR (agregat). Taux d'echec d'inspection,
# nombre de NCR et de receptions non conformes : mesures cles du suivi frs.
DDL_V_QUALITE_FOURNISSEUR = """
CREATE OR REPLACE VIEW achat.v_qualite_fournisseur AS
SELECT
    fournisseur,
    COUNT(*)                                                          AS nb_articles,
    COUNT(resultat_inspection)                                        AS nb_inspectes,
    COUNT(*) FILTER (WHERE resultat_inspection = 'OK')                AS nb_ok,
    COUNT(*) FILTER (WHERE resultat_inspection = 'FAIL')              AS nb_fail,
    ROUND(100.0 * COUNT(*) FILTER (WHERE resultat_inspection = 'FAIL')
          / NULLIF(COUNT(resultat_inspection), 0), 1)                 AS taux_fail_pct,
    COUNT(*) FILTER (WHERE ncr IS NOT NULL)                           AS nb_ncr,
    COUNT(*) FILTER (WHERE reception = 'Non conforme')                AS nb_reception_non_conforme
FROM achat.qualite
WHERE fournisseur IS NOT NULL
GROUP BY fournisseur
ORDER BY nb_fail DESC, nb_ncr DESC;
"""


def load_qualite(df: pd.DataFrame, engine: Engine) -> int:
    """
    Full-refresh de achat.qualite (TRUNCATE + INSERT).

    Table 100% derivee de l'ETL (pas de saisie utilisateur) -> full-refresh sur, comme
    achat.commande. La vue achat.v_qualite_fournisseur en derive l'evaluation frs.

    Junior Tip : le full-refresh garantit que les statuts qualite suivent toujours le
    dernier etat de l'IMPORT, sans risque de lignes orphelines d'un import precedent.

    Args:
        df: DataFrame issu de transform_qualite().
        engine: SQLAlchemy engine PostgreSQL.
    Returns:
        Nombre de lignes inserees.
    """
    if df.empty:
        logger.warning("[ATTENTION] DataFrame qualite vide -- rien a charger.")
        return 0

    logger.info("[INFO] Chargement qualite (full-refresh) : %d lignes...", len(df))
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE achat.qualite RESTART IDENTITY;"))
        df.to_sql("qualite", conn, schema="achat",
                  if_exists="append", index=False, method="multi")
    count = len(df)
    logger.info("[SUCCÈS] Qualite chargee : %d lignes.", count)
    return count


# Vue PREVISIONNEL par ligne -- phases d'avancement d'une commande import.
# Joint commande + qualite (pour "en inspection") sans alterer le modele. Montant
# ligne = PU*qte (jamais total_prix, qui est un SUMIF par PO). ETD effectif =
# reel sinon confirme. Repond au besoin demo : acheté / a payer / en inspection /
# parti / en retard / livré, declinable par fournisseur/produit.
DDL_V_PREVISIONNEL = """
CREATE OR REPLACE VIEW achat.v_previsionnel AS
SELECT
    c.id, c.po_number, c.code_article, c.fournisseur, c.designation, c.statut,
    COALESCE(c.etd_reel, c.etd_confirme)                         AS etd_eff,
    c.eta, c.date_livraison, c.date_paiement,
    CASE WHEN c.code_article IS NULL THEN COALESCE(c.total_prix, 0)
         ELSE COALESCE(c.prix_unitaire * c.quantite, 0) END      AS montant,
    (c.statut <> 'Annulée')                                      AS est_achete,
    (c.date_paiement IS NULL AND c.statut <> 'Annulée')          AS est_a_payer,
    (q.date_inspection IS NOT NULL
        AND c.statut NOT IN ('Livrée','Annulée'))                AS est_en_inspection,
    (c.statut = 'En cours de livraison'
        OR (COALESCE(c.etd_reel, c.etd_confirme) <= CURRENT_DATE
            AND c.date_livraison IS NULL
            AND c.statut NOT IN ('Livrée','Annulée')))           AS est_parti,
    (COALESCE(c.etd_reel, c.etd_confirme) < CURRENT_DATE
        AND c.date_livraison IS NULL
        AND c.statut NOT IN ('Livrée','Annulée'))                AS est_en_retard,
    (c.statut = 'Livrée')                                        AS est_livre,
    TO_CHAR(COALESCE(c.etd_reel, c.etd_confirme), 'YYYY-MM')      AS mois_etd,
    (c.date_paiement IS NULL
        AND COALESCE(c.etd_reel, c.etd_confirme) < CURRENT_DATE
        AND c.statut <> 'Annulée')                               AS est_a_payer_en_retard
FROM achat.commande c
LEFT JOIN achat.qualite q
    ON q.po_number = c.po_number AND q.code_article = c.code_article;
"""


def load_acompte(df: "pd.DataFrame", engine: Engine) -> int:
    """
    Full-refresh de achat.acompte depuis l'IMPORT (source officielle metier).

    Remplace l'enrichissement Sylob (montant absent cote ERP) : la verite est dans
    la colonne Acompte de l'IMPORT 2026, saisie par Marlene.

    Args:
        df: DataFrame issu de transform_acompte().
        engine: SQLAlchemy engine PostgreSQL.
    Returns:
        Nombre de lignes inserees.
    """
    if df.empty:
        logger.warning("[ATTENTION] DataFrame acompte vide -- rien a charger.")
        return 0
    logger.info("[INFO] Chargement acompte (full-refresh) : %d PO...", len(df))
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE achat.acompte;"))
        df.to_sql("acompte", conn, schema="achat", if_exists="append", index=False, method="multi")
    logger.info("[SUCCÈS] Acompte charge : %d PO.", len(df))
    return len(df)
