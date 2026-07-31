-- =============================================================================
-- FUSEAU -- Montants de facture fournisseur : achat.facture_fournisseur
-- Redige le 31/07/2026 (retour Marlene du 29/07, session de paiement reelle)
-- =============================================================================
-- POURQUOI CETTE TABLE
-- Le 29/07, Marlene a paye en s'appuyant sur l'onglet Previsionnel et constate
-- que le montant affiche n'etait pas celui de la facture recue par mail
-- (HONGXING : 6 403,20 EUR sur la liasse, autre chose a l'ecran). Diagnostic :
-- aucun montant de facture n'existe dans FUSEAU. Les pieces jointes des mails
-- fournisseurs sont bien TOUTES telechargees (fetch_attachments.py accepte pdf,
-- xlsx, csv, docx), mais le seul parseur en place, parse_bl.py, a un perimetre
-- EXPEDITION : conteneur, BL, ETD, ETA, transitaire, numero de facture. Il lit
-- le NUMERO de facture, jamais son MONTANT, parce que sa table cible
-- achat.ot_transport n'a aucune colonne monetaire. Les montants affiches
-- viennent donc a 100 % de achat.commande, alimentee par IMPORT 2026.xlsx et
-- Sylob, que le metier doit justement cesser d'utiliser.
--
-- POURQUOI UNE TABLE DEDIEE, ET PAS DES COLONNES AILLEURS
-- 1. achat.commande est en full-refresh (TRUNCATE + INSERT, cf. load.py) : tout
--    montant ecrit dedans serait detruit au run suivant.
-- 2. achat.commande_enrichissement est au grain (po_number, code_article) : une
--    facture couvrant plusieurs PO devrait y etre ventilee arbitrairement, et
--    une note de credit n'y aurait pas de place propre.
-- 3. achat.ot_transport est la table du TRANSITAIRE, au grain conteneur. Or on
--    paie aussi des deposits et des avances qui ne correspondent a aucun
--    conteneur.
-- Le grain naturel est donc la PIECE COMPTABLE elle-meme.
--
-- REGLE DE SOURCE (a ne jamais contourner)
-- Cette table porte ce qu'un DOCUMENT dit, pas ce que FUSEAU croit. Le montant
-- IMPORT reste dans achat.commande, celui de la facture ici, et l'interface
-- affiche les DEUX avec l'ecart. Aucun recalcul, aucune conversion de devise
-- implicite : une facture en EUR est stockee en EUR.
--
-- Script idempotent : rejouable sans effet de bord.
-- =============================================================================

CREATE TABLE IF NOT EXISTS achat.facture_fournisseur (
    id                  BIGSERIAL   PRIMARY KEY,
    -- Identite de la piece
    n_facture           TEXT        NOT NULL,
    fournisseur         TEXT,
    type_piece          TEXT        NOT NULL DEFAULT 'facture',
    date_piece          DATE,
    -- Montant tel qu'il est ecrit sur le document. Negatif pour une note de
    -- credit : on ne stocke jamais un montant positif qu'il faudrait penser a
    -- soustraire, c'est la porte ouverte au double comptage.
    montant             NUMERIC(14, 2),
    devise              TEXT,
    montant_ht          NUMERIC(14, 2),
    -- Rattachements. Une facture peut couvrir plusieurs PO : on garde le
    -- tableau, sans ventiler.
    po_numbers          TEXT[],
    n_conteneur         TEXT,
    n_bl                TEXT,
    -- Tracabilite : d'ou vient ce chiffre, et a quel point on lui fait confiance
    source_fichier      TEXT        NOT NULL,
    source_message_id   TEXT,
    methode_extraction  TEXT        NOT NULL,
    confiance           NUMERIC(3, 2),
    texte_source        TEXT,
    -- Controle humain : une extraction automatique n'est pas une validation
    valide_par          TEXT,
    valide_le           TIMESTAMPTZ,
    charge_le           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_facture_type CHECK (
        type_piece IN ('facture', 'note_credit', 'deposit', 'avance', 'proforma')),
    CONSTRAINT ck_facture_signe CHECK (
        montant IS NULL
        OR (type_piece = 'note_credit' AND montant <= 0)
        OR (type_piece <> 'note_credit' AND montant >= 0)),
    CONSTRAINT ck_facture_confiance CHECK (
        confiance IS NULL OR (confiance >= 0 AND confiance <= 1))
);

-- Idempotence de l'ingestion : une meme piece relue depuis la meme PJ ne doit
-- pas creer de doublon. La cle inclut le fichier source : deux fournisseurs
-- peuvent emettre le meme numero de facture, et un meme numero peut etre
-- corrige puis renvoye dans une autre PJ.
CREATE UNIQUE INDEX IF NOT EXISTS uq_facture_piece_source
    ON achat.facture_fournisseur (n_facture, source_fichier);

CREATE INDEX IF NOT EXISTS ix_facture_fournisseur_frs
    ON achat.facture_fournisseur (fournisseur);
CREATE INDEX IF NOT EXISTS ix_facture_fournisseur_conteneur
    ON achat.facture_fournisseur (n_conteneur);
CREATE INDEX IF NOT EXISTS ix_facture_fournisseur_po
    ON achat.facture_fournisseur USING GIN (po_numbers);

COMMENT ON TABLE achat.facture_fournisseur IS
    'Pieces comptables fournisseurs extraites des PJ Gmail (facture, note de credit, deposit). Grain = une piece. Ne remplace jamais achat.commande : sert a AFFICHER l''ecart entre le montant du document et celui du fichier IMPORT.';
COMMENT ON COLUMN achat.facture_fournisseur.montant IS
    'Montant tel qu''ecrit sur la piece, dans sa devise d''origine. Negatif pour une note de credit. Aucune conversion.';
COMMENT ON COLUMN achat.facture_fournisseur.devise IS
    'Devise de la piece (EUR, USD...). Marlene a signale des factures en EUR alors que FUSEAU affiche des USD : la devise n''est pas une option.';
COMMENT ON COLUMN achat.facture_fournisseur.methode_extraction IS
    'Comment le montant a ete obtenu : llm:<modele>, regex, saisie_manuelle. Determine le niveau de confiance a accorder.';
COMMENT ON COLUMN achat.facture_fournisseur.confiance IS
    'Confiance de l''extraction, 0 a 1. En dessous du seuil metier, l''interface doit demander une validation humaine au lieu d''afficher le chiffre comme un fait.';
COMMENT ON COLUMN achat.facture_fournisseur.valide_par IS
    'NULL tant qu''aucun humain n''a confirme la piece. Une extraction automatique non validee ne doit jamais autoriser un paiement en silence.';
