SELECT table_schema, table_name, column_name, data_type
FROM information_schema.columns
WHERE (table_schema = 'TARRERIAS_SE_TARRERIAS_BONJEAN_Qualite'
       AND table_name IN ('f_controlequalitereception','f_detailcontrolequalitereception','vue_controle_qualite_reception','f_fichenonconformite','vue_evaluation_fournisseur','vue_fiche_non_conformite','f_bonretour','f_retourfournisseur'))
   OR (table_schema = 'TARRERIAS_SE_TARRERIAS_BONJEAN_Fournisseur' AND table_name = 'af_fournisseur')
   OR (table_schema = 'TARRERIAS_SE_TARRERIAS_BONJEAN_Article' AND table_name IN ('a_famillearticle','a_grandefamillearticle','a_sousfamillearticle'))
   OR (table_schema = 'TARRERIAS_SE_TARRERIAS_BONJEAN_Concevoir' AND table_name = 'a_gammenomenclature')
   OR (table_schema = 'TARRERIAS_SE_TARRERIAS_BONJEAN_Finances' AND table_name IN ('a_conditionreglement','f_budget'))
ORDER BY table_schema, table_name, ordinal_position;
