-- =============================================================================
-- [FIX] Artwork = 100% G Sheet Clarisse, abandon complet de l'Excel IMPORT
-- =============================================================================
-- Decision metier 22/07 (Antho) : le statut artwork affiche dans FUSEAU doit
-- s'inspirer UNIQUEMENT du gsheet "LIS-CON-28-0 Suivi des artworks-import"
-- (Clarisse/Design), plus jamais de la colonne "statut artwork" heritee du
-- fichier Excel IMPORT (col N, chargee dans achat.artwork.statut_artwork par
-- le pipeline commande/PO).
--
-- Ce qu'on a decouvert en creusant (22/07) :
--   Le gsheet reel n'a que 2 onglets, SANS colonne "statut" explicite -- le
--   statut est l'appartenance a l'onglet lui-meme :
--     - "Artworks en attente"  (8 lignes reelles)   -> statut = 'En attente'
--     - "Liste artworks"       (385 lignes reelles) -> statut = 'Valide'
--   Total reel trackee par Clarisse = 393 articles. Les valeurs "A traiter"
--   (416 lignes), "Envoye" (54), "Attente Clarisse/Carrefour/Polyflame"
--   provenaient TOUTES de achat.artwork.statut_artwork (Excel IMPORT col N),
--   jamais du gsheet -- exactement ce qu'on nous demande d'oublier.
--   L'ancienne vue v_artwork partait de achat.artwork (951 lignes, perimetre
--   COMMANDE) en LEFT JOIN achat.artwork_statut (perimetre DESIGN, gsheet),
--   donc les ~558 articles jamais suivis par Clarisse affichaient quand meme
--   un "statut artwork" -- celui, non pertinent, de l'Excel IMPORT.
--
-- Correction : v_artwork part desormais de achat.artwork_statut (le miroir du
-- gsheet, 393 lignes) et NE JOINT achat.commande QUE pour un numero de PO
-- informatif (colonne bonus), jamais pour filtrer/completer le statut.
-- Reversible : CREATE OR REPLACE, ADD COLUMN IF NOT EXISTS. Idempotent.
-- =============================================================================

-- Le gsheet a 2 colonnes de commentaire DISTINCTES sur l'onglet "Artworks en
-- attente" (Commentaire Andrea / Commentaire Clarisse ou Thomas), en plus du
-- commentaire de validation (onglet "Liste artworks", reutilise la colonne
-- 'commentaire' existante). On ne les fusionne plus en un seul champ.
ALTER TABLE achat.artwork_statut
    ADD COLUMN IF NOT EXISTS commentaire_andrea TEXT,
    ADD COLUMN IF NOT EXISTS commentaire_clarisse_thomas TEXT;

COMMENT ON COLUMN achat.artwork_statut.statut_artwork IS
    'UNIQUEMENT ''En attente'' ou ''Valide'', derive de l appartenance a l onglet gsheet (decision 22/07). Plus aucun lien avec achat.artwork.statut_artwork (Excel IMPORT, perimetre commande/PO).';
COMMENT ON COLUMN achat.artwork_statut.commentaire IS
    'Commentaire sur derniere version -- onglet "Liste artworks" (articles VALIDES) uniquement.';
COMMENT ON COLUMN achat.artwork_statut.commentaire_andrea IS
    'Commentaire Andrea -- onglet "Artworks en attente" uniquement.';
COMMENT ON COLUMN achat.artwork_statut.commentaire_clarisse_thomas IS
    'Commentaire Clarisse / Thomas -- onglet "Artworks en attente" uniquement.';

-- Vue recentree sur achat.artwork_statut (gsheet). Le PO est un complement
-- d'affichage (pas un filtre, pas un enrichissement de statut) : agrege tous
-- les PO connus pour l'article, NULL si l'article n'a jamais ete commande.
-- DROP necessaire : l'ancienne vue partait de achat.artwork (1ere colonne
-- "id"), CREATE OR REPLACE seul refuse de renommer/reordonner les colonnes.
DROP VIEW IF EXISTS achat.v_artwork;
CREATE VIEW achat.v_artwork AS
SELECT
    s.code_article,
    s.designation,
    s.statut_artwork,
    s.date_demande,
    s.date_validation,
    s.derniere_version,
    s.priorite,
    s.valideur,
    s.commentaire,
    s.commentaire_andrea,
    s.commentaire_clarisse_thomas,
    (SELECT string_agg(DISTINCT c.po_number, ', ' ORDER BY c.po_number)
       FROM achat.commande c
      WHERE c.code_article = s.code_article)   AS po_number,
    s.charge_le AS updated_at
FROM achat.artwork_statut s;

GRANT SELECT ON achat.v_artwork TO platform_team;
