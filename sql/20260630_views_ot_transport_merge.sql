-- =============================================================================
-- Pattern A -- Gmail/maritime tracking decouple de achat.commande (full-refresh)
-- =============================================================================
-- Les ETD reels / ETA niveau expedition vivent dans achat.ot_transport
-- (PK n_conteneur, upsert, survit au full-refresh de achat.commande).
-- Les vues de lecture fusionnent commande + ot_transport, BL/maritime PRIORITAIRE
-- (decision source de verite 30/06) : COALESCE(ot.*, commande.*).
--
-- Reversible : CREATE OR REPLACE, jeu de colonnes inchange (noms/ordre/types).
-- Idempotent.
-- =============================================================================

CREATE OR REPLACE VIEW achat.v_previsionnel AS
SELECT c.id,
    c.po_number,
    c.code_article,
    c.fournisseur,
    c.designation,
    c.statut,
    COALESCE(ot.etd_reel, c.etd_reel, c.etd_confirme) AS etd_eff,
    COALESCE(ot.eta, c.eta) AS eta,
    c.date_livraison,
    c.date_paiement,
    CASE
        WHEN c.code_article IS NULL THEN COALESCE(c.total_prix, 0::numeric)
        ELSE COALESCE(c.prix_unitaire * c.quantite::numeric, 0::numeric)
    END AS montant,
    c.statut <> 'Annulée'::text AS est_achete,
    c.date_paiement IS NULL AND c.statut <> 'Annulée'::text AS est_a_payer,
    q.date_inspection IS NOT NULL AND (c.statut <> ALL (ARRAY['Livrée'::text, 'Annulée'::text])) AS est_en_inspection,
    c.statut = 'En cours de livraison'::text OR COALESCE(ot.etd_reel, c.etd_reel, c.etd_confirme) <= CURRENT_DATE AND c.date_livraison IS NULL AND (c.statut <> ALL (ARRAY['Livrée'::text, 'Annulée'::text])) AS est_parti,
    COALESCE(ot.etd_reel, c.etd_reel, c.etd_confirme) < CURRENT_DATE AND c.date_livraison IS NULL AND (c.statut <> ALL (ARRAY['Livrée'::text, 'Annulée'::text])) AS est_en_retard,
    c.statut = 'Livrée'::text AS est_livre,
    to_char(COALESCE(ot.etd_reel, c.etd_reel, c.etd_confirme)::timestamp with time zone, 'YYYY-MM'::text) AS mois_etd,
    c.date_paiement IS NULL AND COALESCE(ot.etd_reel, c.etd_reel, c.etd_confirme) < CURRENT_DATE AND c.statut <> 'Annulée'::text AS est_a_payer_en_retard
   FROM achat.commande c
     LEFT JOIN achat.qualite q ON q.po_number = c.po_number AND q.code_article = c.code_article
     LEFT JOIN achat.ot_transport ot ON ot.n_conteneur = c.n_conteneur;

CREATE OR REPLACE VIEW achat.v_retard_article AS
SELECT c.code_article,
    c.fournisseur,
    max(COALESCE(ot.etd_reel, c.etd_reel, c.etd_confirme)) AS date_etd,
    CASE
        WHEN bool_and(c.statut = ANY (ARRAY['Livrée'::text, 'Annulée'::text])) THEN max(c.date_livraison) - max(COALESCE(ot.etd_reel, c.etd_reel, c.etd_confirme))
        WHEN max(COALESCE(ot.etd_reel, c.etd_reel, c.etd_confirme)) < CURRENT_DATE THEN CURRENT_DATE - max(COALESCE(ot.etd_reel, c.etd_reel, c.etd_confirme))
        ELSE NULL::integer
    END AS jours_retard,
    CASE
        WHEN bool_and(c.statut = ANY (ARRAY['Livrée'::text, 'Annulée'::text])) THEN 'CLOTUREE'::text
        WHEN max(COALESCE(ot.etd_reel, c.etd_reel, c.etd_confirme)) < CURRENT_DATE THEN 'EN RETARD'::text
        WHEN max(COALESCE(ot.etd_reel, c.etd_reel, c.etd_confirme)) IS NULL THEN 'INCONNU'::text
        ELSE 'DANS LES DELAIS'::text
    END AS statut_retard
   FROM achat.commande c
     LEFT JOIN achat.ot_transport ot ON ot.n_conteneur = c.n_conteneur
  GROUP BY c.code_article, c.fournisseur;
