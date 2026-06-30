-- FUSEAU — Extension des droits platform_team sur achat.commande
-- 2026-06-29 — décision write-path Gmail (Anthony)
-- À exécuter UNE FOIS par un rôle propriétaire du schéma achat (admin / myreport),
-- depuis le poste Antho (VPN + az login) ou via pgAdmin en compte admin.
-- platform_team ne peut PAS se l'auto-accorder.

GRANT INSERT, UPDATE ON achat.commande TO platform_team;

-- Si des INSERT s'appuient sur une séquence (clé technique auto-incrément) :
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA achat TO platform_team;

-- Vérification (attendu : SELECT, INSERT, UPDATE) :
-- SELECT grantee, privilege_type
-- FROM information_schema.role_table_grants
-- WHERE table_schema='achat' AND table_name='commande' AND grantee='platform_team';

-- Note gouvernance : ne PAS accorder TRUNCATE/DELETE/DROP à platform_team.
-- Tracer les écritures Gmail avec source='gmail' + updated_at. Revoir à la sortie du POC.
