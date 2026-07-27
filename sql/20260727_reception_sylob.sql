-- ==============================================================================
-- FUSEAU — Rapprochement Réception Physiques Sylob ↔ FUSEAU
-- Script SQL idempotente d'ajout de la colonne date_reception_sylob
-- Rédigé le 27/07/2026
-- ==============================================================================

DO $$ 
BEGIN 
    -- 1. Table achat.commande
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'achat' 
          AND table_name = 'commande' 
          AND column_name = 'date_reception_sylob'
    ) THEN
        ALTER TABLE achat.commande ADD COLUMN date_reception_sylob DATE;
        COMMENT ON COLUMN achat.commande.date_reception_sylob IS 'Date de réception physique réelle enregistrée dans Sylob (table public.receptions_detaillees2)';
    END IF;

    -- 2. Table achat.qualite
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'achat' 
          AND table_name = 'qualite' 
          AND column_name = 'date_reception_sylob'
    ) THEN
        ALTER TABLE achat.qualite ADD COLUMN date_reception_sylob DATE;
        COMMENT ON COLUMN achat.qualite.date_reception_sylob IS 'Date de réception physique réelle enregistrée dans Sylob (table public.receptions_detaillees2)';
    END IF;
END $$;
