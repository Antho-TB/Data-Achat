SELECT table_name, column_name, data_type, ordinal_position
FROM information_schema.columns
WHERE table_schema = 'achat'
ORDER BY table_name, ordinal_position;
