-- =============================================================================
-- [PURGE] Ligne de test restee en production dans achat.transport_evenement
-- Date : 05/10/2026, auteur Antho Bezille (accord ecrit en session le 05/10)
-- =============================================================================
-- Pourquoi : un evenement "TEST_CONTAINER_SUBQUERY" (source test_script, cree le
-- 27/07) traine dans la table de production. Ce n'est pas un conteneur reel.
-- =============================================================================

BEGIN;

CREATE TABLE achat._archive_transport_evenement_test_20261005 AS
SELECT * FROM achat.transport_evenement
WHERE n_conteneur = 'TEST_CONTAINER_SUBQUERY' AND source = 'test_script';

DO $$
DECLARE n integer;
BEGIN
    SELECT COUNT(*) INTO n FROM achat._archive_transport_evenement_test_20261005;
    IF n <> 1 THEN
        RAISE EXCEPTION 'Volume inattendu : % lignes (attendu 1)', n;
    END IF;
END $$;

DELETE FROM achat.transport_evenement t
USING achat._archive_transport_evenement_test_20261005 a
WHERE t.id = a.id;

COMMIT;

-- Restauration :
-- INSERT INTO achat.transport_evenement SELECT * FROM achat._archive_transport_evenement_test_20261005;
