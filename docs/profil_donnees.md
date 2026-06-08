# Profil des données — Service Achats TB Groupe

> Généré le 2026-06-01 · Source : fichiers Andréa + exports DWH + prise de note.docx

---

## Vue d'ensemble des sources

| Fichier | Onglet | Lignes utiles | Colonnes | Statut qualité |
|---------|--------|--------------|----------|----------------|
| `IMPORT 2026.xlsx` | IMPORT 2025 | 746 | 46 | ⚠️ Semi-structuré |
| `IMPORT 2026.xlsx` | POINT MIF | 23 | 13 | 🔴 Non structuré |
| `IMPORT 2026.xlsx` | STOP REF CARREFOUR | ~9 | 7 | 🟡 Exploitable |
| `Matrice TB Import.xlsx` | Lot-Vrac Produits uniques | 1 190 réfs¹ | 43 | 🟡 Bon, header=2 |
| `Matrice TB Import.xlsx` | Lot Multiples produits | ~300 lots² | 122 | 🔴 Très complexe |
| `Matrice TB Import.xlsx` | Produits PERF | ~59 | 3 | 🔴 À clarifier |
| `Base article dimensions volume.xlsx` | Feuil2 | 4 260 | 13 | ✅ Propre |
| `Ménagère et sets - Fiche Achat Vierge.xlsx` | Feuil1 | — | — | 🔴 Template vide |
| `Produits uniques - Fiche Achat Vierge.xlsx` | Feuil1 | — | — | 🔴 Template vide |
| `DWH_Achats/dim_article_logistique.csv` | — | 4 260 | 13 | ✅ = Base dimensions |
| `DWH_Achats/dim_matrice_vrac.csv` | — | — | — | 🔴 Export corrompu |
| `DWH_Achats/fait_import_suivi.csv` | — | — | — | 🔴 Export corrompu |

¹ 4 765 lignes dont 3 575 sans référence (lignes vides ou sous-détails Excel).  
² Structure multi-produits par lot : 122 colonnes = répétition des specs × 8 produits.

---

## 1. IMPORT 2026.xlsx — Suivi des commandes

### Structure (header ligne 3)

| Colonne | Type | Description | Qualité |
|---------|------|-------------|---------|
| Intermédiaire | Dimension | TB CHINA (94%) / DIRECT (2%) | ✅ |
| Date envoi de la commande | Temporal | 2024-06-17 → 2026-03-10 | ✅ |
| MEN# | Identifiant | N° mission (88 uniques) | ✅ |
| PO# | Identifiant | N° commande (101 uniques) | ✅ |
| N° Lot | Identifiant | Lot de fabrication | 🟡 valeurs libres |
| Fournisseur | Dimension | 25 fournisseurs distincts | ✅ |
| OP/Client/Appro | Dimension | Opération / client / appro | ✅ |
| Acompte | Dimension | Aucun / montant | ✅ |
| Alerte | Dimension | État alerte | 🟡 valeurs libres |
| **Etat de la commande** | Dimension | Texte libre avec dates | 🔴 À normaliser |
| Payé ? | Temporal | Date de paiement | 🟡 mélange bool/date |
| REF | Identifiant | Référence article | ✅ |
| Désignation | Texte | Libellé article | ✅ |
| Quantité | Métrique | — | ✅ |
| PU | Métrique | Prix unitaire | ✅ |
| Total prix commande | Métrique | 0 → 782 523 | ✅ |
| Volume m3 commande | Métrique | Volume total | ✅ |
| ETD confirmé | Temporal | Date départ usine prévue | ✅ |
| ETD réel | Temporal | Date départ réelle | ✅ |
| ETA | Temporal | Date arrivée estimée | ✅ |
| Date de livraison | Temporal | Date livraison effective | ✅ |
| Lieu de livraison | Dimension | — | ✅ |
| N° BL | Identifiant | Bon de livraison | ✅ |
| N° Conteneur | Identifiant | — | ✅ |
| N° Facture | Identifiant | — | ✅ |
| Transitaire | Dimension | — | ✅ |
| Colis/pièces manquantes | Texte | Anomalies livraison | 🟡 |

### KPIs extractibles

- Délai moyen commande → livraison (ETD → Date livraison)
- Taux de commandes annulées (colonne Etat)
- Montant total par fournisseur / gamme / période
- Taux de conformité livraison (Non-conformité NCR)
- Retard en jours (colonne présente)

### Problème qualité critique

`Etat de la commande` contient des valeurs texte libres avec dates embarquées :
- `"Livrée le 18/09/2025"`, `"En production"`, `"En cours de livraison"`, `"Annulée"`
- → Nécessite un parsing regex pour extraire : **statut (enum)** + **date effective**

---

## 2. Matrice TB Import.xlsx — Catalogue produits

### Onglet principal : Lot-Vrac Produits uniques

