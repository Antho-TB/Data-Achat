-- =============================================================================
-- FUSEAU -- Table d'enrichissement persistante achat.commande_enrichissement
-- Redige le 28/07/2026 (audit de reprise post-Antigravity)
-- =============================================================================
-- POURQUOI CETTE TABLE
-- achat.commande et achat.qualite sont rechargees en full-refresh
-- (TRUNCATE + INSERT, cf. src/scripts/etl/load.py). Tout UPDATE applique
-- directement sur ces deux tables par un enrichissement (reception physique
-- Sylob, non-conformite remontee par mail) est donc DETRUIT au prochain
-- passage de l'ETL nocturne.
--
-- On applique ici le meme pattern que achat.commande_annotation : les donnees
-- qui ne viennent pas du fichier IMPORT sont stockees dans une table a part,
-- jointe par cle metier (po_number, code_article), puis reprojetees sur
-- achat.commande / achat.qualite par src/scripts/etl/apply_enrichissement.py
-- a la fin de chaque run ETL.
--
-- Grain : (po_number, code_article). code_article = '' pour un enrichissement
-- au niveau PO complet (cas d'une reception Sylob, qui n'est pas ventilee par
-- article dans public.receptions_detaillees2).
--
-- Script idempotent : rejouable sans effet de bord.
-- =============================================================================

CREATE TABLE IF NOT EXISTS achat.commande_enrichissement (
    po_number             TEXT        NOT NULL,
    code_article          TEXT        NOT NULL DEFAULT '',
    date_reception_sylob  DATE,
    non_conformite        TEXT,
    ncr_ref               TEXT,
    resultat_inspection   TEXT,
    source                TEXT        NOT NULL,
    maj_le                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT pk_commande_enrichissement PRIMARY KEY (po_number, code_article)
);

COMMENT ON TABLE achat.commande_enrichissement IS
    'Enrichissements hors fichier IMPORT (reception physique Sylob, NCR mail). Survit au full-refresh de achat.commande, reprojete par apply_enrichissement.py.';
COMMENT ON COLUMN achat.commande_enrichissement.code_article IS
    'Chaine vide = enrichissement au niveau du PO complet, pas d''une ligne article.';
COMMENT ON COLUMN achat.commande_enrichissement.source IS
    'Module a l''origine de la ligne : enrich_reception_sylob, load_email_ncr, saisie_manuelle.';

CREATE INDEX IF NOT EXISTS ix_commande_enrichissement_po
    ON achat.commande_enrichissement (po_number);

-- -----------------------------------------------------------------------------
-- Remise en phase des sequences des tables evenements.
-- Les INSERT de load_evenements.py / load_ot_gmail.py calculaient l'id via
-- (SELECT MAX(id) + 1), ce qui court-circuite la sequence et provoque une
-- collision de cle primaire des que deux executions se croisent (tache
-- planifiee + lancement manuel). On repasse sur la sequence native, donc il
-- faut la recaler sur le max courant avant de rendre la main.
-- -----------------------------------------------------------------------------
DO $$
DECLARE
    t TEXT;
    seq TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY['qualite_decision', 'transport_evenement',
                             'commerce_decision', 'design_evenement']
    LOOP
        seq := pg_get_serial_sequence('achat.' || t, 'id');
        IF seq IS NOT NULL THEN
            EXECUTE format(
                'SELECT setval(%L, COALESCE((SELECT MAX(id) FROM achat.%I), 0) + 1, false)',
                seq, t
            );
        END IF;
    END LOOP;
END $$;
