-- =============================================================================
-- FUSEAU -- Date de paiement saisissable par les Achats
-- Redige le 28/07/2026 (demande Marlene)
-- =============================================================================
-- BESOIN
-- La colonne Paiement (Paye / A payer / A payer en retard) est deduite de
-- achat.commande.date_paiement, alimentee par l'ETL depuis IMPORT 2026.xlsx.
-- Marlene doit pouvoir corriger ou anticiper un paiement directement dans
-- l'application, sans attendre le prochain run de nuit.
--
-- CONTRAINTE
-- achat.commande est rechargee en full-refresh (TRUNCATE + INSERT). Une saisie
-- ecrite directement dedans serait perdue la nuit suivante. On applique donc
-- le pattern deja en place pour l'ETD et le commentaire : la saisie va dans
-- achat.commande_annotation, jointe par cle metier, et la vue arbitre.
--
-- ARBITRAGE : la saisie utilisateur PRIME sur la donnee ETL. Si Marlene
-- renseigne une date, c'est qu'elle sait quelque chose que le fichier ignore
-- encore. Pour revenir a la valeur ETL, il suffit d'effacer la saisie (NULL).
--
-- Script idempotent : rejouable sans effet de bord.
-- =============================================================================

ALTER TABLE achat.commande_annotation
    ADD COLUMN IF NOT EXISTS date_paiement DATE;

COMMENT ON COLUMN achat.commande_annotation.date_paiement IS
    'Date de paiement saisie par les Achats. Prime sur achat.commande.date_paiement dans achat.v_previsionnel. NULL = on retombe sur la valeur ETL.';

-- -----------------------------------------------------------------------------
-- Vue previsionnelle : meme definition qu'avant, a ceci pres que la date de
-- paiement effective devient COALESCE(saisie utilisateur, valeur ETL). Les
-- trois axes qui en dependent (est_a_payer, est_a_payer_en_retard, et le
-- montant a payer de l'echeancier) suivent automatiquement.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW achat.v_previsionnel AS
SELECT c.id,
       c.po_number,
       c.code_article,
       c.fournisseur,
       c.designation,
       c.statut,
       COALESCE(c.etd_reel, c.etd_confirme)                  AS etd_eff,
       c.eta,
       c.date_livraison,
       COALESCE(a.date_paiement, c.date_paiement)            AS date_paiement,
       CASE
           WHEN c.code_article IS NULL THEN COALESCE(c.total_prix, 0::numeric)
           ELSE COALESCE(c.prix_unitaire * c.quantite::numeric, 0::numeric)
       END                                                   AS montant,
       c.statut <> 'Annulée'::text                           AS est_achete,
       COALESCE(a.date_paiement, c.date_paiement) IS NULL
           AND c.statut <> 'Annulée'::text                   AS est_a_payer,
       q.date_inspection IS NOT NULL
           AND (c.statut <> ALL (ARRAY['Livrée'::text, 'Annulée'::text]))
                                                             AS est_en_inspection,
       c.statut = 'En cours de livraison'::text
           OR COALESCE(c.etd_reel, c.etd_confirme) <= CURRENT_DATE
              AND c.date_livraison IS NULL
              AND (c.statut <> ALL (ARRAY['Livrée'::text, 'Annulée'::text]))
                                                             AS est_parti,
       COALESCE(c.etd_reel, c.etd_confirme) < CURRENT_DATE
           AND c.date_livraison IS NULL
           AND (c.statut <> ALL (ARRAY['Livrée'::text, 'Annulée'::text]))
                                                             AS est_en_retard,
       c.statut = 'Livrée'::text                             AS est_livre,
       to_char(COALESCE(c.etd_reel, c.etd_confirme)::timestamp with time zone,
               'YYYY-MM'::text)                              AS mois_etd,
       COALESCE(a.date_paiement, c.date_paiement) IS NULL
           AND COALESCE(c.etd_reel, c.etd_confirme) < CURRENT_DATE
           AND c.statut <> 'Annulée'::text                   AS est_a_payer_en_retard,
       -- Colonne ajoutee EN FIN de vue : CREATE OR REPLACE VIEW n'autorise que
       -- l'ajout de colonnes a la fin, jamais l'insertion au milieu.
       -- Tracabilite pour l'UI : distinguer une date saisie a la main d'une
       -- date remontee par l'ETL, afin d'afficher un marqueur.
       (a.date_paiement IS NOT NULL)                         AS paiement_saisi_manuellement
FROM achat.commande c
LEFT JOIN achat.qualite q
       ON q.po_number = c.po_number AND q.code_article = c.code_article
LEFT JOIN achat.commande_annotation a
       ON a.po_number = c.po_number AND a.code_article = c.code_article;

COMMENT ON VIEW achat.v_previsionnel IS
    'Axes previsionnels orthogonaux (a payer / parti / livre / en retard / en inspection). Depuis le 28/07/2026, la date de paiement effective est COALESCE(saisie Achats, valeur ETL).';