| Colonne | Type | Description | Qualité |
|---------|------|-------------|---------|
| Référence | Identifiant (PK) | 1 190 valeurs uniques / 4 765 lignes | ⚠️ 75% nulls |
| Description FR | Texte | Libellé français | ✅ |
| Description ENG | Texte | Libellé anglais | ✅ |
| Fournisseur | Dimension | 24 fournisseurs | ✅ |
| Date création | Temporal | — | ✅ |
| Gamme | Dimension | ~60 gammes distinctes | ✅ |
| Lot/Vrac | Dimension | Lot / Vrac / False | 🟡 booléen mal encodé |
| Nombre de pièce | Métrique | Unités par lot | ✅ |
| EAN 13 | Identifiant | Code-barres consommateur | ✅ |
| EAN 14 SPCB / PCB | Identifiant | Code-barres logistique | ⚠️ 75% nulls |
| Nomenclature | Texte | Code douanier | ✅ |
| Épaisseur / Longueur / Poids | Métriques | Dimensions physiques | ✅ |
| Matière lame / manche | Dimension | Matériaux | ✅ |
| Finition | Dimension | — | ✅ |
| Pantone/Motif (x6) | Dimension | Coloris | 🟡 multi-valeurs |
| Packaging / dimensions PCB | Métriques | Colisage | ✅ |

**Explication des 75% nulls sur Référence** : le fichier Excel a une structure hiérarchique — la référence n'est écrite qu'une fois, les lignes suivantes sont des variantes (coloris, finitions). Il faut un `ffill()` (forward-fill) sur la colonne Référence à l'extraction.

### Gammes les plus représentées (top 10)

Acidule · Intuition · Open decor · Duo · Amande · Héritage · Laguiole · Drop · Open uni color · Céramique

---

## 3. Base article dimensions volume.xlsx

Source **propre et déjà dans le DWH** (`dim_article_logistique.csv` = identique).

| Colonne | Renseignée | Note |
|---------|-----------|------|
| Référence | 100% | 3 430 uniques |
| EAN 13 | 80% | |
| EAN 14 SPCB / PCB | 25% | Seulement les articles avec suremballage |
| Désignation | 100% | |
| PCB / SPCB | 100% | |
| Dimensions PCB (L/l/H) | ~80% | 871 nulls |
| Poids PCB / UVC | ~80% | |
| Volume (m3) | ~80% | |

**Jointure avec Matrice** : 1 071 références en commun sur 1 190 (Matrice) et 3 430 (Dimensions) — bonne couverture pour les articles import.

---

## 4. Problèmes qualité — synthèse

| Sévérité | Problème | Fichier | Action |
|----------|---------|---------|--------|
| 🔴 Critique | `Etat de la commande` texte libre avec dates | IMPORT 2026 | Regex → statut enum + date |
| 🔴 Critique | CSV DWH corrompus (newlines dans headers) | dim_matrice_vrac, fait_import_suivi | Ré-exporter depuis les xlsx |
| 🔴 Critique | Matrice onglet "Lot Multiples" : 122 colonnes pivotées | Matrice TB Import | Unpivot + normalisation |
| ⚠️ Majeur | Référence null à 75% dans Matrice Lot-Vrac | Matrice TB Import | `ffill()` à l'extraction |
| ⚠️ Majeur | `Lot/Vrac` encodé avec False (booléen Excel) | Matrice TB Import | Nettoyage → enum Lot/Vrac/Unitaire |
| 🟡 Mineur | EAN 14 null à 75% | Matrice + Base dimensions | Normal (articles sans suremballage) |
| 🟡 Mineur | Dimensions physiques null à ~20% | Base dimensions | Données manquantes légitimes |
| 🟡 Mineur | Fiches Achat Vierges = templates non remplis | Fiches FOR-ACH-03-12 | Exclure de l'ingestion |

---

## 5. Schéma cible (DWH PostgreSQL)

