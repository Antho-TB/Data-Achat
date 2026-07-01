-- =============================================================================
-- Qualité #1/#2 -- index des rapports (lien FAIL->rapport) + extraction labo
-- =============================================================================
-- Décision 30/06 (B). Rapports DEKRA/labo rangés dans Drive/serveur par PO et stade.
-- qualite_doc = index (métadonnées + URL) pour ouvrir le rapport depuis un FAIL.
-- qualite_analyse = données extraites du texte SPECTRO (chrome/dureté/conformité).
-- Voir docs/profil_inspections_analyses.md. Idempotent.
-- =============================================================================

CREATE TABLE IF NOT EXISTS achat.qualite_doc (
    drive_file_id   TEXT PRIMARY KEY,       -- 1 ligne par fichier rapport
    po_number       TEXT,
    societe         TEXT,                   -- TB | GDD
    type            TEXT,                   -- analyse | inspection
    stade           TEXT,                   -- SP | MAT | production ...
    ref_rapport     TEXT,                   -- CA183435 (DEKRA)
    composant       TEXT,
    echantillon     TEXT,
    fichier         TEXT,
    drive_url       TEXT,
    source_fichier  TEXT,
    charge_le       TIMESTAMP WITHOUT TIME ZONE DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_qualite_doc_po  ON achat.qualite_doc (po_number);
CREATE INDEX IF NOT EXISTS ix_qualite_doc_ref ON achat.qualite_doc (ref_rapport);
GRANT SELECT, INSERT, UPDATE ON achat.qualite_doc TO platform_team;

CREATE TABLE IF NOT EXISTS achat.qualite_analyse (
    drive_file_id   TEXT PRIMARY KEY,       -- 1 analyse par fichier
    ref_rapport     TEXT,
    po_number       TEXT,
    echantillon     TEXT,
    sample_name     TEXT,
    hardness_hrc    NUMERIC,
    cr_pct          NUMERIC,                 -- chrome % (best-effort si texte aplati)
    conformite      TEXT,                    -- Conforme | Non conforme | NULL
    norme           TEXT,
    date_mesure     TIMESTAMP,
    source_fichier  TEXT,
    charge_le       TIMESTAMP WITHOUT TIME ZONE DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_qualite_analyse_po ON achat.qualite_analyse (po_number);
GRANT SELECT, INSERT, UPDATE ON achat.qualite_analyse TO platform_team;
