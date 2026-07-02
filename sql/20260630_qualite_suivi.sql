-- =============================================================================
-- Qualité #5 -- SUIVI DES ANALYSES (décision A, 30/06)
-- =============================================================================
-- Grain échantillon (article × PO × CA × stade), incompatible avec l'UNIQUE
-- (po_number, code_article) d'achat.qualite -> table dédiée. Full-refresh (relu
-- du gsheet). Se joint à qualite_doc / qualite_analyse par ref_rapport (CA).
-- Bloc E (facturation labo) = grain rapport CA -> table séparée.
-- Voir docs/profil_suivi_analyses.md. Idempotent.
-- =============================================================================

CREATE TABLE IF NOT EXISTS achat.qualite_suivi (
    id              SERIAL PRIMARY KEY,
    code_article    TEXT,
    designation     TEXT,
    stade           TEXT,               -- MAT | SP | BAT | RECEP
    po_number       TEXT,
    ref_rapport     TEXT,               -- CA<num> (jointure #1/#2)
    date_envoi      DATE,
    n_bl            TEXT,
    date_bl         DATE,
    niveau_urgence  INTEGER,
    etat_produit    TEXT,
    etat_analyse    TEXT,
    operateur       TEXT,
    origine         TEXT,               -- en_cours (bloc A) | archive (bloc D)
    source_fichier  TEXT,
    charge_le       TIMESTAMP WITHOUT TIME ZONE DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_qualite_suivi_po  ON achat.qualite_suivi (po_number);
CREATE INDEX IF NOT EXISTS ix_qualite_suivi_ref ON achat.qualite_suivi (ref_rapport);
GRANT SELECT, INSERT, UPDATE ON achat.qualite_suivi TO platform_team;

CREATE TABLE IF NOT EXISTS achat.qualite_facturation (
    id                SERIAL PRIMARY KEY,
    stade             TEXT,
    po_number         TEXT,
    ref_rapport       TEXT,
    nb_spectro        INTEGER,
    nb_durete         INTEGER,
    nb_meca           INTEGER,
    nb_cycle10        INTEGER,
    nb_cycle_10_50    INTEGER,
    nb_cycle_50       INTEGER,
    nb_rapport        INTEGER,
    montant_ht_ca     NUMERIC,
    n_bl              TEXT,
    date_bl           DATE,
    montant_ht_bl     NUMERIC,
    a_facturer        BOOLEAN,
    facturation_faite BOOLEAN,
    source_fichier    TEXT,
    charge_le         TIMESTAMP WITHOUT TIME ZONE DEFAULT now()
);
GRANT SELECT, INSERT, UPDATE ON achat.qualite_facturation TO platform_team;
