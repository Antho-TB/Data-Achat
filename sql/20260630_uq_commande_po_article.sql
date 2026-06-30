-- =============================================================================
-- FUSEAU — Contrainte UNIQUE (po_number, code_article) sur achat.commande
-- 2026-06-30 — débloque l'UPSERT du pipeline Gmail (ON CONFLICT)
-- À exécuter UNE FOIS depuis le poste Antho (VPN Stormshield + compte admin/owner
-- du schéma achat). platform_team n'a PAS le droit d'ALTER TABLE.
--
-- Ordre : lancer d'abord l'ÉTAPE 1 (diagnostic, lecture seule) et VÉRIFIER le
-- résultat. Ne lancer l'ÉTAPE 2 (transaction) que si le diagnostic est compris.
--
-- Note NULL : PostgreSQL traite les NULL comme DISTINCTS par défaut (NULLS
-- DISTINCT). Les lignes de frais à code_article NULL ne sont donc NI dédoublonnées
-- NI bloquées par la contrainte — comportement voulu (plusieurs frais par PO).
-- =============================================================================


-- -----------------------------------------------------------------------------
-- ÉTAPE 1 — DIAGNOSTIC (lecture seule) : y a-t-il des doublons à purger ?
-- Exécuter SEULE, lire le résultat avant d'aller plus loin.
-- -----------------------------------------------------------------------------
SELECT po_number, code_article, COUNT(*) AS nb_doublons
FROM achat.commande
WHERE code_article IS NOT NULL
  AND po_number IS NOT NULL
GROUP BY po_number, code_article
HAVING COUNT(*) > 1
ORDER BY nb_doublons DESC, po_number;


-- -----------------------------------------------------------------------------
-- ÉTAPE 2 — DÉDOUBLONNAGE + CONTRAINTE (transactionnel, idempotent)
-- Décommenter et exécuter d'un bloc APRÈS revue de l'étape 1.
-- Garde la ligne de plus grand ctid par couple (po_number, code_article).
-- ⚠ ctid = ordre physique, pas chronologique : si une colonne de date fiable
--    existe (updated_at), préférer un tri par cette colonne. À adapter au DDL réel.
-- -----------------------------------------------------------------------------
-- BEGIN;
--
--     -- 2.1 Purge des doublons (conserve un enregistrement par clé métier)
--     DELETE FROM achat.commande a
--     USING achat.commande b
--     WHERE a.code_article IS NOT NULL
--       AND a.po_number   IS NOT NULL
--       AND a.po_number   = b.po_number
--       AND a.code_article = b.code_article
--       AND a.ctid < b.ctid;
--
--     -- 2.2 Création de la contrainte (idempotent : ne rejoue pas si déjà là)
--     DO $$
--     BEGIN
--         IF NOT EXISTS (
--             SELECT 1 FROM pg_constraint WHERE conname = 'uq_commande_po_article'
--         ) THEN
--             ALTER TABLE achat.commande
--                 ADD CONSTRAINT uq_commande_po_article UNIQUE (po_number, code_article);
--         END IF;
--     END $$;
--
-- COMMIT;


-- -----------------------------------------------------------------------------
-- ÉTAPE 3 — VÉRIFICATION (attendu : la contrainte existe, plus aucun doublon)
-- -----------------------------------------------------------------------------
-- SELECT conname, contype, pg_get_constraintdef(oid) AS def
-- FROM pg_constraint
-- WHERE conrelid = 'achat.commande'::regclass
--   AND conname = 'uq_commande_po_article';
