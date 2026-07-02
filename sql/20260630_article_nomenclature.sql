-- =============================================================================
-- Nomenclature article (source Matrice TB Import.xlsx) -- décision 30/06
-- =============================================================================
-- Composant + packaging + gamme + HS code, par article. Full-refresh (relu de
-- l'Excel). Débloque le concept BI manquant "Gammes & Sous-familles / nomenclature".
-- ⚠️ Cible stratégique = ramener ces données dans Sylob (vérifier d'abord ce qui
-- existe déjà dans Sylob). Table achat.* = étape POC. Voir docs/audit_excels_service_achat.md.
-- =============================================================================

CREATE TABLE IF NOT EXISTS achat.article_nomenclature (
    code_article        TEXT PRIMARY KEY,
    description_fr      TEXT,
    description_en      TEXT,
    fournisseur         TEXT,
    date_creation       DATE,
    gamme               TEXT,
    lot_vrac            TEXT,
    nb_piece            INTEGER,
    ean13               TEXT,
    ean14_spcb          TEXT,
    ean14_pcb           TEXT,
    hs_code             TEXT,
    epaisseur_mm        NUMERIC,
    longueur_mm         NUMERIC,
    poids_g             NUMERIC,
    matiere_lame        TEXT,
    chrome_pct          NUMERIC,
    finition            TEXT,
    matiere_manche      TEXT,
    pantone_manche      TEXT,
    marquage            TEXT,
    dim_marquage        TEXT,
    emplacement_marquage TEXT,
    source_fichier      TEXT,
    charge_le           TIMESTAMP WITHOUT TIME ZONE DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_article_nomenclature_gamme ON achat.article_nomenclature (gamme);
GRANT SELECT, INSERT, UPDATE ON achat.article_nomenclature TO platform_team;
