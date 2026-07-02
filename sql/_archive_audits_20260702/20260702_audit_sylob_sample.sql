SELECT code_article, designation, code_gtin_13, sup_ean14_pcb, sup_pcb,
       sup_poids_pcb, sup_rapport_dinspection, sup_certificat_matiere,
       sup_code_douanier_us
FROM "TARRERIAS_SE_TARRERIAS_BONJEAN_Article".af_article
WHERE sup_rapport_dinspection IS NOT NULL
LIMIT 5;
