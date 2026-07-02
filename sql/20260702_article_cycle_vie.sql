-- =============================================================================
-- Item #4 plan captation -- Cycle de vie article (STOP REF CARREFOUR)
-- =============================================================================
-- Source : IMPORT 2026.xlsx, onglet "STOP REF CARREFOUR" (16x7, copie figee
-- POC datee mars 2026 -- pas de gsheet vivant connu, cf. decision Antho 02/07,
-- a rafraichir si Andrea a une version a jour). Objectif : identifier les
-- articles Carrefour a l'arret / en sommeil (concept BI manquant "Articles en
-- sommeil" / cycle de vie).
-- =============================================================================

CREATE TABLE IF NOT EXISTS achat.article_cycle_vie (
    code_article            TEXT PRIMARY KEY,
    fournisseur             TEXT,
    designation             TEXT,
    quantite_en_commande    INTEGER,
    statut                  TEXT,          -- ex: "PAS DE COMMANDE EN COURS" / "SUR BATEAU NON ANNULABLE"
    ean13                   TEXT,
    source_fichier          TEXT,
    charge_le               TIMESTAMP WITHOUT TIME ZONE DEFAULT now()
);

GRANT SELECT, INSERT, UPDATE, DELETE ON achat.article_cycle_vie TO platform_team;
