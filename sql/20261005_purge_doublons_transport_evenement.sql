-- =============================================================================
-- [PURGE] Doublons d'evenements ETA du conteneur MSMU3526021
-- Date : 05/10/2026, auteur Antho Bezille (accord ecrit en session le 05/10)
-- =============================================================================
-- Pourquoi : un PDF transitaire du 20/05, relu a chaque passage de l'ETL Gmail,
-- prenait l'heure du chargement comme date de transmission. Il a cree chaque
-- matin le meme evenement "eta : 2026-05-29 -> 2026-05-12". 9 lignes au total,
-- on garde la premiere (id 54, 10/08) et on supprime les 8 suivantes.
-- Cause corrigee par la branche fix/gmail-eta-date-transmission.
-- =============================================================================

BEGIN;

CREATE TABLE achat._archive_transport_evenement_20261005 AS
SELECT * FROM achat.transport_evenement
WHERE n_conteneur = 'MSMU3526021'
  AND champ_date = 'eta'
  AND nouvelle_valeur = DATE '2026-05-12'
  AND source LIKE 'gmail:20260520_%'
  AND id <> 54;

-- Garde-fou de volume : exactement 8 lignes attendues
DO $$
DECLARE n integer;
BEGIN
    SELECT COUNT(*) INTO n FROM achat._archive_transport_evenement_20261005;
    IF n <> 8 THEN
        RAISE EXCEPTION 'Volume inattendu : % lignes (attendu 8)', n;
    END IF;
END $$;

DELETE FROM achat.transport_evenement t
USING achat._archive_transport_evenement_20261005 a
WHERE t.id = a.id;

COMMIT;

-- Restauration :
-- INSERT INTO achat.transport_evenement SELECT * FROM achat._archive_transport_evenement_20261005;
