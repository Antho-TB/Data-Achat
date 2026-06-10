# Analyse des fichiers Excel du service Achat — TB Groupe
_2026-06-10 · réplica J-1 · profiling complet : `outputs/profil_excels_brut.md`_

## 1. Vue d'ensemble

| Fichier | Rôle métier | Nature | Ingéré DWH |
|---|---|---|---|
| IMPORT 2026.xlsx | Suivi opérationnel des commandes import (Circuit B) | Table de données vivante | ✅ partiel → à compléter |
| Matrice TB Import.xlsx | Référentiel produit fournisseur (fiches techniques) | Table de données | ✅ partiel (1 onglet sur 3) |
| Base article dimensions volume.xlsx | Référentiel logistique (EAN, PCB, volumes) | Table de données | ✅ |
| Demande de création référence.xlsx | Formulaire Circuit A (création article) | **Formulaire**, pas une table | ❌ (à modéliser, pas à ingérer) |
| Fiche produit - Ménagères et sets.xlsx | Formulaire fiche produit | Formulaire | ❌ idem |
| FOR-ACH-03-12 Purchase sheet (×2 + G2D) | Formulaire fournisseur (EN) — fiche achat vierge | Formulaire | ❌ idem |

**Constat structurant** : 3 fichiers sont des *tables* (à ingérer), 4 sont des *formulaires*
(des workflows Circuit A à modéliser en BDD, pas des sources de données).

## 2. IMPORT 2026.xlsx — le cœur du Circuit B

### Onglet `IMPORT 2025` (661 lignes × 46 colonnes utiles, header ligne 4)
Lignes 1-2 : EORI/SIREN/TVA des 2 entités (TB, GDD) — métadonnées douanières.
**Ligne 3 : 6 blocs fonctionnels** (la vraie structure sémantique du fichier) :

| Bloc (ligne 3) | Colonnes | Contenu | Statut ingestion |
|---|---|---|---|
| Caractéristique de la commande | B–N | Intermédiaire, date envoi, MEN#, PO#, lot, fournisseur, **OP/Client/Appro (H)**, **Acompte (I)**, **Alerte (J)**, État, **Payé ? (L)**, délai, **Artwork (N)** | ⚠️ H, I, J, N ignorés jusqu'à ce jour — N corrigé (suivi artwork), reste H/I/J |
| Articles | O–R | REF, désignation, quantité, PU | ✅ |
| Montants divers | S–V | Prix/réf (=Q×R), **Total prix commande (T = SUMIF par PO, répété par ligne !)**, frais supp, total facture | ✅ (piège SUMIF documenté) |
| Volume | W–Z | PCB, volumes m3 (VLOOKUP Matrice) | ✅ |
| Analyses échantillons et inspections | AA–AH | **Matière (MAT), Semi-prod (SP), Échantillon conformité, Production (BAT), Date+Rapport inspection, Réception (RECEP), NCR** | ❌ seul NCR ingéré — c'est pourtant le « Suivi des analyses » demandé par Andréa (P6) |
| Livraison | AI–AT | ETD confirmé/réel, ETA, livraison, lieu, BL, conteneur, facture, navire, transitaire, manquants | ✅ |

