-- =============================================================================
-- Tracabilite provenance packaging/dimensions -- achat.produit
-- =============================================================================
-- Contexte (02/07, question Antho) : achat.produit n'a aucune colonne
-- source_fichier, et enrich_dimensions.py (02/07) ecrit desormais dans les
-- memes colonnes (longueur_pcb_cm, poids_pcb_kg, ean14_pcb...) que celles
-- initialement remplies par la Matrice TB Import (transform_produit). Une
-- meme ligne peut donc avoir des champs Excel et des champs Sylob V25 --
-- sans marqueur, impossible de savoir lequel a eu le dernier mot.
--
-- Choix : PAS de lineage generalise (JSONB par champ) -- sur-ingenierie pour
-- un POC dont la finalite est de disparaitre dans Sylob (cf. decision 02/07,
-- reintegration ecriture Sylob). Un marqueur cible sur le seul bloc a risque
-- (packaging/dimensions) suffit.
--
-- IMPORTANT : sylob_synced_at existe deja (ajoutee par enrich_from_sylob.py,
-- ensure_sylob_columns) mais porte le bloc prix/delai_reappro. Reutiliser
-- cette meme colonne depuis enrich_dimensions.py ecraserait le marqueur de
-- l'autre job (impossible de savoir lequel des deux a synchronise en dernier)
-- -> colonne dediee ci-dessous, pattern ADD COLUMN IF NOT EXISTS idempotent
-- (identique a ensure_sylob_columns).
-- =============================================================================

ALTER TABLE achat.produit
  ADD COLUMN IF NOT EXISTS source_dimensions          TEXT,          -- 'sylob_v25' si au moins un champ packaging vient de Sylob, NULL sinon (Matrice Excel ou jamais renseigne)
  ADD COLUMN IF NOT EXISTS sylob_dimensions_synced_at  TIMESTAMPTZ;   -- horodatage dedie packaging/dimensions (distinct de sylob_synced_at = prix/delai)
