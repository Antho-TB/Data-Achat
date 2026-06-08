# TASKS — Data-Achat

_Projet : POC Analyse & Centralisation données Service Achats TB Groupe_  
_Contact métier : Andréa (Achats) · e.georgeon@tb-groupe.fr (Supply Chain)_  
_Deadline POC : 31/07/2026_

---

## Active

- [ ] Écrire `etl_achat.py` — extraction + nettoyage xlsx → PostgreSQL DWH
  - `ffill()` sur Référence (Matrice TB Import)
  - Regex `Etat de la commande` → statut enum + date
  - Normaliser `Lot/Vrac` (False → 'Unitaire')
  - Tables cibles : `dim_article`, `fait_commande_import`

- [ ] Valider le schéma cible avec Andréa + e.georgeon avant prod

- [ ] Concevoir l'architecture du formulaire par blocs (référentiel produit collaboratif)
  - Bloc Design (packaging) → Design
  - Bloc Commerce (prix, conditions) → Eric
  - Bloc Produit (nom FR/EN, gamme) → Jonatan
  - Bloc Sourcing (fournisseur, China) → Julia
  - Bloc Logistique (PCB, EAN, volumes) → Emmanuelle

- [ ] Ré-exporter `dim_matrice_vrac.csv` et `fait_import_suivi.csv` (corrompus — newlines dans headers)

- [ ] Décider option d'intégration : A (MyReport ETL nuit) ou C (SharePoint + n8n temps réel)

---

## Someday

- [ ] Unpivot onglet "Lot Multiples produits" (122 colonnes → modèle normalisé)
- [ ] Connecter Sylob ERP comme source complémentaire (mode d'accès à définir)
- [ ] Mettre en place tracking `updated_by` / `updated_at` par bloc dans le DWH

---

## Completed

- [x] Cartographier les 4 sources de données Achats (2026-06-01)
- [x] Profiler les fichiers Excel Andréa — structure, colonnes, qualité (2026-06-01)
- [x] Identifier les tables DWH existantes (dim_article_logistique déjà chargée) (2026-06-01)
- [x] Produire le schéma cible de centralisation (2026-06-01)
- [x] Intégrer la prise de note — architecture multi-service, PK = code article (2026-06-01)
