-- [FIX] Garde-fou qualite sur le retard fournisseur
-- =============================================================================
-- Constat (diagnostic 20/07) : etd_confirme est pollue par des erreurs d'annee
-- (ex. confirme 2024-09-05 vs reel 2025-09-13 = ecart 373 j ≈ 1 an). Ces
-- valeurs faussent la moyenne fournisseur (WANXIN a 182 j de moyenne a cause de
-- ca). Un depart ne part pas realistiquement 6 mois apres l'ETD confirme : au
-- dela, c'est presque toujours une erreur de saisie/annee.
--
-- Garde-fou : on exclut de la MOYENNE fournisseur les expeditions dont l'ecart
-- absolu depasse 180 jours (probable erreur de donnee). v_retard_expedition
-- reste brute (ecart_jours visible) pour tracabilite / HITL.
-- Seuil 180 j ajustable selon validation metier.
-- Reversible : CREATE OR REPLACE.
-- =============================================================================

CREATE OR REPLACE VIEW achat.v_retard_fournisseur AS
SELECT
    fournisseur,
    COUNT(*)                                     AS nb_expeditions_12m,
    COUNT(*) FILTER (WHERE jours_retard > 0)      AS nb_expeditions_en_retard,
    ROUND(AVG(jours_retard), 1)                   AS retard_moyen_jours,
    MAX(etd_reel)                                 AS derniere_expedition,
    COUNT(*) FILTER (WHERE ABS(ecart_jours) > 180) AS nb_ecarts_suspects
FROM achat.v_retard_expedition
WHERE etd_reel >= CURRENT_DATE - INTERVAL '12 months'
  AND ABS(ecart_jours) <= 180   -- exclut les erreurs d'annee sur etd_confirme
GROUP BY fournisseur;
