-- =============================================================================
-- Pattern A (artworks) -- suivi de validation design DÉCOUPLÉ, par ARTICLE
-- =============================================================================
-- Le "Suivi des artworks" (Clarisse, gsheet) est keyé par Référence (article),
-- SANS PO. achat.artwork est keyé (po_number, code_article). On découple :
-- la donnée niveau-article vit dans achat.artwork_statut (PK code_article) et la
-- vue v_artwork la fusionne sur code_article. Survit au full-refresh d'achat.artwork.
-- Décision 30/06. Voir docs/profil_artworks.md. Idempotent.
-- =============================================================================

CREATE TABLE IF NOT EXISTS achat.artwork_statut (
    code_article      TEXT PRIMARY KEY,
    designation       TEXT,
    statut_artwork    TEXT,
    date_demande      DATE,
    date_validation   DATE,
    derniere_version  DATE,
    priorite          INTEGER,
    valideur          TEXT,
    commentaire       TEXT,
    source_fichier    TEXT,
    charge_le         TIMESTAMP WITHOUT TIME ZONE DEFAULT now()
);

GRANT SELECT, INSERT, UPDATE ON achat.artwork_statut TO platform_team;

-- Vue de fusion : achat.artwork (par po_number, code_article) enrichie du suivi
-- design (par code_article). Le suivi design (Clarisse) PRIORITAIRE sur le statut
-- et la date de validation. Le merge ne duplique pas (1 statut par article).
CREATE OR REPLACE VIEW achat.v_artwork AS
SELECT a.id,
    a.po_number,
    a.code_article,
    COALESCE(s.designation, a.designation)         AS designation,
    COALESCE(s.statut_artwork, a.statut_artwork)   AS statut_artwork,
    a.responsable,
    COALESCE(s.commentaire, a.commentaire)         AS commentaire,
    COALESCE(s.date_validation, s.date_demande, a.date_demande) AS date_demande,
    s.date_validation,
    s.derniere_version,
    s.priorite,
    s.valideur,
    a.updated_at
   FROM achat.artwork a
     LEFT JOIN achat.artwork_statut s ON s.code_article = a.code_article;
