-- =============================================================================
-- [QUALITE] Dedoublonnage et normalisation de achat.qualite_decision
-- Date : 08/10/2026, auteur Antho Bezille. NON EXECUTE : a lancer par Antho.
-- =============================================================================
-- Pourquoi : la tache Cowork alimente achat.qualite_decision via
-- src/scripts/gmail/load_evenements.py. La cle d'idempotence variait pour une
-- meme decision (constat du poste metier, 06/10/2026) :
--   A. PO ecrit "00187324" ou "187324" selon le mail ;
--   B. ancien format de cle anterieur au 28/07 (5 segments) ;
--   C. n_conteneur / champ_date / nouvelle_valeur remplis au hasard sur une
--      decision qualite, et entres dans la cle ;
--   D. meme fil et meme PO : une ligne "tout le PO" puis une ligne par article,
--      stade ecrit "FRI" ou "inspection".
-- Le stade n'etait pas dans la cle : "MAT conforme" puis "SP conforme" sur un
-- meme PO dans un meme fil se marchaient dessus. Le code corrige (meme branche)
-- calcule desormais la cle qualite ainsi :
--     thread_id|qualite|decision|po_number|code_article|stade
-- avec PO sur 8 chiffres, decision en minuscules et stade canonique.
--
-- Ce script :
--   1. calcule l'etat cible de chaque ligne (table temporaire _cible) ;
--   2. archive les lignes supprimees ET l'etat d'origine des lignes modifiees
--      dans achat._archive_qualite_decision_doublons_20261008 ;
--   3. supprime les doublons (on garde le plus petit id) groupes par
--      (thread_id, PO normalise, code_article, decision, stade normalise) ;
--   4. supprime les lignes "tout le PO" (code_article NULL) quand le meme fil
--      porte des lignes par article pour le meme PO, stade et decision (cause D) ;
--   5. normalise po_number, stade et decision, et requalifie les "conforme"
--      dont le motif ou le texte parle d'un rapport DEKRA "Pending" ;
--   6. recalcule cle_idempotence avec la MEME formule que _cle() en Python,
--      sauf les cles de reservation "dekra_resa|..." fournies par le prompt.
--
-- IMPORTANT : la formule SQL de normalisation et de cle (CTE "norm" et colonne
-- cle_n ci-dessous) DOIT rester identique a normaliser_po(), normaliser_stade()
-- et _cle() de load_evenements.py. Si elles divergent, le prochain passage de la
-- tache Cowork sur un fil deja charge produit une cle differente, donc un
-- nouveau doublon.
--
-- Requalification (decision 'conforme' + 'pending' dans motif ou texte) :
--   - 'conforme_sous_reserve' si le texte mentionne OK SHIPMENT, expedition
--     validee ou sous reserve (DEKRA Pending + accord d'expedition TB) ;
--   - 'en_attente' sinon (Pending sans decision TB).
--   Les stades MAT, SP et BAT sont exclus : ids 617 et 618 (PO 00184684) sont
--   des echantillons SP approuves dont le texte cite au passage une FRI DEKRA
--   Pending ; la decision SP elle-meme est bien "conforme".
--
-- Mesures en lecture seule le 08/10/2026 (383 lignes dans la table) :
--   - lignes supprimees : 64 = 56 doublons + 8 lignes "tout le PO" (cause D) ;
--   - lignes restantes : 319, toutes avec une cle recalculee distincte
--     (319 cles distinctes, 0 collision avec une cle existante d'une autre ligne
--     restante, donc pas de violation transitoire de l'index UNIQUE) ;
--   - decisions requalifiees : 8 (ids 346, 355, 966 a 971), toutes en
--     'conforme_sous_reserve' ; l'id 900 (meme fil que 966 a 971, niveau PO)
--     part en suppression cause D ;
--   - PO renormalises sur 8 chiffres : 15 ; stades FRI -> inspection : 8 ;
--   - cles recalculees : 318 sur 319.
-- Garde-fou : le bloc DO leve si les volumes sortent des plages ci-dessous
-- (marge pour les mails charges entre la mesure et l'execution).
--
-- Ordre de deploiement : deployer d'abord le code de load_evenements.py sur le
-- poste, PUIS executer ce script. Dans l'autre ordre, l'ancien code recree des
-- cles a l'ancien format au prochain passage de la tache Cowork.
--
-- Restauration (dans une transaction) :
--   INSERT INTO achat.qualite_decision (id, cle_idempotence, po_number, code_article,
--          n_conteneur, thread_id, acteur, source, date_info, decision, motif, stade,
--          texte, created_at)
--   SELECT id, cle_idempotence, po_number, code_article, n_conteneur, thread_id,
--          acteur, source, date_info, decision, motif, stade, texte, created_at
--   FROM achat._archive_qualite_decision_doublons_20261008 WHERE action = 'supprimee';
--   UPDATE achat.qualite_decision d
--   SET cle_idempotence = a.cle_idempotence, po_number = a.po_number,
--       stade = a.stade, decision = a.decision, code_article = a.code_article
--   FROM achat._archive_qualite_decision_doublons_20261008 a
--   WHERE a.action = 'modifiee' AND a.id = d.id;
-- (restaurer apres avoir repasse l'ancien code, sinon les cles divergent de nouveau)
-- =============================================================================

BEGIN;

-- Bloque les insertions concurrentes de la tache Cowork le temps du traitement.
LOCK TABLE achat.qualite_decision IN SHARE ROW EXCLUSIVE MODE;

CREATE TEMP TABLE _cible ON COMMIT DROP AS
WITH norm AS (
    SELECT d.id, d.thread_id, d.cle_idempotence, d.po_number, d.code_article,
           d.stade, d.decision, d.motif, d.texte,
           -- = normaliser_po() : chiffres seuls -> 8 chiffres (sans tronquer un
           -- PO plus long, comme str.zfill), sinon simple nettoyage.
           CASE WHEN NULLIF(btrim(d.po_number), '') IS NULL THEN NULL
                WHEN btrim(d.po_number) ~ '^[0-9]+$'
                    THEN lpad(btrim(d.po_number), GREATEST(8, length(btrim(d.po_number))), '0')
                ELSE btrim(d.po_number) END AS po_n,
           NULLIF(btrim(d.code_article), '') AS art_n,
           -- = normaliser_stade() : STADES_CANONIQUES, sinon minuscules.
           CASE upper(btrim(d.stade))
                WHEN 'MAT' THEN 'MAT' WHEN 'SP' THEN 'SP' WHEN 'BAT' THEN 'BAT'
                WHEN 'FRI' THEN 'inspection' WHEN 'INSPECTION' THEN 'inspection'
                WHEN 'RECEP' THEN 'reception' WHEN 'RECEPTION' THEN 'reception'
                ELSE NULLIF(lower(btrim(d.stade)), '') END AS stade_n,
           NULLIF(lower(btrim(d.decision)), '') AS dec_n
    FROM achat.qualite_decision d
), requal AS (
    SELECT n.*,
           CASE WHEN n.dec_n = 'conforme'
                 AND (n.motif ILIKE '%pending%' OR n.texte ILIKE '%pending%')
                 AND COALESCE(n.stade_n, '') NOT IN ('MAT', 'SP', 'BAT')
                THEN CASE WHEN COALESCE(n.motif, '') || ' ' || COALESCE(n.texte, '')
                               ~* '(ok[ -]?shipment|exp.dition valid.e|sous r.serve)'
                          THEN 'conforme_sous_reserve' ELSE 'en_attente' END
                ELSE n.dec_n END AS dec_f
    FROM norm n
), rang AS (
    SELECT r.*,
           ROW_NUMBER() OVER (PARTITION BY r.thread_id, r.po_n, COALESCE(r.art_n, ''),
                                           r.dec_f, r.stade_n
                              ORDER BY r.id) AS rn
    FROM requal r
    WHERE r.cle_idempotence NOT LIKE 'dekra\_resa|%'
), a_supprimer AS (
    SELECT id, 'doublon' AS cause FROM rang WHERE rn > 1
    UNION ALL
    SELECT g.id, 'niveau_po' FROM rang g
    WHERE g.rn = 1 AND g.art_n IS NULL AND g.po_n IS NOT NULL
      AND EXISTS (SELECT 1 FROM rang a
                  WHERE a.rn = 1 AND a.art_n IS NOT NULL
                    AND a.thread_id = g.thread_id AND a.po_n = g.po_n
                    AND a.dec_f IS NOT DISTINCT FROM g.dec_f
                    AND a.stade_n IS NOT DISTINCT FROM g.stade_n)
)
SELECT r.id, r.po_n, r.art_n, r.stade_n, r.dec_f, r.dec_n,
       s.cause,
       -- = _cle() pour le domaine qualite :
       --   thread_id|qualite|decision|po_number|code_article|stade
       CASE WHEN r.cle_idempotence LIKE 'dekra\_resa|%' THEN r.cle_idempotence
            ELSE concat_ws('|', COALESCE(r.thread_id, '?'), 'qualite', COALESCE(r.dec_f, ''),
                           COALESCE(r.po_n, ''), COALESCE(r.art_n, ''), COALESCE(r.stade_n, ''))
       END AS cle_n
FROM requal r
LEFT JOIN a_supprimer s ON s.id = r.id;

CREATE TABLE achat._archive_qualite_decision_doublons_20261008 AS
SELECT d.*,
       CASE WHEN c.cause IS NOT NULL THEN 'supprimee' ELSE 'modifiee' END AS action,
       c.cause,
       now() AS archive_le
FROM achat.qualite_decision d
JOIN _cible c ON c.id = d.id
WHERE c.cause IS NOT NULL
   OR d.cle_idempotence IS DISTINCT FROM c.cle_n
   OR d.po_number IS DISTINCT FROM c.po_n
   OR d.code_article IS DISTINCT FROM c.art_n
   OR d.stade IS DISTINCT FROM c.stade_n
   OR d.decision IS DISTINCT FROM c.dec_f;

DO $$
DECLARE
    n_supprimees integer;
    n_requalifiees integer;
    n_restantes integer;
    n_cles integer;
BEGIN
    SELECT count(*) INTO n_supprimees FROM _cible WHERE cause IS NOT NULL;
    SELECT count(*) INTO n_requalifiees FROM _cible
    WHERE cause IS NULL AND dec_n = 'conforme' AND dec_f IN ('conforme_sous_reserve', 'en_attente');
    SELECT count(*), count(DISTINCT cle_n) INTO n_restantes, n_cles FROM _cible WHERE cause IS NULL;

    -- Mesure du 08/10 : 64 supprimees, 8 requalifiees.
    IF n_supprimees NOT BETWEEN 60 AND 90 THEN
        RAISE EXCEPTION '[ECHEC] % ligne(s) a supprimer, plage attendue 60 a 90 (mesure du 08/10 : 64)', n_supprimees;
    END IF;
    IF n_requalifiees NOT BETWEEN 6 AND 20 THEN
        RAISE EXCEPTION '[ECHEC] % ligne(s) a requalifier, plage attendue 6 a 20 (mesure du 08/10 : 8)', n_requalifiees;
    END IF;
    IF n_restantes <> n_cles THEN
        RAISE EXCEPTION '[ECHEC] cles recalculees non uniques : % lignes, % cles', n_restantes, n_cles;
    END IF;
    RAISE NOTICE '[INFO] a supprimer=%, a requalifier=%, restantes=%', n_supprimees, n_requalifiees, n_restantes;
END $$;

DELETE FROM achat.qualite_decision d
USING _cible c
WHERE c.id = d.id AND c.cause IS NOT NULL;

UPDATE achat.qualite_decision d
SET po_number = c.po_n,
    code_article = c.art_n,
    stade = c.stade_n,
    decision = c.dec_f,
    cle_idempotence = c.cle_n
FROM _cible c
WHERE c.id = d.id AND c.cause IS NULL
  AND (d.cle_idempotence, d.po_number, d.code_article, d.stade, d.decision)
      IS DISTINCT FROM (c.cle_n, c.po_n, c.art_n, c.stade_n, c.dec_f);

-- Controle final : aucune paire de lignes ne doit plus partager
-- (thread, PO, article, decision, stade).
DO $$
DECLARE
    n_groupes integer;
BEGIN
    SELECT count(*) INTO n_groupes FROM (
        SELECT 1 FROM achat.qualite_decision
        WHERE cle_idempotence NOT LIKE 'dekra\_resa|%'
        GROUP BY thread_id, po_number, COALESCE(code_article, ''), decision, stade
        HAVING count(*) > 1
    ) x;
    IF n_groupes > 0 THEN
        RAISE EXCEPTION '[ECHEC] % groupe(s) encore en doublon apres traitement', n_groupes;
    END IF;
END $$;

COMMIT;
