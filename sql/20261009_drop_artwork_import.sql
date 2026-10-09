-- =============================================================================
-- [NETTOYAGE] Suppression de l'ancienne table achat.artwork (IMPORT col N)
-- Date : 09/10/2026, auteur Antho Bezille
-- =============================================================================
-- Pourquoi : achat.artwork portait le statut d'envoi de l'artwork au fournisseur
-- par ligne de commande (IMPORT 2026, colonne N). Plus aucune lecture depuis le
-- 22/07 (v_artwork part de achat.artwork_statut, cf. 20260722_artwork_gsheet_only.sql),
-- aucune vue dependante, et son nom bloquait le socle d'ecriture.
--
-- PREREQUIS : le poste de Marlene doit tourner sur un code qui ne charge plus
-- cette table (branche fix/socle-ecriture-table-artwork). Sinon l'ETL de 02h la
-- recree vide (create_tables_if_not_exist) et y reinsere l'IMPORT.
--
-- Archive complete conservee : achat._archive_artwork_import_20261009.
-- Execution : psql, compte nominal dtpf_sylob_anthony_bezille_prod (proprietaire).
-- =============================================================================

BEGIN;

CREATE TABLE achat._archive_artwork_import_20261009 AS
SELECT * FROM achat.artwork;

DO $$
DECLARE
    n_src bigint;
    n_arc bigint;
BEGIN
    SELECT count(*) INTO n_src FROM achat.artwork;
    SELECT count(*) INTO n_arc FROM achat._archive_artwork_import_20261009;
    IF n_src <> n_arc THEN
        RAISE EXCEPTION 'Archive incomplete : % lignes source, % archivees', n_src, n_arc;
    END IF;
    RAISE NOTICE 'Archive OK : % lignes', n_arc;
END $$;

DROP TABLE achat.artwork;

COMMIT;

-- Controle : SELECT to_regclass('achat.artwork');  -- attendu : NULL
-- Retour arriere :
-- CREATE TABLE achat.artwork AS SELECT * FROM achat._archive_artwork_import_20261009;
