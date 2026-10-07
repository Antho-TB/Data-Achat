-- =============================================================================
-- [DROITS] Retrait du pont de lecture MyReport de l'API FUSEAU
-- Date : 07/10/2026, auteur Antho Bezille (accord ecrit en session le 07/10)
-- =============================================================================
-- Pourquoi : le pont achat.fn_myreport_* (sql/20261005_pont_lecture_myreport_fuseau.sql)
-- palliait la perte nocturne du SELECT de dtpf_fuseau_api_prod sur les tables
-- MyReport de public. Le default privilege pose le 06/10 sous le proprietaire
-- dtpf_sylob_myreport_prod tient : verifie le 07/10 apres recreation nocturne
-- de articles3, commandes6 et receptions_detaillees4.
--
-- Prealable verifie : l'API ne les appelle plus depuis la PR #34, deployee le
-- 07/10 (commit 1b35dc9, lu sur /api/health).
--
-- A executer avec le compte proprietaire des fonctions
-- (dtpf_sylob_anthony_bezille_prod).
--
-- Garde-fous : le bloc DO leve si les deux fonctions ne sont pas exactement
-- presentes, ou si le droit SELECT de l'API sur les tables lues n'est pas
-- acquis (le retrait casserait alors la recherche article).
--
-- Restauration : rejouer sql/20261005_pont_lecture_myreport_fuseau.sql.
-- =============================================================================

BEGIN;

DO $$
DECLARE
    n_fonctions integer;
BEGIN
    SELECT count(*) INTO n_fonctions
    FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'achat' AND p.proname LIKE 'fn\_myreport\_%';
    IF n_fonctions <> 2 THEN
        RAISE EXCEPTION '[ECHEC] % fonction(s) achat.fn_myreport_* trouvee(s), 2 attendues', n_fonctions;
    END IF;
    IF NOT (has_table_privilege('dtpf_fuseau_api_prod', 'public.articles3', 'SELECT')
            AND has_table_privilege('dtpf_fuseau_api_prod', 'public.commandes6', 'SELECT')) THEN
        RAISE EXCEPTION '[ECHEC] dtpf_fuseau_api_prod n''a pas SELECT sur articles3 ou commandes6 : retrait refuse';
    END IF;
END $$;

DROP FUNCTION achat.fn_myreport_recherche_article(text, integer);
DROP FUNCTION achat.fn_myreport_intitules_commande(text[], integer);

COMMIT;

-- Controle : doit rendre 0
-- SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
-- WHERE n.nspname = 'achat' AND p.proname LIKE 'fn\_myreport\_%';
