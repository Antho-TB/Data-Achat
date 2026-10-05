-- =============================================================================
-- [DROITS] Lecture durable des tables MyReport par l'API FUSEAU
-- Date : 05/10/2026, auteur Antho Bezille
-- =============================================================================
-- Pourquoi : dtpf_fuseau_api_prod n'a AUCUN droit sur les tables MyReport de
-- public (verifie le 05/10 par has_table_privilege : articles3, commandes6,
-- receptions_detaillees4, toutes a False). Le GRANT table par table du 03/09
-- (sql/20260903_role_api_fuseau.sql) disparait a chaque nuit : l'ETL MyReport
-- supprime et recree ses tables, et le droit part avec elles.
-- Consequences en production : la recherche article ne voit plus Sylob et
-- retombe sur achat.produit ; l'onglet Promo/Ope retombe sur l'IMPORT.
--
-- Seul un DEFAULT PRIVILEGE accorde POUR le role proprietaire survit aux
-- recreations. Le meme mecanisme existe deja sur public pour le groupe admin
-- (dtpf_sylob_myreport_prod -> group_dtpf_sylob_admin_prod = r), cree hors
-- Terraform.
--
-- QUI PEUT L'EXECUTER : uniquement le proprietaire dtpf_sylob_myreport_prod (ou
-- un membre de ce role), ou platform_team. Le compte nominal d'Antho n'a pas ce
-- droit (pas de GRANT OPTION, pas membre du role MyReport).
--
-- Perimetre : SELECT seul, sur les tables creees par MyReport. Rien d'autre.
-- Sans effet reseau ni redemarrage : n'expose pas l'IP de DTPF (cf. absence de
-- Samuel, tunnel Stormshield a ne pas perturber).
-- =============================================================================

-- 1. Tables existantes (effet immediat, jusqu'a la prochaine recreation)
GRANT SELECT ON ALL TABLES IN SCHEMA public TO dtpf_fuseau_api_prod;

-- 2. Tables futures creees par l'ETL MyReport dans public (effet durable)
ALTER DEFAULT PRIVILEGES FOR ROLE dtpf_sylob_myreport_prod IN SCHEMA public
    GRANT SELECT ON TABLES TO dtpf_fuseau_api_prod;

-- 3. Anticipation de la bascule vers le schema myreport. L'USAGE sur le schema
--    releve de platform_team (proprietaire) : a demander avec la proposition
--    MyReport/docs/20260930_Proposition_Nubo_droits_schema_myreport.tf.
ALTER DEFAULT PRIVILEGES FOR ROLE dtpf_sylob_myreport_prod IN SCHEMA myreport
    GRANT SELECT ON TABLES TO dtpf_fuseau_api_prod;
-- GRANT USAGE ON SCHEMA myreport TO dtpf_fuseau_api_prod;   -- par platform_team

-- Controle (doit renvoyer true partout, y compris le lendemain matin) :
-- SELECT has_table_privilege('dtpf_fuseau_api_prod', 'public.articles3', 'SELECT'),
--        has_table_privilege('dtpf_fuseau_api_prod', 'public.commandes6', 'SELECT'),
--        has_table_privilege('dtpf_fuseau_api_prod', 'public.receptions_detaillees4', 'SELECT');

-- Retour arriere :
-- ALTER DEFAULT PRIVILEGES FOR ROLE dtpf_sylob_myreport_prod IN SCHEMA public
--     REVOKE SELECT ON TABLES FROM dtpf_fuseau_api_prod;
-- ALTER DEFAULT PRIVILEGES FOR ROLE dtpf_sylob_myreport_prod IN SCHEMA myreport
--     REVOKE SELECT ON TABLES FROM dtpf_fuseau_api_prod;
-- REVOKE SELECT ON ALL TABLES IN SCHEMA public FROM dtpf_fuseau_api_prod;
