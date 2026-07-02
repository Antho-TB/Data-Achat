-- =============================================================================
-- Item #1b plan captation -- Nomenclature Lot Multiples (multi-composant)
-- =============================================================================
-- Source : Matrice TB Import.xlsx, onglet "Lot Multiples produits" (752x122,
-- copie figee mars 2026 -- cf. decision Antho 02/07). Un article "lot multiple"
-- (ex: coffret 24 pieces) a jusqu'a 8 composants, chacun avec sa propre
-- matiere/finition/marquage -- achat.article_nomenclature ne porte qu'UN seul
-- jeu de champs composant (adapte au Lot-Vrac mono-composant). On decouple :
-- cette table porte le detail par composant (grain code_article x position),
-- achat.article_nomenclature garde l'identite header (gamme/HS/EAN/nb_piece)
-- avec lot_vrac='Multiple' pour ces articles (deja la colonne, pas de migration).
-- =============================================================================

CREATE TABLE IF NOT EXISTS achat.article_nomenclature_composant (
    code_article        TEXT NOT NULL,
    position            INTEGER NOT NULL,      -- 1..8, ordre des blocs composant dans la Matrice
    nom_composant        TEXT,
    epaisseur_mm         NUMERIC,
    longueur_mm          NUMERIC,
    poids_g              NUMERIC,
    matiere_lame         TEXT,
    chrome_pct           NUMERIC,
    finition             TEXT,
    matiere_manche       TEXT,
    pantone_manche       TEXT,
    marquage             TEXT,
    dim_marquage         TEXT,
    emplacement_marquage TEXT,
    source_fichier       TEXT,
    charge_le            TIMESTAMP WITHOUT TIME ZONE DEFAULT now(),
    PRIMARY KEY (code_article, position)
);

GRANT SELECT, INSERT, UPDATE, DELETE ON achat.article_nomenclature_composant TO platform_team;
