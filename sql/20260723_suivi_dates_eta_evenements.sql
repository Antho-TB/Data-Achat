-- =============================================================================
-- FUSEAU / achat.* — Suivi des changements de dates transport (ETA / livraison)
-- =============================================================================
-- Migration 2026-07-23. À exécuter avec l'identité OWNER/ADMIN (poste Antho).
-- Suite à docs/20260722_FUSEAU_Spec_SuiviDatesETA_v1.md, décisions arbitrées le 23/07 :
--   - Sémantique dates confirmée telle quelle (etd_reel=départ port, eta=arrivée port,
--     date_livraison=arrivée entrepôt TB/réception).
--   - Horodatage fichier maritime = date du fichier (mtime), pas date d'ingestion ETL.
--   - Échelle couleur : 1=orange, 2=rouge, 3+=violet (jamais remis à zéro).
--   - ETD non historisé (seulement ETA + livraison, périmètre initial).
--
-- Réutilise achat.transport_evenement (créée 22/07, sql/20260722_tables_evenements_metier.sql,
-- commentaire "Absorbe le besoin ot_transport_date_evenement de la spec ETA") plutôt que
-- de créer une nouvelle table -- une seule table d'événements transport pour les 2 sources
-- (mail via load_evenements.py, fichier maritime via load_ot_gmail.py).
--
-- Colonnes ajoutées à ot_transport : mémorisent la date de transmission qui a fixé la
-- valeur courante de chaque champ, pour appliquer la préséance chronologique ("la valeur
-- la plus récemment TRANSMISE gagne" -- pas "le dernier load exécuté gagne", cf. spec §4).
-- =============================================================================

BEGIN;

ALTER TABLE achat.ot_transport
    ADD COLUMN IF NOT EXISTS eta_maj_le            TIMESTAMP,
    ADD COLUMN IF NOT EXISTS date_livraison_maj_le  TIMESTAMP;

COMMENT ON COLUMN achat.ot_transport.eta_maj_le IS
    'Date de transmission (date_transmission) de la source qui a fixé eta -- sert a refuser une transmission plus ancienne (preseance chronologique, spec ETA §4).';
COMMENT ON COLUMN achat.ot_transport.date_livraison_maj_le IS
    'Idem eta_maj_le, pour date_livraison.';

-- Vue de suivi : nb de changements cumulés (jamais remis à zéro) + couleur d'alerte,
-- par conteneur, dérivée de achat.transport_evenement (type='chgt_date', domaine transport).
CREATE OR REPLACE VIEW achat.v_ot_transport_suivi AS
WITH chg AS (
    SELECT n_conteneur, champ_date,
           COUNT(*)            AS nb_changements,
           MAX(date_info)      AS date_dernier_changement
    FROM achat.transport_evenement
    WHERE type = 'chgt_date'
      AND champ_date IN ('eta', 'date_livraison')
      AND nouvelle_valeur IS DISTINCT FROM ancienne_valeur
    GROUP BY n_conteneur, champ_date
)
SELECT
    t.n_conteneur,
    t.eta,
    t.date_livraison,
    COALESCE(eta_c.nb_changements, 0)             AS nb_changements_eta,
    COALESCE(liv_c.nb_changements, 0)             AS nb_changements_livraison,
    eta_c.date_dernier_changement                 AS date_dernier_changement_eta,
    liv_c.date_dernier_changement                 AS date_dernier_changement_livraison,
    CASE
        WHEN COALESCE(eta_c.nb_changements, 0) = 0 THEN NULL
        WHEN eta_c.nb_changements = 1 THEN 'orange'
        WHEN eta_c.nb_changements = 2 THEN 'rouge'
        ELSE 'violet'
    END                                            AS couleur_eta,
    CASE
        WHEN COALESCE(liv_c.nb_changements, 0) = 0 THEN NULL
        WHEN liv_c.nb_changements = 1 THEN 'orange'
        WHEN liv_c.nb_changements = 2 THEN 'rouge'
        ELSE 'violet'
    END                                            AS couleur_livraison
FROM achat.ot_transport t
LEFT JOIN chg eta_c ON eta_c.n_conteneur = t.n_conteneur AND eta_c.champ_date = 'eta'
LEFT JOIN chg liv_c ON liv_c.n_conteneur = t.n_conteneur AND liv_c.champ_date = 'date_livraison';

COMMENT ON VIEW achat.v_ot_transport_suivi IS
    'Indicateurs de suivi ETA/livraison par conteneur (nb changements cumulés + couleur alerte 1=orange/2=rouge/3+=violet) -- spec 20260722_FUSEAU_Spec_SuiviDatesETA_v1.md.';

GRANT SELECT ON achat.v_ot_transport_suivi TO platform_team;

COMMIT;
