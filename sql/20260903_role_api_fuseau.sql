-- =============================================================================
-- [SQL] COMPTE DE SERVICE DE L'API FUSEAU HEBERGEE
-- =============================================================================
-- Contexte : l'application FUSEAU passe du poste de Marlene a une Web App Azure
-- (decision du 03/09/2026). Sur le poste, l'API tournait sous le compte nominal
-- d'Antho (psql-prod-sylob-anthony-bezille). Une application hebergee ne doit
-- jamais porter un compte nominal : depart, rotation de mot de passe ou audit
-- deviennent impossibles a traiter proprement, et les ecritures de l'appli sont
-- indistinguables de celles d'un humain.
--
-- Ce script cree un role de connexion dedie, au moindre privilege :
--   - lecture sur tout le schema achat (l'API est majoritairement en lecture) ;
--   - ecriture uniquement sur les tables de saisie metier ;
--   - aucun droit sur les tables rechargees par l'ETL en full-refresh, que
--     l'API n'a aucune raison de modifier.
--
-- Non destructif : aucun DROP, aucun DELETE. Idempotent.
--
-- PREREQUIS : definir le mot de passe hors de ce fichier, puis le deposer dans
-- kv-dtpf-prod sous psql-prod-fuseau-api-login / psql-prod-fuseau-api-password.
-- Ne jamais commiter le mot de passe.
--
-- Execution (a lancer avec le compte owner du schema, platform_team) :
--   psql "host=psql-dtpf-psql-prod.postgres.database.azure.com ..." \
--        -v mot_de_passe="'<secret>'" -f sql/20260903_role_api_fuseau.sql
-- =============================================================================

\set ON_ERROR_STOP on

-- Garde-fou : le mot de passe doit etre fourni, sinon on ne cree pas un role
-- sans authentification utilisable.
DO $$
BEGIN
    IF current_setting('is_superuser') = 'off'
       AND NOT pg_has_role(current_user, 'platform_team', 'member')
       AND current_user <> 'platform_team' THEN
        RAISE EXCEPTION
            'Ce script doit etre execute par platform_team (proprietaire du schema achat), pas par %',
            current_user;
    END IF;
END
$$;

-- 1. Role de connexion dedie a l'API hebergee.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dtpf_fuseau_api_prod') THEN
        EXECUTE format('CREATE ROLE dtpf_fuseau_api_prod LOGIN PASSWORD %L', :mot_de_passe);
        RAISE NOTICE '[SUCCES] Role dtpf_fuseau_api_prod cree.';
    ELSE
        EXECUTE format('ALTER ROLE dtpf_fuseau_api_prod PASSWORD %L', :mot_de_passe);
        RAISE NOTICE '[INFO] Role dtpf_fuseau_api_prod deja present, mot de passe mis a jour.';
    END IF;
END
$$;

-- 2. Lecture sur le schema achat et sur public.articles3 (recherche article).
GRANT USAGE ON SCHEMA achat  TO dtpf_fuseau_api_prod;
GRANT USAGE ON SCHEMA public TO dtpf_fuseau_api_prod;

GRANT SELECT ON ALL TABLES    IN SCHEMA achat TO dtpf_fuseau_api_prod;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA achat TO dtpf_fuseau_api_prod;
GRANT SELECT ON TABLE public.articles3 TO dtpf_fuseau_api_prod;

-- Les tables creees plus tard par l'ETL doivent l'etre aussi, sinon une nouvelle
-- table casse l'application au prochain deploiement sans que personne ne le voie.
ALTER DEFAULT PRIVILEGES FOR ROLE platform_team IN SCHEMA achat
    GRANT SELECT ON TABLES TO dtpf_fuseau_api_prod;

-- 3. Ecriture strictement limitee aux tables de saisie metier.
--    achat.commande, achat.produit, achat.qualite et achat.historique_prix_sylob
--    sont rechargees en full-refresh par l'ETL : l'API n'y ecrit jamais.
--    Verifie le 03/09/2026 dans app/main.py : les seules ecritures de l'API
--    visent achat.commande_annotation (annotations et paiements) et
--    achat.artwork_statut (statut artwork). achat.commande_enrichissement est
--    ecrite par l'ETL, pas par l'API : pas de droit d'ecriture ici.
GRANT SELECT, INSERT, UPDATE ON TABLE
      achat.commande_annotation,
      achat.artwork_statut
    TO dtpf_fuseau_api_prod;

GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA achat TO dtpf_fuseau_api_prod;

-- 4. Verification : lister ce que le role peut ecrire, pour relecture humaine.
SELECT table_name, string_agg(privilege_type, ', ' ORDER BY privilege_type) AS droits
FROM information_schema.table_privileges
WHERE grantee = 'dtpf_fuseau_api_prod'
  AND privilege_type IN ('INSERT', 'UPDATE', 'DELETE')
GROUP BY table_name
ORDER BY table_name;