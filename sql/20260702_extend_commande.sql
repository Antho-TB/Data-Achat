-- =============================================================================
-- Item #5 plan de captation -- extension achat.commande (colonnes IMPORT non mappees)
-- =============================================================================
-- Audit du 02/07 (dump complet des 46 colonnes "IMPORT 2025") a identifie des
-- colonnes source presentes dans le fichier mais jamais lues par transform_commande.
-- Cette migration les ajoute. Full-refresh (TRUNCATE+INSERT) -> pas de backfill
-- necessaire, le prochain run du pipeline les peuple.
--
-- Bug corrige au passage (cf. transform.py) : le champ `transitaire` etait
-- rempli depuis la colonne Excel "Transport" (= NOM DU NAVIRE, ex. "CMA CGM
-- ALEXANDER VON HUMBOLDT") au lieu de la colonne "Transitaire" (= transporteur
-- reel, ex. QUALITAIRSEA/SEALOGIS/COSMOS/DHL). Verifie par comptage de valeurs
-- distinctes sur IMPORT 2025 (02/07) : les deux colonnes sont bien distinctes
-- et non-redondantes. `nom_navire` recueille desormais la valeur "Transport".
-- =============================================================================

ALTER TABLE achat.commande
  ADD COLUMN IF NOT EXISTS op_client_appro      TEXT,     -- ex. "Appro 251217" -- campagne appro / OP
  ADD COLUMN IF NOT EXISTS alerte               TEXT,     -- libre : "Nvx produit", "Réunion OP", "TOP CHEF"...
  ADD COLUMN IF NOT EXISTS nb_mois_livraison     NUMERIC,  -- "Nombre de mois (de la commande à la livraison)"
  ADD COLUMN IF NOT EXISTS prix_reference        NUMERIC,  -- "Prix / référence" (distinct de PU = prix unitaire commande)
  ADD COLUMN IF NOT EXISTS total_prix_facture    NUMERIC,  -- "Total prix sur facture" (distinct de total_prix = prix commande)
  ADD COLUMN IF NOT EXISTS pcb_ligne             INTEGER,  -- PCB au grain ligne de commande (distinct de produit.pcb, referentiel article)
  ADD COLUMN IF NOT EXISTS volume_m3_pcb         NUMERIC,  -- "Volume m3 PCB"
  ADD COLUMN IF NOT EXISTS volume_m3_ref_total   NUMERIC,  -- "Volume m3 référence total"
  ADD COLUMN IF NOT EXISTS nom_navire            TEXT;     -- ex-bug : anciennement stocke (a tort) dans `transitaire`
