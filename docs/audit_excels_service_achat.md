# Audit captation des Excel du service Achat — 2026-06-30

> But : s'assurer que FUSEAU/l'ETL capte **toutes** les données des fichiers Excel Achat.
> Statut « capté » = actuellement lu par `src/scripts/etl/transform.py` (source = `IMPORT 2026.xlsx`).

## Inventaire (dossier `Service_Achat/`)

| Fichier | Contenu | Grain | Capté ETL ? |
|---|---|---|---|
| **IMPORT 2026.xlsx** — onglet `IMPORT 2025` (671×47) | Suivi commandes import (le cœur actuel) | ligne article×commande | ✅ **oui** (transform_commande) |
| IMPORT 2026 — onglet `POINT MIF` (24×15) | Made In France : lames envoyées / couteaux retour par lot PP | lot PP × coloris | ❌ **non** |
| IMPORT 2026 — onglet `STOP REF CARREFOUR` (16×7) | Réfs Carrefour arrêtées / en cours | article | ❌ **non** |
| **Matrice TB Import.xlsx** (3 onglets, ~5600 lignes) | **Référentiel NOMENCLATURE** (composant + packaging) | article (+ multi-produit) | ❌ **non** |
| **Base article dimensions volume.xlsx** (4260×13) | Dimensions/volume/poids PCB & UVC | article | ❌ **non** (volume recalculé depuis IMPORT) |
| Fiche Achat Vierge (Ménagère / Produits uniques / G2D) | **Modèle** de fiche achat (packaging + metal part) | modèle | n/a (gabarit) |
| Demande de création référence.xlsx | Formulaire création article (composant + packaging + HS) | modèle | n/a (gabarit) |
| Fiche produit - Informations.xlsx | Fiche info produit (ensemble/manche/marquage) | modèle | n/a (gabarit) |

## Détail — sources riches NON captées

### Matrice TB Import.xlsx = LE référentiel nomenclature
- **`Lot-Vrac Produits uniques`** (4766×43) : `Référence, Description FR/ENG, Fournisseur, Date création, Gamme, Lot/Vrac, Nombre de pièce, EAN 13 / EAN 14 SPCB / EAN 14 PCB, Nomenclature (HS code), Epaisseur, Longueur, Poids, Matière lame/haut de couvert, Chrome %, Finition, Matière manche, Pantone/Motif manche 1→6, Marquage, Dimensions marquage, Emplacement`.
- **`Lot Multiples produits`** (753×122) : idem mais **multi-composants** (Produit 1→8, chaque composant avec matière/chrome/dimensions) = vraie nomenclature d'assemblage (ménagères/sets).
- **`Produits PERF`** (60×3) : réfs en perfectionnement passif.
→ Couvre **composant (matière, chrome, dimensions, manche)**, **packaging (EAN, PCB/SPCB)**, **gamme**, **HS code**. C'est la réponse à « assez de données pour la nomenclature ? » = **OUI, ici**.

### Base article dimensions volume.xlsx
`Référence, EAN 13/14 SPCB/PCB, Désignation, PCB, SPCB, L/l/H PCB (cm), Poids PCB (kg), Poids UVC, Volume (m3)` → dimensions/volumes **officiels** (aujourd'hui l'ETL recalcule le volume depuis l'IMPORT ; à fiabiliser avec cette source).

### IMPORT 2026 — onglets secondaires ignorés
- `POINT MIF` : suivi **Made In France** (lames envoyées/retour par PP) → alimente le report *BILAN MADE IN France* (concept BI manquant).
- `STOP REF CARREFOUR` : cycle de vie article (réfs arrêtées) → *Articles en sommeil*.

### IMPORT 2025 — colonnes présentes potentiellement sous-exploitées
`OP/Client/Appro, Acompte, Alerte, Nombre de mois (commande→livraison), Prix / référence, Total prix sur facture, Volume m3 PCB / référence, Matière (MAT) / Semi-production (SP) / Echantillon de conformité` (ces 3 dernières = statuts de stade qualité, cf. #1/#2/#5).

## Recommandations (captation)
1. **Ingérer `Matrice TB Import`** → table `achat.article_nomenclature` (composant + packaging + gamme + HS). Débloque le concept BI manquant « Gammes & Sous-familles / nomenclature ».
2. **Ingérer `Base article dimensions volume`** → fiabiliser dimensions/volumes (ou table `achat.article_dimensions`).
3. **Ingérer `POINT MIF`** (Made In France) et **`STOP REF CARREFOUR`** (cycle de vie).
4. Vérifier le **mapping complet des 47 colonnes de `IMPORT 2025`** dans transform_commande (colonnes OP/Client, Acompte, Alerte, Nb mois, MAT/SP/conformité).
5. Fiches (achat/produit/demande) = **gabarits** ; les instances remplies vivent dans les dossiers Drive `Purchase sheet - PS` (par PO) → à croiser avec la Matrice.

> Prochain pas : ouvrir une **PS remplie** (Drive) + livrer le mapping champ fiche/Matrice → nomenclature Sylob.