### Dépendances externes critiques (formules)
- `[1]Feuil2` = **Base article dimensions volume.xlsx** → désignation, PCB, volumes (VLOOKUP O→P,W,X)
- `[2]/[3] CONTENEUR PLEIN` = **classeurs transitaire absents du réplica** → ETD réel, ETA,
  date livraison, navire (1 427 #N/A). **Source n°1 à récupérer** pour fiabiliser la Livraison.
- Col M et AJ : DATEDIF hétérogènes (236 variantes de formule retard) → remplacés côté DWH
  par la vue `achat.v_retard_article`.

### Qualité
- 84 doublons stricts (PO, REF, même lot) supprimés le 2026-06-10 (log dédié).
- 3 lignes de frais REF "/" (molding fees) — légitimes, conservées (code_article NULL).
- Dates en texte libre : « Estimée : 07-avril » (67 occurrences col AM) → non parsables.
- Col L « Payé ? » mélange "Non" et dates — parsé en date_paiement (NULL si "Non").

### Onglets secondaires
- `POINT MIF` : tableau de bord manuel production Laguiole MIF (lames/mitres/couteaux
  par matière de manche) — 19 lignes, structure libre. Ingestion non prioritaire.
- `STOP REF CARREFOUR` : liste ad hoc d'arrêts référence Carrefour (8 refs, pas de header
  propre, 1 #REF préexistant). À traiter comme un signal métier (champ `alerte`), pas une table.

## 3. Matrice TB Import.xlsx — le référentiel produit

- `Lot-Vrac Produits uniques` (ingéré) : ~1 160 articles réels (4 763 lignes dont variantes
  Pantone avec Référence propagée par ffill). Blocs ligne 2 : Informations / Caractéristiques /
  Packaging / Conditionnement. Colonne Artwork remplie à 5 % → **pas une source artwork**
  (confirmé : la source est IMPORT col N).
- `Lot Multiples produits` (**non ingéré**) : 304 ménagères/sets × 122 colonnes — structure
  dénormalisée : blocs « Produit 1 » à « Produit 8 » répétés (composition des sets).
  → Modèle cible : table `achat.produit_composant` (code_article_set, rang, type, dimensions,
  matières, marquage). C'est le chaînon manquant du référentiel ménagères.
- `Produits PERF` (**non ingéré**) : 59 références (liste simple sans header).

## 4. Base article dimensions volume.xlsx
4 259 références logistiques, EAN13 à 81 %. Référence en doublon détectée (ex : 30020342 ×2)
→ dédoublonnage keep-first dans l'ETL. Sert aussi de cible aux VLOOKUP d'IMPORT 2026 :
toute divergence entre ce fichier et la Matrice se propage dans le suivi import.

## 5. Les formulaires (Circuit A)
`Demande de création référence`, `Fiche produit Ménagères`, `FOR-ACH-03-12 Purchase sheet`
(FR interne + EN fournisseur + variante G2D) : ce sont les supports de la **fiche achat
5 blocs** (Design/Commerce/Produit/Sourcing/Logistique). Ils ne s'ingèrent pas :
ils définissent les champs de `achat.produit` et le futur workflow de création
(code provisoire JJMMAAHHMM → code article Sylob). Couverture actuelle de `achat.produit` : bonne
(les blocs y sont déjà représentés).

## 6. Réponse à la question : regrouper la BD selon les blocs ligne 3 ?

**Oui sur le fond — c'est la bonne lecture métier — mais en 4 tables, pas 6.**
Les blocs Articles/Montants/Volume partagent la même granularité (la ligne article) :
les séparer créerait des jointures 1:1 sans valeur. Le découpage pertinent suit les
**granularités réelles** :

```
achat.commande            (entête PO — granularité PO)
  ← bloc « Caractéristique de la commande » (B–N)
  po_number PK, men_number, intermediaire, date_commande, fournisseur,
  op_client_appro, acompte, alerte, statut, date_paiement, artwork_statut*

achat.commande_ligne      (granularité ligne article)
  ← blocs « Articles » + « Montants divers » + « Volume » (O–Z)
  FK po_number, code_article (FK produit), quantite, pu, prix_ligne,
  frais_supp, volumes — SANS total_prix répété (recalculé par agrégat)

achat.controle_qualite    (granularité ligne — workflow qualité)
  ← bloc « Analyses échantillons et inspections » (AA–AH)
  FK (po_number, code_article), mat, sp, echantillon, bat,
  date_inspection, rapport, recep, ncr
  → répond directement au besoin « Suivi des analyses » d'Andréa (P6)

achat.expedition          (granularité conteneur/expédition)
  ← bloc « Livraison » (AI–AT)
  n_conteneur PK, etd_confirme, etd_reel, eta, date_livraison, lieu,
  n_bl, n_facture, navire, transitaire
  + table de lien ligne ↔ expédition
  → alimentée à terme par les classeurs CONTENEUR PLEIN (transitaire)
```

Bénéfices : suppression des répétitions (total_prix, ETD dupliqués par ligne), le suivi
qualité devient requêtable, les expéditions deviennent une entité réelle (un conteneur
regroupe N lignes). Coût : refonte API/frontend + ETL. **Recommandation : conserver la
table plate actuelle comme table d'ingestion + vues, et construire ce modèle cible en
v0.3 une fois la source CONTENEUR PLEIN récupérée** — sinon achat.expedition naîtrait
aux deux tiers vide.

## 7. Backlog priorisé issu de l'analyse

1. 🔴 Récupérer les classeurs « CONTENEUR PLEIN » (transitaire) → bloc Livraison fiable.
2. 🔴 Ingérer le bloc qualité AA–AH → `achat.controle_qualite` (besoin Andréa P6).
3. 🟠 Ingérer H/I/J (OP-Appro, acompte, alerte) dans achat.commande — traçabilité Circuit B
   (lien suggestion d'appro Olivier ↔ PO).
4. 🟠 Ingérer `Lot Multiples produits` → `achat.produit_composant` (304 ménagères).
5. 🟡 Modèle cible 4 tables (v0.3, après CONTENEUR PLEIN).
6. 🟡 Produits PERF (59 refs) → flag sur achat.produit.
