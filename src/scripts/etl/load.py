# -*- coding: utf-8 -*-
"""
[DATA ENGINEERING]
Chargement des données transformées dans PostgreSQL (schéma achat) du DWH TB Groupe.

Stratégie : les opérations sont idempotentes et re-exécutables sans risque.
achat.produit utilise un UPSERT (INSERT ... ON CONFLICT DO UPDATE) pour préserver
les enrichissements Sylob ajoutés hors-pipeline. achat.commande utilise un
full-refresh (TRUNCATE + INSERT) car la granularité ligne-article rend l'UPSERT
complexe et le volume reste faible (< 10 000 lignes).
"""
import logging

import pandas as pd
from sqlalchemy import Engine, text

logger = logging.getLogger(__name__)

DDL_SCHEMA = "CREATE SCHEMA IF NOT EXISTS achat;"

DDL_PRODUIT = """
CREATE TABLE IF NOT EXISTS achat.produit (
    code_article         TEXT PRIMARY KEY,
    -- Identifiants & traçabilité
    code_provisoire      TEXT,              -- JJMMAAHHMM avant code article définitif
    type_circuit         TEXT,              -- 'A1' (usine GDD) | 'A2' (import Chine) | 'B' (réappro)
    -- Bloc Produit (Jonatan)
    ean13                TEXT,
    ean14_pcb            TEXT,
    ean14_spcb           TEXT,
    designation_fr       TEXT,
    designation_en       TEXT,
    marque               TEXT,              -- ex: Laguiole, Suricate
    gamme                TEXT,
    grande_famille       TEXT,
    -- Bloc Sourcing (Julia)
    fournisseur          TEXT,
    pays_fournisseur     TEXT,              -- ex: CHINE, FRANCE
    -- Bloc Commerce (Eric)
    client_unique        TEXT,              -- client spécifique si exclusivité
    code_client          TEXT,
    prix_vente           NUMERIC,           -- prix de vente cible
    -- Catalogue
    type_lot             TEXT,              -- 'Lot' | 'Vrac' | 'Unitaire'
    nomenclature         TEXT,             -- code douanier HS Code
    -- Bloc Design  -- matières
    matiere_lame         TEXT,
    chrome_pct           NUMERIC,          -- % chrome acier
    traitement_thermique TEXT,
    matiere_manche       TEXT,
    finition             TEXT,
    -- Bloc Design  -- marquage
    marquage_libelle     TEXT,
    artwork              TEXT,             -- référence artwork/visuel
    -- Dimensions produit
    poids_uvc_g          NUMERIC,
    longueur_mm          NUMERIC,
    epaisseur_mm         NUMERIC,
    -- Bloc Logistique (Emmanuelle)
    pcb                  INTEGER,          -- pièces par carton maître
    spcb                 INTEGER,          -- pièces par carton intérieur
    inner_qty            INTEGER,          -- INNER (cartons intérieurs par master)
    master_qty           INTEGER,          -- MASTER (cartons par palette)
    longueur_pcb_cm      NUMERIC,
    largeur_pcb_cm       NUMERIC,
    hauteur_pcb_cm       NUMERIC,
    poids_pcb_kg         NUMERIC,
    volume_m3            NUMERIC,
    -- Méta
    date_creation        DATE,
    date_maj             DATE,             -- dernière mise à jour fiche
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


def create_tables_if_not_exist(engine: Engine) -> None:
    """
    Crée les tables achat.produit et achat.commande si elles n'existent pas.

    Le DDL utilise CREATE TABLE IF NOT EXISTS pour être idempotent -- aucune
    erreur si les tables existent déjà. Le schéma achat doit être pré-créé
    manuellement par un admin car CREATE SCHEMA requiert des droits DATABASE-level
    que l'utilisateur ETL ne possède pas (principe du moindre privilège).

    Junior Tip : engine.begin() ouvre une transaction DDL. PostgreSQL autorise
    les DDL en transaction (contrairement à MySQL), ce qui garantit l'atomicité :
    soit les deux tables sont créées, soit aucune.

    Args:
        engine: SQLAlchemy engine connecté à PostgreSQL (schéma achat accessible).
    Returns:
        None
    """
    logger.info("[INFO] Création des tables PostgreSQL (si nécessaire)...")
    with engine.begin() as conn:
        # DDL_SCHEMA retiré -- schéma créé manuellement par platform_team
        conn.execute(text(DDL_PRODUIT))
        conn.execute(text(DDL_COMMANDE))
    logger.info("[SUCCÈS] Tables prêtes.")


def load_produit(df: pd.DataFrame, engine: Engine) -> int:
    """
    UPSERT de la table achat.produit via table temporaire intermédiaire.

    Stratégie en deux temps : on écrit d'abord dans une table temporaire
    achat._tmp_produit, puis on exécute l'INSERT ... ON CONFLICT depuis cette
    table vers achat.produit. Cette approche évite de construire une requête
    paramétrée avec N*M paramètres (trop lourd pour psycopg2 au-delà de ~500 lignes).

    Junior Tip : ON CONFLICT DO UPDATE (UPSERT PostgreSQL) garantit l'idempotence :
    re-exécuter le pipeline deux fois ne créera pas de doublons. EXCLUDED est un
    pseudo-alias PostgreSQL qui désigne la ligne "candidate" qui a provoqué le conflit.

    Args:
        df: DataFrame produit transformé (issu de transform_produit).
        engine: SQLAlchemy engine PostgreSQL.
    Returns:
        Nombre de lignes insérées ou mises à jour.
    """
    if df.empty:
        logger.warning("[ATTENTION] DataFrame produit vide -- rien à charger.")
        return 0

    logger.info("[INFO] Chargement produit : %d articles...", len(df))

    cols = [c for c in df.columns if c != "code_article"]
    set_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols)
    set_clause += ", updated_at = now()"

    tmp_table = "achat._tmp_produit"
    with engine.begin() as conn:
        df.to_sql("_tmp_produit", conn, schema="achat",
                  if_exists="replace", index=False, method="multi")
        result = conn.execute(text(f"""
            INSERT INTO achat.produit ({', '.join(['code_article'] + cols)})
            SELECT {', '.join(['code_article'] + cols)} FROM {tmp_table}
            ON CONFLICT (code_article) DO UPDATE SET {set_clause};
        """))
        conn.execute(text(f"DROP TABLE IF EXISTS {tmp_table};"))

    count = len(df)
    logger.info("[SUCCÈS] Produit chargé : %d articles.", count)
    return count


def load_commande(df: pd.DataFrame, engine: Engine) -> int:
    """
    Full-refresh de la table achat.commande (TRUNCATE + INSERT).

    La table commande a une granularité ligne-article (plusieurs lignes par PO#),
    donc pas d'UPSERT possible sur po_number seul car il n'est pas unique.
    On préfère le full-refresh : TRUNCATE vide la table puis INSERT recharge tout.
    RESTART IDENTITY remet le compteur SERIAL à 1 pour éviter une dérive infinie des ID.

    Junior Tip : engine.begin() garantit que TRUNCATE et INSERT sont dans la même
    transaction -- si l'INSERT échoue, le TRUNCATE est annulé (rollback automatique)
    et les données précédentes restent intactes.

    Args:
        df: DataFrame commande transformé (issu de transform_commande).
        engine: SQLAlchemy engine PostgreSQL.
    Returns:
        Nombre de lignes insérées.
    """
    if df.empty:
        logger.warning("[ATTENTION] DataFrame commande vide -- rien à charger.")
        return 0

    logger.info("[INFO] Chargement commande (full-refresh) : %d lignes...", len(df))

    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE achat.commande RESTART IDENTITY;"))
        df.to_sql("commande", conn, schema="achat",
                  if_exists="append", index=False, method="multi")

    count = len(df)
    logger.info("[SUCCÈS] Commande chargée : %d lignes.", count)
    return count
