SELECT COUNT(*) FILTER (WHERE montant_de_l_acompte <> 0) AS acompte_non_zero,
       COUNT(*) FILTER (WHERE pourcentage_d_acompte <> 0) AS pct_non_zero,
       COUNT(*) AS total
FROM "TARRERIAS_SE_TARRERIAS_BONJEAN_Achat".f_commandeachat;

SELECT sup_statut_pub_recaptransport, COUNT(*)
FROM "TARRERIAS_SE_TARRERIAS_BONJEAN_Achat".f_commandeachat
GROUP BY 1 ORDER BY 2 DESC LIMIT 5;

SELECT numero_de_la_commande, sup_date_dembarquement, sup_etd_confirme, sup_etd_demande
FROM "TARRERIAS_SE_TARRERIAS_BONJEAN_Achat".f_commandeachat
WHERE sup_etd_confirme IS NOT NULL LIMIT 5;
