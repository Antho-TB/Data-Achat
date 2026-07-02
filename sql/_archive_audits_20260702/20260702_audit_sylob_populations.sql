SELECT
  COUNT(*) AS total,
  COUNT(montant_de_l_acompte) AS montant_acompte,
  COUNT(pourcentage_d_acompte) AS pct_acompte,
  COUNT(sup_date_dembarquement) AS etd_embarquement,
  COUNT(sup_etd_confirme) AS etd_confirme,
  COUNT(sup_etd_demande) AS etd_demande,
  COUNT(sup_statut_pub_recaptransport) AS statut_recap_transport,
  COUNT(sup_envoye_a_bext) AS envoye_bext
FROM "TARRERIAS_SE_TARRERIAS_BONJEAN_Achat".f_commandeachat;

SELECT
  COUNT(*) AS total,
  COUNT(sup_nb_palette_europe) AS nb_palette,
  COUNT(sup_nb_total_de_colis) AS nb_colis,
  COUNT(sup_nombre_dunite_logistique) AS nb_unite_log,
  COUNT(sup_poids_suggestion_ot) AS poids_ot,
  COUNT(sup_volume) AS volume,
  COUNT(sup_rapport_dinspection) AS rapport_inspection,
  COUNT(sup_certificat_matiere) AS certif_matiere,
  COUNT(sup_nbl) AS nbl
FROM "TARRERIAS_SE_TARRERIAS_BONJEAN_Achat".f_lignecommandeachat;
