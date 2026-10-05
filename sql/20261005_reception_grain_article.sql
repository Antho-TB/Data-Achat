-- =============================================================================
-- [MIGRATION] Receptions Sylob : passage du grain PO au grain (PO, article)
-- Date : 05/10/2026, auteur Antho Bezille
-- =============================================================================
-- Pourquoi : jusqu'au 05/10, enrich_reception_sylob deposait une date de
-- reception par PO (code_article = ''), lue dans public.receptions_detaillees2,
-- figee depuis le 04/08. apply_enrichissement marquait alors "Livree" TOUTES
-- les lignes d'un PO des qu'un seul article etait recu.
-- Le module ecrit desormais au grain article, depuis le DWH Sylob. Les 98 lignes
-- PO-level de cette source doivent cesser de s'appliquer, sinon elles continuent
-- de marquer livrees des lignes qui ne le sont pas.
--
-- Choix : on vide date_reception_sylob plutot que de supprimer les lignes. Une
-- NCR ou un resultat d'inspection pourrait un jour vivre sur la meme ligne
-- PO-level, et on ne detruit rien.
-- achat.commande est rechargee chaque nuit : le prochain ETL reconstruit les
-- dates de reception a partir du grain article, sans autre intervention.
--
-- Prerequis : le nouveau enrich_reception_sylob deploye sur le poste de Marlene.
-- Execution : psql en compte nominal, apres accord ecrit d'Antho.
-- =============================================================================

BEGIN;

-- Archive avant modification (restauration en bas de fichier)
CREATE TABLE achat._archive_enrich_reception_po_20261005 AS
SELECT * FROM achat.commande_enrichissement
WHERE source = 'enrich_reception_sylob' AND code_article = '';

-- Garde-fou de volume : 98 lignes attendues au 05/10/2026
DO $$
DECLARE n integer;
BEGIN
    SELECT COUNT(*) INTO n FROM achat._archive_enrich_reception_po_20261005;
    IF n = 0 OR n > 150 THEN
        RAISE EXCEPTION 'Volume inattendu : % lignes PO-level (attendu environ 98)', n;
    END IF;
END $$;

UPDATE achat.commande_enrichissement
SET date_reception_sylob = NULL,
    maj_le               = NOW()
WHERE source = 'enrich_reception_sylob'
  AND code_article = ''
  AND date_reception_sylob IS NOT NULL;

COMMIT;

-- Restauration :
-- UPDATE achat.commande_enrichissement e
-- SET date_reception_sylob = a.date_reception_sylob, maj_le = a.maj_le
-- FROM achat._archive_enrich_reception_po_20261005 a
-- WHERE e.po_number = a.po_number AND e.code_article = a.code_article;
