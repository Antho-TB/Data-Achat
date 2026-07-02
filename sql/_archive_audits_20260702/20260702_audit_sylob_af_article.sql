SELECT COUNT(*) AS total,
       COUNT(code_gtin_13) AS ean13,
       COUNT(sup_code_douanier_us) AS hs_us,
       COUNT(sup_ean14_pcb) AS ean14_pcb,
       COUNT(sup_pcb) AS pcb,
       COUNT(sup_poids_pcb) AS poids_pcb,
       COUNT(sup_rapport_dinspection) AS rapport_inspection,
       COUNT(sup_certificat_matiere) AS certif_matiere
FROM "TARRERIAS_SE_TARRERIAS_BONJEAN_Article".af_article;
