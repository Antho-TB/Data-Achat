-- =============================================================================
-- [FIX] Calcul du retard -- definition metier validee en demo du 07/07/2026
-- =============================================================================
-- Probleme corrige :
--   L'ancien v_retard_article calculait jours_retard = CURRENT_DATE - ETD, qui
--   croissait indefiniment (biais herite de la formule Excel =AUJOURDHUI). Le
--   retard n'etait donc jamais fige et melangeait deux notions distinctes.
--
-- Definition validee (07/07) :
--   retard d'expedition = ETD reel - ETD confirme, FIGE une fois le depart connu
--   (on ne recalcule plus contre la date du jour). Les avances (ETD reel < ETD
--   confirme) sont PLANCHEES a 0. Moyenne par fournisseur sur 12 mois glissants.
--
-- Deux axes SEPARES (decision 20/07) :
--   1. Retard d'expedition FIGE      -> v_retard_expedition / v_retard_fournisseur
--   2. Alerte operationnelle EN RETARD (ETD confirme depasse, pas encore parti,
--      pour appeler TB China) -> conservee dans v_retard_article.statut_retard,
--      mais bornee (plus de soustraction CURRENT_DATE stockee).
--
-- Source ETD reel : ot_transport prioritaire (BL/maritime), sinon commande.
-- Reversible : CREATE OR REPLACE, idempotent. A jouer sous VPN (DWH Azure).
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. Retard d'expedition -- grain ligne (PO x article), FIGE
-- -----------------------------------------------------------------------------
-- Une ligne par commande PARTIE (ETD reel connu). ecart_jours = valeur signee
-- (negatif = avance) conservee pour transparence ; jours_retard = plancher a 0
-- (base de la moyenne fournisseur, decision 20/07).
CREATE OR REPLACE VIEW achat.v_retard_expedition AS
SELECT
    c.po_number,
    c.code_article,
    c.fournisseur,
    c.etd_confirme,
    COALESCE(ot.etd_reel, c.etd_reel)                              AS etd_reel,
    (COALESCE(ot.etd_reel, c.etd_reel) - c.etd_confirme)           AS ecart_jours,
    GREATEST(COALESCE(ot.etd_reel, c.etd_reel) - c.etd_confirme, 0) AS jours_retard
FROM achat.commande c
LEFT JOIN achat.ot_transport ot ON ot.n_conteneur = c.n_conteneur
WHERE c.etd_confirme IS NOT NULL
  AND COALESCE(ot.etd_reel, c.etd_reel) IS NOT NULL;

-- -----------------------------------------------------------------------------
-- 2. Retard moyen par fournisseur -- 12 mois glissants
-- -----------------------------------------------------------------------------
-- Fenetre ancree sur l'ETD reel (depart effectif) dans les 12 derniers mois.
-- Chaque retard unitaire etant fige, seule la population de la fenetre glisse.
CREATE OR REPLACE VIEW achat.v_retard_fournisseur AS
SELECT
    fournisseur,
    COUNT(*)                                    AS nb_expeditions_12m,
    COUNT(*) FILTER (WHERE jours_retard > 0)     AS nb_expeditions_en_retard,
    ROUND(AVG(jours_retard), 1)                  AS retard_moyen_jours,
    MAX(etd_reel)                                AS derniere_expedition
FROM achat.v_retard_expedition
WHERE etd_reel >= CURRENT_DATE - INTERVAL '12 months'
GROUP BY fournisseur;

-- -----------------------------------------------------------------------------
-- 3. v_retard_article -- axe OPERATIONNEL (compat frontend)
-- -----------------------------------------------------------------------------
-- Colonnes inchangees (code_article, fournisseur, date_etd, jours_retard,
-- statut_retard) pour ne rien casser cote API. Semantique corrigee :
--   * jours_retard = retard d'expedition FIGE (max ecart connu, plancher 0),
--     NULL tant qu'aucune ligne de l'article n'est partie.
--   * statut_retard = etat operationnel BORNE (plus de CURRENT_DATE - ETD) :
--       CLOTUREE        -> toutes les lignes livrees/annulees
--       EN RETARD       -> au moins une ligne : ETD confirme depasse,
--                          pas livree, pas annulee (a relancer)
--       DANS LES DELAIS -> sinon
--       INCONNU         -> aucun ETD confirme
CREATE OR REPLACE VIEW achat.v_retard_article AS
SELECT
    c.code_article,
    c.fournisseur,
    max(COALESCE(ot.etd_reel, c.etd_reel, c.etd_confirme))          AS date_etd,
    max(GREATEST(COALESCE(ot.etd_reel, c.etd_reel) - c.etd_confirme, 0))
        FILTER (WHERE COALESCE(ot.etd_reel, c.etd_reel) IS NOT NULL
                  AND c.etd_confirme IS NOT NULL)                   AS jours_retard,
    CASE
        WHEN bool_and(c.statut = ANY (ARRAY['Livrée'::text, 'Annulée'::text]))
            THEN 'CLOTUREE'::text
        WHEN bool_or(
                 c.etd_confirme < CURRENT_DATE
                 AND c.date_livraison IS NULL
                 AND (c.statut <> ALL (ARRAY['Livrée'::text, 'Annulée'::text]))
             )
            THEN 'EN RETARD'::text
        WHEN max(c.etd_confirme) IS NULL
            THEN 'INCONNU'::text
        ELSE 'DANS LES DELAIS'::text
    END                                                            AS statut_retard
FROM achat.commande c
LEFT JOIN achat.ot_transport ot ON ot.n_conteneur = c.n_conteneur
GROUP BY c.code_article, c.fournisseur;
