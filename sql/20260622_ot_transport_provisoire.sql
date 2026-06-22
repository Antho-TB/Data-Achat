-- =====================================================================
-- [DATA ENGINEERING] achat.ot_transport -- suivi maritime / transitaire
-- =====================================================================
-- Source cible : \\Srv-files-pom\...\2026\TRANSITAIRE\2026 SUIVI MARITIME.xlsx
--                feuille "CONTENEUR PLEIN" (+ version 2025).
-- Cle de jointure vers achat.commande = N° Conteneur (IMPORT 2026 col AP).
-- Grain = 1 ligne PAR CONTENEUR (un conteneur transporte plusieurs lignes PO).
--
-- STATUT : PROVISOIRE. Les colonnes exactes de CONTENEUR PLEIN restent a
-- confirmer une fois l'acces au dossier TRANSITAIRE obtenu. On modelise ici
-- ce que la VLOOKUP de l'IMPORT consomme aujourd'hui (cols renvoyees : ETD reel,
-- ETA, Date livraison, Transport) + les champs de rapprochement evidents.
--
-- Regle d'archi (cf. ADR 2026-06-10) : table alimentee par ETL (full-refresh ou
-- upsert par conteneur). AUCUNE saisie utilisateur ici -> annotations ailleurs.
-- =====================================================================

CREATE TABLE IF NOT EXISTS achat.ot_transport (
    n_conteneur      TEXT PRIMARY KEY,          -- ex. 'CMAU6128009' (cle metier)
    etd_reel         DATE,                      -- depart reel navire
    eta              DATE,                      -- arrivee estimee port
    date_livraison   TIMESTAMP,                 -- livraison effective (heure incluse dans la source)
    transport        TEXT,                      -- mode / compagnie (col renvoyee par CONTENEUR PLEIN)
    transitaire      TEXT,                      -- ex. 'QUALITAIRSEA' (IMPORT col AS)
    n_bl             TEXT,                      -- numero BL (IMPORT col AO)
    n_facture        TEXT,                      -- numero facture (IMPORT col AQ)
    lieu_livraison   TEXT,                      -- ex. 'GDD' (IMPORT col AN)
    -- Tracabilite ETL
    source_fichier   TEXT,                      -- nom du classeur SUIVI MARITIME ingere
    charge_le        TIMESTAMP NOT NULL DEFAULT now()
);

COMMENT ON TABLE  achat.ot_transport IS
    'Suivi maritime par conteneur (source transitaire SUIVI MARITIME). PROVISOIRE 2026-06-22.';
COMMENT ON COLUMN achat.ot_transport.n_conteneur IS
    'Cle de jointure vers achat.commande (IMPORT 2026 col AP N° Conteneur).';

-- Index de jointure cote commande (si N° Conteneur y est stocke / a ajouter).
-- CREATE INDEX IF NOT EXISTS ix_commande_conteneur ON achat.commande (n_conteneur);

-- Vue de service : ETD effectif = COALESCE(transport reel, confirme) -- coherente
-- avec achat.v_retard_article (regle ETD effectif de l'ADR).
-- A activer une fois la table alimentee :
-- CREATE OR REPLACE VIEW achat.v_suivi_conteneur AS
-- SELECT c.po_number, c.code_article, c.n_conteneur,
--        t.etd_reel, t.eta, t.date_livraison, t.transitaire, t.n_bl
-- FROM achat.commande c
-- LEFT JOIN achat.ot_transport t USING (n_conteneur);

-- Grants poste Marlene (lecture seule, coherent avec platform_team) :
-- GRANT SELECT ON achat.ot_transport TO platform_team;
