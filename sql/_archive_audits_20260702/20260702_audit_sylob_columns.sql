SELECT table_schema, table_name, column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'TARRERIAS_SE_TARRERIAS_BONJEAN_Achat'
  AND table_name IN ('f_commandeachat','f_lignecommandeachat','vue_commande_achat','vue_commande_achat_detail','f_receptionachat','f_lignereceptionachat')
ORDER BY table_name, ordinal_position;
