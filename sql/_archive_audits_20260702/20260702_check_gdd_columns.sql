SELECT column_name FROM information_schema.columns
WHERE table_schema='TARRERIAS_GENERALE_DE_DECOUPAGE_Article' AND table_name='af_article'
  AND column_name LIKE 'sup_%' OR column_name = 'code_gtin_13';
