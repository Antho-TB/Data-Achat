-- =============================================================================
-- [SOCLE ECRITURE] Tables saisies dans FUSEAU et journal des modifications
-- Date : 08/10/2026, auteur Antho Bezille
-- Cadrage : docs/20261008_FUSEAU_Cadrage_PhaseEcriture_v1.md
-- =============================================================================
-- Pourquoi : FUSEAU devient la source des donnees hors ERP aujourd'hui tenues
-- dans des gsheets (artworks, suivi des analyses, facturation intersite).
-- Ces tables sont PERSISTANTES : aucun ETL ne les vide ni ne les recharge.
--
-- Principes :
-- - chaque ligne porte une version (concurrence optimiste) et son auteur ;
-- - chaque ecriture de l'API ajoute une ligne au journal ;
-- - pas de suppression : l'API recoit SELECT, INSERT, UPDATE, jamais DELETE.
--
-- Purement additif : aucune table existante n'est modifiee.
-- Execution : psql, compte nominal dtpf_sylob_anthony_bezille_prod (proprietaire
-- des tables de achat, droit CREATE sur le schema). Aucun effet reseau.
-- =============================================================================

BEGIN;

-- ---------------------------------------------------------------- journal
CREATE TABLE IF NOT EXISTS achat.journal_modification (
    id            bigserial   PRIMARY KEY,
    table_cible   text        NOT NULL,
    cle           text        NOT NULL,
    action        text        NOT NULL CHECK (action IN ('creation', 'modification', 'archivage', 'reprise')),
    avant         jsonb,
    apres         jsonb,
    auteur        text        NOT NULL,
    fait_le       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_journal_cible ON achat.journal_modification (table_cible, cle, fait_le DESC);
COMMENT ON TABLE achat.journal_modification IS
    'Historique de toutes les ecritures faites depuis FUSEAU : qui, quand, avant, apres. Jamais purge.';

-- ---------------------------------------------------------------- artworks
CREATE TABLE IF NOT EXISTS achat.artwork (
    id                    bigserial   PRIMARY KEY,
    identifiant           text        NOT NULL UNIQUE,   -- <article>-<AAAAMMJJ>[-n], fige a la creation
    code_article          text,                          -- NULL tant que la reference n'existe pas
    designation           text        NOT NULL,
    statut                text        NOT NULL DEFAULT 'en_attente'
                                      CHECK (statut IN ('en_attente', 'valide', 'archive')),
    priorite              smallint    CHECK (priorite BETWEEN 1 AND 5),
    valideur              text,
    commentaire_acheteur  text,
    commentaire_design    text,
    commentaire_version   text,
    lien_drive            text,
    date_demande          date,
    date_derniere_version date,
    cree_le               timestamptz NOT NULL DEFAULT now(),
    cree_par              text        NOT NULL,
    valide_le             timestamptz,
    valide_par            text,
    archive_le            timestamptz,
    archive_par           text,
    maj_le                timestamptz NOT NULL DEFAULT now(),
    maj_par               text        NOT NULL,
    version               integer     NOT NULL DEFAULT 1,
    origine               text        NOT NULL DEFAULT 'fuseau' CHECK (origine IN ('fuseau', 'reprise_gsheet'))
);
CREATE INDEX IF NOT EXISTS ix_artwork_article ON achat.artwork (code_article);
CREATE INDEX IF NOT EXISTS ix_artwork_statut ON achat.artwork (statut);
COMMENT ON TABLE achat.artwork IS
    'Artworks saisis dans FUSEAU (source depuis la bascule). Un article peut avoir plusieurs artworks.';

-- ---------------------------------------------------------------- analyses
-- Suivi des analyses qualite hors Sylob : la commande d'analyse (CA), ses
-- montants et son BL restent lus dans Sylob ; ici seulement ce que le metier
-- saisit (urgence, etat du produit, etat de l'analyse, archivage).
CREATE TABLE IF NOT EXISTS achat.analyse_suivi (
    id              bigserial   PRIMARY KEY,
    ca              text        NOT NULL,      -- n° de commande d'analyse Sylob (SE)
    code_article    text,
    stade           text        CHECK (stade IN ('MAT', 'SP', 'BAT', 'RECEP', 'ECH')),
    urgence         smallint    CHECK (urgence BETWEEN 1 AND 5),
    etat_produit    text,
    etat_analyse    text,
    commentaire     text,
    archive_le      timestamptz,
    archive_par     text,
    cree_le         timestamptz NOT NULL DEFAULT now(),
    cree_par        text        NOT NULL,
    maj_le          timestamptz NOT NULL DEFAULT now(),
    maj_par         text        NOT NULL,
    version         integer     NOT NULL DEFAULT 1,
    UNIQUE (ca, code_article, stade)
);

-- ---------------------------------------------------------------- facturation
-- Une ligne par CA : seulement la decision du metier. Montants, BL et etats de
-- facturation Sylob restent lus dans Sylob (app/facturation_intersite.py).
CREATE TABLE IF NOT EXISTS achat.facturation_intersite_suivi (
    ca                 text        PRIMARY KEY,
    facturation_faite  boolean     NOT NULL DEFAULT false,
    facturee_le        date,
    commentaire        text,
    maj_le             timestamptz NOT NULL DEFAULT now(),
    maj_par            text        NOT NULL,
    version            integer     NOT NULL DEFAULT 1
);

-- ---------------------------------------------------------------- droits API
GRANT SELECT, INSERT, UPDATE ON achat.journal_modification,
                                achat.artwork,
                                achat.analyse_suivi,
                                achat.facturation_intersite_suivi
      TO dtpf_fuseau_api_prod;
GRANT USAGE, SELECT ON SEQUENCE achat.journal_modification_id_seq,
                                achat.artwork_id_seq,
                                achat.analyse_suivi_id_seq
      TO dtpf_fuseau_api_prod;

COMMIT;

-- Controle :
-- SELECT c.relname,
--        has_table_privilege('dtpf_fuseau_api_prod', c.oid, 'INSERT') AS ins,
--        has_table_privilege('dtpf_fuseau_api_prod', c.oid, 'DELETE') AS del
-- FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
-- WHERE n.nspname = 'achat'
--   AND c.relname IN ('journal_modification', 'artwork', 'analyse_suivi', 'facturation_intersite_suivi');
-- Attendu : ins = true, del = false partout.
--
-- Retour arriere (tables vides uniquement, sinon archiver d'abord) :
-- DROP TABLE achat.facturation_intersite_suivi, achat.analyse_suivi, achat.artwork, achat.journal_modification;
