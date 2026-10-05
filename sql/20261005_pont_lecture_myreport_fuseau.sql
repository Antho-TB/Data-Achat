-- =============================================================================
-- [DROITS] Pont de lecture MyReport pour l'API FUSEAU (palliatif)
-- Date : 05/10/2026, auteur Antho Bezille (accord ecrit en session le 05/10)
-- =============================================================================
-- Pourquoi : dtpf_fuseau_api_prod n'a aucun SELECT sur les tables MyReport de
-- public, et le droit table par table disparait a chaque DROP/CREATE nocturne
-- de l'ETL MyReport. La solution durable (default privilege pour le role
-- proprietaire, sql/20261005_default_privileges_myreport_fuseau.sql) exige le
-- compte dtpf_sylob_myreport_prod, dont personne n'a le mot de passe a ce jour.
--
-- Palliatif : deux fonctions SECURITY DEFINER, proprietaire
-- dtpf_sylob_anthony_bezille_prod. Ce compte lit les tables MyReport via
-- group_dtpf_sylob_admin_prod, qui beneficie deja d'un default privilege du
-- proprietaire et garde donc son droit apres chaque recreation.
--
-- Garde-fous :
-- - SQL dynamique (EXECUTE) : aucune dependance enregistree sur les tables
--   MyReport, donc l'ETL MyReport peut toujours les supprimer et les recreer.
--   Une vue aurait bloque son DROP, ou ete supprimee en silence par un CASCADE.
-- - Perimetre fige : colonnes et tables en dur, aucun nom de table passe en
--   argument. Le role applicatif ne peut lire QUE ce qui est expose ici.
-- - search_path verrouille, EXECUTE retire a PUBLIC.
--
-- Dette assumee : un compte nominal derriere un service. A retirer des que le
-- default privilege est pose (DROP FUNCTION en bas de fichier).
-- =============================================================================

BEGIN;

CREATE OR REPLACE FUNCTION achat.fn_myreport_recherche_article(p_q text, p_lim integer)
RETURNS TABLE (code_article text, designation text, ean13 text, edi text)
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
    v_q   text    := btrim(coalesce(p_q, ''));
    v_lim integer := least(greatest(coalesce(p_lim, 10), 1), 50);
BEGIN
    IF v_q = '' THEN
        RETURN;
    END IF;
    RETURN QUERY EXECUTE $sql$
        SELECT a.code_article::text,
               COALESCE(MAX(a.designation) FILTER (WHERE a.libelle_langue ILIKE 'fran%'),
                        MAX(a.designation))::text,
               MAX(a.code_gtin_13)::text,
               MAX(a.identifiant_edi)::text
        FROM public.articles3 a
        WHERE a.code_article = $1
           OR (length($1) >= 2 AND (a.designation ILIKE '%' || $1 || '%'
                                    OR a.libelle ILIKE '%' || $1 || '%'))
           OR ($1 ~ '^[0-9]{4,}$' AND (a.code_gtin_13 ILIKE '%' || $1 || '%'
                                       OR a.identifiant_edi ILIKE '%' || $1 || '%'
                                       OR a.identifiant_edi2 ILIKE '%' || $1 || '%'
                                       OR a.sup_ean14_pcb ILIKE '%' || $1 || '%'
                                       OR a.sup_ean14_spcb ILIKE '%' || $1 || '%'
                                       OR a.sup_ean14_palette ILIKE '%' || $1 || '%'))
        GROUP BY a.code_article
        ORDER BY 2
        LIMIT $2
    $sql$ USING v_q, v_lim;
END
$fn$;

CREATE OR REPLACE FUNCTION achat.fn_myreport_intitules_commande(p_pos text[], p_max_ecart integer)
RETURNS TABLE (po text, intitule text)
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $fn$
BEGIN
    IF p_pos IS NULL OR cardinality(p_pos) = 0 THEN
        RETURN;
    END IF;
    RETURN QUERY EXECUTE $sql$
        SELECT DISTINCT ON (x.po) x.po, x.intitule
        FROM (
            SELECT ltrim(btrim(c.po_number::text), '0') AS po,
                   nullif(btrim(m.commande_reference), '')::text AS intitule,
                   abs(m.commande_creee_le::date - c.date_commande) AS ecart
            FROM achat.commande c
            JOIN public.commandes6 m
              ON ltrim(btrim(m.commande_numero_de_la_commande), '0')
               = ltrim(btrim(c.po_number::text), '0')
            WHERE ltrim(btrim(c.po_number::text), '0') = ANY($1)
        ) x
        WHERE x.intitule IS NOT NULL AND (x.ecart IS NULL OR x.ecart <= $2)
        ORDER BY x.po, x.ecart NULLS LAST
    $sql$ USING p_pos, least(greatest(coalesce(p_max_ecart, 180), 0), 3650);
END
$fn$;

REVOKE ALL ON FUNCTION achat.fn_myreport_recherche_article(text, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION achat.fn_myreport_intitules_commande(text[], integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION achat.fn_myreport_recherche_article(text, integer) TO dtpf_fuseau_api_prod;
GRANT EXECUTE ON FUNCTION achat.fn_myreport_intitules_commande(text[], integer) TO dtpf_fuseau_api_prod;

COMMIT;

-- Controle :
-- SELECT has_function_privilege('dtpf_fuseau_api_prod',
--        'achat.fn_myreport_recherche_article(text, integer)', 'EXECUTE');
-- SELECT * FROM achat.fn_myreport_recherche_article('couteau', 5);
--
-- Retrait, une fois le default privilege pose :
-- DROP FUNCTION achat.fn_myreport_recherche_article(text, integer);
-- DROP FUNCTION achat.fn_myreport_intitules_commande(text[], integer);
