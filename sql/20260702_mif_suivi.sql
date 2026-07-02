-- =============================================================================
-- Item #3 plan captation -- POINT MIF (Made In France)
-- =============================================================================
-- Source : IMPORT 2026.xlsx, onglet "POINT MIF" (24x13, pivot gamme x coloris,
-- copie figee mars 2026 -- cf. decision Antho 02/07). Suivi lames envoyees /
-- couteaux retour / mitre envoyes / couteaux recus par lot PP et coloris.
-- Alimente le concept BI manquant "BILAN MADE IN France".
-- =============================================================================

CREATE TABLE IF NOT EXISTS achat.mif_suivi (
    id              SERIAL PRIMARY KEY,
    gamme           TEXT NOT NULL,      -- LAGUIOLE ACCESS / MEDIUM / PREMIUM
    stade           TEXT NOT NULL,      -- LAMES ENVOYEES / COUTEAUX EN RETOUR / MITRE ENVOYES / COUTEAUX RECUS
    lot_pp          TEXT NOT NULL,      -- PP226, PP227, PP231...
    coloris         TEXT NOT NULL,
    quantite        NUMERIC,
    total_ligne     NUMERIC,            -- total tous coloris pour (gamme, stade, lot_pp)
    source_fichier  TEXT,
    charge_le       TIMESTAMP WITHOUT TIME ZONE DEFAULT now(),
    UNIQUE (gamme, stade, lot_pp, coloris)
);

GRANT SELECT, INSERT, UPDATE, DELETE ON achat.mif_suivi TO platform_team;
