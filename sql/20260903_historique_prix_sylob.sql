-- =============================================================================
-- [SQL] HISTORIQUE PRIX SYLOB - REPLI SANS LIMITE DE DATE
-- =============================================================================
-- Besoin metier (mail Marlene MONTBRIZON du 03/09/2026, retour "TEST MODULES
-- ARTICLES") : l'onglet Article ne remonte les 3 derniers prix que depuis
-- achat.commande, alimente par IMPORT 2026.xlsx, qui ne couvre que juin 2024 a
-- aujourd'hui. Pour 788 articles du referentiel achat.produit, aucun prix ne
-- sort. Demande : "si il ne ressort rien alors il faut aller chercher les 3
-- derniers prix quelle que soit la date, on doit faire sauter la limitation de
-- date".
--
-- Cette table porte les 3 derniers prix d'achat par code article issus des
-- commandes fournisseur du DWH Sylob (2013 a aujourd'hui, 3 societes), toutes
-- societes et tous fournisseurs confondus. Elle sert UNIQUEMENT de repli quand
-- achat.commande ne renvoie rien : achat.commande reste la source de verite du
-- perimetre Import.
--
-- Donnee purement derivee : rechargee en full-refresh par
-- src/scripts/etl/enrich_historique_prix_sylob.py. Aucune saisie utilisateur
-- ne doit y etre ecrite (elle serait effacee au run suivant).
--
-- Non destructif : CREATE TABLE IF NOT EXISTS uniquement.
-- =============================================================================

CREATE TABLE IF NOT EXISTS achat.historique_prix_sylob (
    id                 BIGSERIAL     PRIMARY KEY,
    code_article       TEXT          NOT NULL,
    designation        TEXT,
    fournisseur        TEXT,
    po_number          TEXT,
    societe            TEXT          NOT NULL,
    date_commande      DATE,
    prix_unitaire      NUMERIC(18,6),
    prix_unitaire_eur  NUMERIC(18,6),
    devise_etrangere   BOOLEAN       NOT NULL DEFAULT FALSE,
    quantite           NUMERIC(18,4),
    unite              TEXT,
    rang               SMALLINT      NOT NULL,
    charge_le          TIMESTAMPTZ   NOT NULL DEFAULT now()
);

COMMENT ON TABLE  achat.historique_prix_sylob IS
    'Repli prix d''achat hors perimetre Import : 3 derniers prix par article depuis les commandes fournisseur Sylob (3 societes, sans borne de date). Full-refresh nocturne, ne jamais y ecrire a la main.';
COMMENT ON COLUMN achat.historique_prix_sylob.prix_unitaire IS
    'Prix unitaire HT en devise du document (USD sur un achat import).';
COMMENT ON COLUMN achat.historique_prix_sylob.prix_unitaire_eur IS
    'Prix unitaire HT converti en devise societe (EUR) par Sylob.';
COMMENT ON COLUMN achat.historique_prix_sylob.devise_etrangere IS
    'Vrai quand prix document et prix societe divergent : le prix affiche n''est pas en euros.';
COMMENT ON COLUMN achat.historique_prix_sylob.date_commande IS
    'Date de creation de la commande Sylob (commande_creee_le) : seule date fiable de la vue, les lignes datees dans le futur sont ecartees a l''ETL.';
COMMENT ON COLUMN achat.historique_prix_sylob.rang IS
    'Rang du prix pour l''article, 1 = le plus recent toutes societes confondues.';

CREATE INDEX IF NOT EXISTS idx_hps_code_article_rang
    ON achat.historique_prix_sylob (code_article, rang);