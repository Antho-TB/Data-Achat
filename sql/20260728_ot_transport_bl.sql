-- =============================================================================
-- FUSEAU -- Plusieurs BL par conteneur
-- Redige le 28/07/2026 (retour Andrea)
-- =============================================================================
-- REGLE METIER
-- Les BL sont edites par les FOURNISSEURS, et un conteneur groupe plusieurs
-- fournisseurs. Un conteneur porte donc regulierement plusieurs BL. Le modele
-- ne le permettait pas : achat.ot_transport a le conteneur pour cle primaire et
-- une seule colonne n_bl, qui ne retenait que le premier BL rencontre. Les
-- suivants etaient perdus en silence.
--
-- CHOIX : une table fille plutot qu'un champ multivalue. Un BL est une entite a
-- part entiere (il declenche le paiement, il a son fournisseur), pas un
-- attribut du conteneur. Le grain (conteneur, BL) permettra plus tard de
-- rattacher facture et packing list a chaque BL.
--
-- achat.ot_transport.n_bl EST CONSERVEE : elle porte le BL principal, ce qui
-- evite de casser l'affichage existant et les vues. La table fille porte la
-- liste complete. Une fois l'UI et les vues basculees, la colonne pourra etre
-- retiree.
--
-- Script idempotent : rejouable sans effet de bord.
-- =============================================================================

CREATE TABLE IF NOT EXISTS achat.ot_transport_bl (
    n_conteneur    TEXT        NOT NULL,
    n_bl           TEXT        NOT NULL,
    fournisseur    TEXT,
    source_fichier TEXT,
    charge_le      TIMESTAMP   NOT NULL DEFAULT NOW(),
    CONSTRAINT pk_ot_transport_bl PRIMARY KEY (n_conteneur, n_bl)
);

COMMENT ON TABLE achat.ot_transport_bl IS
    'BL rattaches a un conteneur. Un conteneur groupe plusieurs fournisseurs, chacun editant son BL : la relation est 1-N. Alimentee par transform_maritime depuis le gsheet du transitaire (colonne M).';
COMMENT ON COLUMN achat.ot_transport_bl.fournisseur IS
    'Fournisseur emetteur du BL, quand le gsheet le precise.';

CREATE INDEX IF NOT EXISTS ix_ot_transport_bl_conteneur
    ON achat.ot_transport_bl (n_conteneur);
CREATE INDEX IF NOT EXISTS ix_ot_transport_bl_bl
    ON achat.ot_transport_bl (n_bl);

-- -----------------------------------------------------------------------------
-- Reprise de l'existant : les BL deja presents dans achat.ot_transport sont
-- recopies dans la table fille, pour ne pas repartir de zero. On ecarte les
-- valeurs qui ne sont manifestement pas des BL : le parsing historique y a
-- range du bruit ("DHL", "ATTACH", "ACKTRAY", "/"), qu'il est inutile de
-- propager dans une table neuve.
-- -----------------------------------------------------------------------------
INSERT INTO achat.ot_transport_bl (n_conteneur, n_bl, source_fichier)
SELECT n_conteneur, TRIM(n_bl), 'reprise:ot_transport'
FROM achat.ot_transport
WHERE n_bl IS NOT NULL
  AND TRIM(n_bl) <> ''
  AND LENGTH(TRIM(n_bl)) >= 6
  AND TRIM(n_bl) ~ '[0-9]'
ON CONFLICT (n_conteneur, n_bl) DO NOTHING;
