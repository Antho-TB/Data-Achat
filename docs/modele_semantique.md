# Modèle sémantique — schéma `achat.*` (DWH Azure `dtpf_sylob_prod`)

> But : comprendre les données, tables et champs qu'on constitue, et servir de **socle
> au mapping vers Sylob** (objectif cible : ramener ces données structurées dans l'ERP).
> Généré à partir de l'introspection du schéma (12 tables + 4 vues au 2026-07-02).
> Colonne « Sylob ? » = à auditer contre `tarrerias_production_dwh` (déjà présent oui/non).

## Zones fonctionnelles

- **Base import** (source IMPORT Excel Andréa, cible Sylob V25) : `commande`, `produit`, `acompte`, `fournisseur_ca`.
- **Enrichissement découplé (pattern A)** — survit au full-refresh, mergé par les vues : `ot_transport`, `artwork_statut`, `qualite_doc`, `qualite_analyse`, `article_nomenclature`, `commande_annotation`.
- **Vues de lecture** (ce que consomme FUSEAU) : `v_previsionnel`, `v_retard_article`, `v_artwork`, `v_qualite_fournisseur`.

## Dictionnaire des tables

| Table | Rôle | Grain | Clé | Source | Sylob ? |
|-------|------|-------|-----|--------|---------|
| `commande` | Suivi commandes import (cœur) | ligne article × commande | id ; UQ (po_number, code_article) | IMPORT 2025.xlsx | partiel (Sylob = commande achat) |
| `produit` (46 col) | Référentiel produit enrichi | article | code_article | ETL + enrich Sylob | **oui** (Sylob article) |
| `acompte` | Acompte versé par PO | PO | po_number | IMPORT (col Acompte) | % oui / montant non |
| `fournisseur_ca` | CA cumulé 3 ans | fournisseur | fournisseur | Sylob (vue_commande_achat) | **oui** (dérivable Sylob) |
| `article_nomenclature` | **Nomenclature composant+packaging+gamme+HS** | article | code_article | Matrice TB Import.xlsx | à auditer (gamme/HS/EAN probables) |
| `ot_transport` | Suivi expédition maritime | conteneur | n_conteneur | SUIVI MARITIME (transitaire) | **non** (hors Sylob) |
| `artwork` | Artwork par commande | po × article | UQ (po_number, code_article) | IMPORT | non |
| `artwork_statut` | Statut validation design | article | code_article | Suivi artworks (Clarisse) | non |
| `qualite` | Qualité par commande | po × article | UQ (po_number, code_article) | IMPORT (MAT/SP/conformité) | partiel |
| `qualite_doc` | Index rapports (lien FAIL→fichier) | fichier rapport | drive_file_id | Drive/serveur ANALYSES ET INSPECTIONS | non |
| `qualite_analyse` | Mesures labo (chrome/dureté/conformité) | fichier rapport | drive_file_id | rapports SPECTRO (PDF) | non |
| `commande_annotation` | Notes métier (survit full-refresh) | po × article | UQ (po_number, code_article) | saisie FUSEAU | non |

Tables décidées mais non créées (build #5 en pause) : `qualite_suivi` (suivi analyses A+D), `qualite_facturation` (bloc E).

## Vues (lecture / merge)

| Vue | Compose | Logique clé |
|-----|---------|-------------|
| `v_previsionnel` | commande + qualite + **ot_transport** | `COALESCE(ot.etd_reel, c.etd_reel, c.etd_confirme)`, `COALESCE(ot.eta, c.eta)` (BL prioritaire) ; flags acheté/à payer/parti/retard/livré |
| `v_retard_article` | commande + ot_transport | retard figé si livré, sinon `CURRENT_DATE - ETD` |
| `v_artwork` | artwork + **artwork_statut** | statut design prioritaire (`COALESCE` sur code_article) |
| `v_qualite_fournisseur` | qualite | évaluation fournisseur |

## Relations (schéma de jointure)

```
article_nomenclature.code_article ─┐
produit.code_article ──────────────┤
                                    ▼
commande (po_number, code_article) ─┬─ qualite (po_number, code_article)
   │  │                             ├─ artwork (po_number, code_article) ── artwork_statut (code_article)
   │  │                             └─ commande_annotation (po_number, code_article)
   │  └─ code_article ── article_nomenclature / produit
   └─ n_conteneur ── ot_transport (n_conteneur)

qualite / qualite_doc / qualite_analyse ── ref_rapport (CA…)   [suivi analyses #5 = même CA]
fournisseur ── fournisseur_ca ; acompte ── po_number
```

## Maintenance & suite

- Ce document = **modèle sémantique v1** (niveau table). Détail colonnes : DDL `sql/` + `information_schema`.
- ➜ **Proposé** : générer un `achat_schema.yaml` (machine-readable, auto-introspecté) + descriptions, réutilisable par le skill `data-context-extractor` pour donner à Claude le contexte data de TB.
- ➜ **Colonne « Sylob ? »** : à compléter par l'audit `tarrerias_production_dwh` (chaque champ : existe déjà / à migrer) — livrable clé de la revue Emmanuelle et de la cible « ramener dans Sylob ».
