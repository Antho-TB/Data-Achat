-- =============================================================================
-- FUSEAU -- Purge des numeros de BL enregistres comme numeros de conteneur
-- Redige le 28/07/2026, sur retour d'Andrea, accord explicite d'Antho
-- =============================================================================
-- CONSTAT
-- 27 lignes de achat.ot_transport sur 173 portent un numero de BL du transitaire
-- en guise de numero de conteneur : SZSE2604053, SZAE2601690, COMP0600002...
-- Elles proviennent toutes du pipeline Gmail, qui lisait des noms de fichiers
-- du type "BL-SZSE2604053.PDF" avec une expression reguliere incapable de
-- distinguer les deux references : un BL et un conteneur ont la meme forme
-- apparente, 4 lettres suivies de 7 chiffres.
--
-- La norme ISO 6346 impose que la 4e lettre soit le code de categorie, qui vaut
-- U (conteneur de marchandises), J (equipement detachable) ou Z (chassis).
-- C'est le seul discriminant fiable, et il est desormais applique dans
-- parse_bl.py, transform_maritime.py et parse_email_eta.py (commit dca1829).
-- Ce script traite le stock deja en base, que le correctif ne peut pas defaire.
--
-- CE QU'ON PERD : presque rien. Sur ces 27 lignes, 1 seule porte une ETA, 1 un
-- ETD, aucune une date de livraison ni un nom de navire. Les 14 valeurs de n_bl
-- presentes sont elles-memes du bruit ("ACKTRAY", "ATTACH", "PO00151554").
--
-- SANS EFFET DE BORD : verifie le 28/07, aucune ligne de achat.commande ne
-- reference ces numeros. Aucune commande ne sera donc orpheline.
--
-- NE SONT PAS CONCERNEES : les 9 lignes portant une reference non normalisee
-- issue du fichier IMPORT (numeros de suivi DHL, "TK6433", "CA457"). Ce sont
-- des expeditions AERIENNES, qui n'ont legitimement pas de conteneur maritime.
-- Elles restent en base, c'est de la donnee metier valide.
--
-- REVERSIBLE : les lignes sont copiees dans une table d'archive avant
-- suppression. Pour revenir en arriere :
--   INSERT INTO achat.ot_transport SELECT * FROM achat._archive_faux_conteneurs_20260728;
-- =============================================================================

BEGIN;

-- 1. Archive integrale avant suppression.
DROP TABLE IF EXISTS achat._archive_faux_conteneurs_20260728;

CREATE TABLE achat._archive_faux_conteneurs_20260728 AS
SELECT * FROM achat.ot_transport
WHERE n_conteneur ~ '^[A-Z]{4}[0-9]{7}$'
  AND n_conteneur !~ '^[A-Z]{3}[UJZ][0-9]{7}$';

COMMENT ON TABLE achat._archive_faux_conteneurs_20260728 IS
    'Sauvegarde des lignes ot_transport dont le n_conteneur etait en realite un numero de BL (purge du 28/07/2026). Supprimable une fois la correction validee en exploitation.';

-- 2. Garde-fou : on refuse de continuer si le volume ne correspond pas a ce qui
--    a ete constate. Une purge silencieuse de 170 lignes au lieu de 27 serait
--    une catastrophe ; mieux vaut echouer et rouvrir le dossier.
DO $$
DECLARE
    nb INTEGER;
BEGIN
    SELECT count(*) INTO nb FROM achat._archive_faux_conteneurs_20260728;
    IF nb = 0 THEN
        RAISE EXCEPTION 'Aucune ligne a purger : le correctif a-t-il deja ete applique ?';
    END IF;
    IF nb > 40 THEN
        RAISE EXCEPTION 'Volume anormal (% lignes, attendu ~27). Purge annulee, verifier le motif.', nb;
    END IF;
    RAISE NOTICE 'Archive : % ligne(s) sauvegardee(s) avant purge.', nb;
END $$;

-- 3. Suppression.
DELETE FROM achat.ot_transport
WHERE n_conteneur IN (SELECT n_conteneur FROM achat._archive_faux_conteneurs_20260728);

COMMIT;

-- =============================================================================
-- VERIFICATION
-- =============================================================================
-- Doit renvoyer 0 faux conteneur, et le total doit avoir baisse d'autant :
--
-- SELECT count(*) FILTER (WHERE n_conteneur ~ '^[A-Z]{3}[UJZ][0-9]{7}$') AS vrais,
--        count(*) FILTER (WHERE n_conteneur ~ '^[A-Z]{4}[0-9]{7}$'
--                     AND n_conteneur !~ '^[A-Z]{3}[UJZ][0-9]{7}$')      AS faux,
--        count(*)                                                        AS total
-- FROM achat.ot_transport;