```
dim_fournisseur
  fournisseur_id  SERIAL PK
  nom             TEXT
  eori            TEXT
  siren           TEXT
  tva_intracommunautaire TEXT

dim_article
  reference       TEXT PK          ← clé naturelle TB Groupe
  ean13           TEXT
  ean14_pcb       TEXT
  ean14_spcb      TEXT
  designation_fr  TEXT
  designation_en  TEXT
  gamme           TEXT
  type_lot        TEXT             ← enum : 'Lot' | 'Vrac' | 'Unitaire'
  fournisseur_id  INT FK → dim_fournisseur
  nomenclature    TEXT             ← code douanier
  matiere_lame    TEXT
  matiere_manche  TEXT
  finition        TEXT
  poids_uvc_g     NUMERIC
  longueur_mm     NUMERIC
  epaisseur_mm    NUMERIC
  -- packaging
  pcb             INT
  spcb            INT
  longueur_pcb_cm NUMERIC
  largeur_pcb_cm  NUMERIC
  hauteur_pcb_cm  NUMERIC
  poids_pcb_kg    NUMERIC
  volume_m3       NUMERIC
  date_creation   DATE
  updated_at      TIMESTAMPTZ DEFAULT now()

fait_commande_import
  commande_id     SERIAL PK
  men_number      TEXT             ← MEN#
  po_number       TEXT             ← PO#
  n_lot           TEXT
  intermediaire   TEXT             ← 'TB CHINA' | 'DIRECT'
  fournisseur_id  INT FK → dim_fournisseur
  reference       TEXT FK → dim_article
  designation     TEXT
  quantite        INT
  prix_unitaire   NUMERIC
  total_prix      NUMERIC
  frais_supp      NUMERIC
  volume_m3_cmd   NUMERIC
  statut          TEXT             ← enum normalisé
  date_commande   DATE
  date_paiement   DATE
  etd_confirme    DATE
  etd_reel        DATE
  eta             DATE
  date_livraison  DATE
  lieu_livraison  TEXT
  n_bl            TEXT
  n_conteneur     TEXT
  n_facture       TEXT
  transitaire     TEXT
  non_conformite  TEXT
  retard_jours    INT
  colis_manquants TEXT
  updated_at      TIMESTAMPTZ DEFAULT now()
```

---

## 6. Contexte organisationnel — prise de note

### La Fiche Achat est un processus collaboratif, pas un fichier

La fiche achat (`FOR-ACH-03-12`) qu'Andréa constitue est le **document d'origine** — elle agrège des informations provenant de 5 services différents :

| Bloc | Responsable | Données concernées |
|------|------------|-------------------|
| Packaging | Service Design | Dimensions, matériaux, visuels |
| Commerce | Eric | Prix, conditions, clients |
| Nom produit | Jonatan | Désignation FR/EN, gamme |
| Infos China | Julia | Fournisseur, production, conformité |
| Logistique | Emmanuelle | PCB, SPCB, volumes, transport |

### Décisions d'architecture issues de la prise de note

1. **Clé primaire = code article** (pas l'EAN). L'EAN peut être absent ou multiple ; le code article TB est la clé stable dès la création.
2. **Découper la fiche achat en blocs** : chaque bloc correspond à un service propriétaire de sa donnée. L'architecture cible doit permettre à chaque service de renseigner/mettre à jour **son bloc uniquement**, sans écraser le travail des autres.

### Impact sur le modèle de données

Ce n'est pas un ETL classique fichier → DWH. C'est un **référentiel produit collaboratif** avec des producteurs de données multiples :

```
code_article (PK stable dès création)
    ├── bloc_commerce      → Eric         (prix, client, statut commercial)
    ├── bloc_design        → Design       (packaging, dimensions, visuels)
    ├── bloc_produit       → Jonatan      (nom FR/EN, gamme, description)
    ├── bloc_sourcing      → Julia        (fournisseur, pays, conformité, import)
    └── bloc_logistique    → Emmanuelle   (PCB, SPCB, poids, volume, EAN)
```

Le DWH doit pouvoir tracer **qui a renseigné quoi et quand** (`updated_by`, `updated_at` par bloc).

---

## 7. Recommandation d'implémentation

**Phase 1 — POC immédiat (Option B : script Python)**

1. Script `etl_achat.py` → lit les 3 fichiers xlsx, nettoie, exporte vers PostgreSQL
2. Transformations critiques :
   - `ffill()` sur Référence dans Matrice (structure hiérarchique Excel)
   - Regex sur `Etat de la commande` → `statut` (enum) + `date_statut`
   - Normalisation `Lot/Vrac` (False → 'Unitaire')
   - Unpivot de l'onglet "Lot Multiples" (à faire en phase 2)
3. Tables à alimenter en priorité : `dim_article` + `fait_commande_import`
4. **Clé primaire : code article** — ne jamais utiliser l'EAN comme PK

**Phase 2 — Référentiel produit collaboratif**

Vu la structure multi-service identifiée, la cible n'est pas un simple ETL mais un **formulaire web par bloc** :
- Chaque service accède à son bloc (Design, Commerce, Logistique, Sourcing, Produit)
- Andréa reste coordinatrice / validatrice
- Les données alimentent directement le DWH sans passer par l'Excel

Options d'implémentation : formulaire Streamlit multipage · ou n8n + form SharePoint · ou appli dédiée.

**Phase 3 — Production (Option A ou C)**

- Option A (MyReport ETL) : intégrer dans le pipeline existant, compte de service, nuit
- Option C (SharePoint + n8n) : si Andréa accepte de migrer son fichier sur SharePoint

**Coordination requise** : valider le schéma + le découpage par bloc avec Andréa, Eric, Jonatan, Julia et Emmanuelle avant de construire quoi que ce soit.
