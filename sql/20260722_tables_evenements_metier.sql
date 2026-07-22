-- =============================================================================
-- FUSEAU / achat.* — Tables d'événements métier issus du flux Gmail informel
-- =============================================================================
-- Migration 2026-07-22. À exécuter avec l'identité OWNER/ADMIN (poste Antho).
--
-- Principe directeur : achat.* ne stocke QUE le non-Sylob. Ces 4 sujets sont
-- confirmés absents de Sylob (audit 02/07, docs/modele_semantique.md) :
--   - qualite_decision   : décision conforme/non-conforme (email-first, Eric T).
--                          Sylob a un FNC formel (f_fichenonconformite) à réconcilier
--                          plus tard, mais la décision informelle par mail est hors Sylob.
--   - transport_evenement: retards / imprévus / changements ETD-ETA-livraison (transitaire).
--                          Absorbe le besoin ot_transport_date_evenement de la spec ETA.
--   - commerce_decision  : arbitrages commerce (prix client, go/no-go, priorité, promo).
--   - design_evenement   : validations design (boîte, artwork, marquage, pantone — Clarisse).
--
-- Remplacent le fourre-tout achat.commande_annotation (conservé pour le divers non classé).
-- Idempotence : colonne cle_idempotence UNIQUE (le loader fait ON CONFLICT DO NOTHING).
-- Colonnes communes : po_number, code_article, n_conteneur, thread_id, acteur, source, date_info, texte, created_at.
-- =============================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS achat.qualite_decision (
    id              serial PRIMARY KEY,
    cle_idempotence text        NOT NULL UNIQUE,
    po_number       text,
    code_article    text,
    n_conteneur     text,
    thread_id       text,
    acteur          text,
    source          text,                 -- mail_corps | mail_pj | gsheet
    date_info       date,
    decision        text,                 -- conforme | non_conforme
    motif           text,
    stade           text,                 -- MAT | SP | BAT | reception | ...
    texte           text,
    created_at      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE achat.qualite_decision IS 'Décisions qualité conforme/non-conforme issues des mails (Eric T) — non-Sylob (email-first).';

CREATE TABLE IF NOT EXISTS achat.transport_evenement (
    id              serial PRIMARY KEY,
    cle_idempotence text        NOT NULL UNIQUE,
    po_number       text,
    code_article    text,
    n_conteneur     text,
    thread_id       text,
    acteur          text,
    source          text,
    date_info       date,
    type            text,                 -- retard | imprevu | chgt_date
    champ_date      text,                 -- etd | eta | livraison
    ancienne_valeur date,
    nouvelle_valeur date,
    motif           text,
    texte           text,
    created_at      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE achat.transport_evenement IS 'Retards / imprévus / changements de dates transport (transitaire) — non-Sylob.';

CREATE TABLE IF NOT EXISTS achat.commerce_decision (
    id              serial PRIMARY KEY,
    cle_idempotence text        NOT NULL UNIQUE,
    po_number       text,
    code_article    text,
    n_conteneur     text,
    thread_id       text,
    acteur          text,
    source          text,
    date_info       date,
    type            text,                 -- prix_client | go_nogo | priorite | promo
    contenu         text,
    texte           text,
    created_at      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE achat.commerce_decision IS 'Arbitrages / décisions commerce (Eric, David) issus des mails — non-Sylob.';

CREATE TABLE IF NOT EXISTS achat.design_evenement (
    id              serial PRIMARY KEY,
    cle_idempotence text        NOT NULL UNIQUE,
    po_number       text,
    code_article    text,
    n_conteneur     text,
    thread_id       text,
    acteur          text,
    source          text,
    date_info       date,
    type            text,                 -- validation_boite | artwork | marquage | pantone
    statut          text,
    texte           text,
    created_at      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE achat.design_evenement IS 'Validations design (boîte, artwork, marquage, pantone — Clarisse) issues des mails — non-Sylob.';

-- Index de rattachement (lecture par PO / conteneur)
CREATE INDEX IF NOT EXISTS idx_qualite_decision_po    ON achat.qualite_decision   (po_number);
CREATE INDEX IF NOT EXISTS idx_transport_evenement_ct ON achat.transport_evenement(n_conteneur);
CREATE INDEX IF NOT EXISTS idx_transport_evenement_po ON achat.transport_evenement(po_number);
CREATE INDEX IF NOT EXISTS idx_commerce_decision_po   ON achat.commerce_decision  (po_number);
CREATE INDEX IF NOT EXISTS idx_design_evenement_po    ON achat.design_evenement   (po_number);

-- Si l'owner n'est pas platform_team, ouvrir les droits DML au rôle applicatif :
GRANT SELECT, INSERT, UPDATE ON
    achat.qualite_decision, achat.transport_evenement,
    achat.commerce_decision, achat.design_evenement
    TO platform_team;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA achat TO platform_team;

COMMIT;
