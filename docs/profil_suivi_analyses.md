# Profil source #5 — SUIVI DES ANALYSES (Andréa, mail 25/06)

> Profilé le 2026-06-30 (gsheet `1lE9te1…Jzi-c`, Drive « Qualité et achat », ~88k → sous-agent).
> Cible : suivi qualité (onglet Qualité). Complète #1/#2 (rapports) : le **`CA`** ici = `ref_rapport` là-bas.

## 6 blocs empilés (1 seul classeur)

| Bloc | Contenu | Grain | Charger ? |
|---|---|---|---|
| **A** | Suivi analyses **en cours** (~60 lignes utiles) | échantillon (article×PO×CA×stade) | ✅ |
| **D** | **Archive** des analyses (~276) | idem A | ✅ (UNION avec A) |
| **E** | **Facturation labo** (~107) : comptes S/D/M/Cycles + montants CA vs BL | rapport CA facturé | ✅ table à part |
| B | Référentiel analyses par famille produit (27) | règles | référence (option) |
| C | Légendes urgence/états | doc | ignorer |
| F | Tarifs labo (6) | référence | option |
| G | Catalogue article Ref↔Désignation (~516) | référence | référence (option) |

## Colonnes Bloc A / D (cœur)

A : `Ref | Désignation échantillon | Stade Echantillon | PO FRS | CA | Date d'envoi | N° BL | Niveau d'urgence 1->5 | Etat du produit | Etat analyse`
D : `REF | Désignation échantillon | Stade Echantillon | PO fournisseur | CA | Date d'envoi de la CA | N° BL | Opérateur | Date de BL`

- **Clés** : `Ref`→code_article, `PO FRS`→po_number, **`CA`→ref_rapport** (jointure vers #1/#2 `qualite_doc`/`qualite_analyse`), `Stade` ∈ {MAT, SP, BAT, RECEP}.
- Pas de chrome/dureté chiffrés ici (ils sont dans les PDF SPECTRO = #2). #5 = **cycle de vie de la demande d'analyse** (CA envoyée, stade, dates, BL, état).

## 🔴 Décalage de grain (décision requise)

`achat.qualite` (633 lignes, ex-IMPORT) a **UNIQUE (po_number, code_article)** = 1 ligne/article/PO.
#5 a **plusieurs analyses par (PO, article)** (stades MAT/SP/BAT/RECEP, plusieurs CA) → **conflit** avec cette contrainte.

Options :
- **A (reco)** : nouvelle table **`achat.qualite_suivi`** (grain échantillon : po_number, code_article, ref_rapport CA, stade, date_envoi, n_bl, date_bl, urgence, etat_produit, etat_analyse, operateur, source). UNION Bloc A+D. Se joint à `qualite_doc`/`qualite_analyse` par `ref_rapport`. `achat.qualite` inchangée.
- **B** : étendre `achat.qualite` (ajouter stade/CA, changer la contrainte) — invasif, impacte 633 lignes + `v_qualite_fournisseur`/`v_previsionnel`.

Bloc E → table **`achat.qualite_facturation`** (grain = CA facturé) : nb_spectro/durete/meca/cycles, montant_ht_ca, n_bl, date_bl, montant_ht_bl, a_facturer, facturation_faite.

## Gotchas
1. `#N/A` de padding (~30) en bas du Bloc A → filtrer.
2. En-têtes **multi-lignes** (`&#10;`), `->` échappé.
3. **PO multi-valeurs** (`173654-177438`, `217333-4-5-…`) + non numériques (`POLYFLAME`) + zéros de tête incohérents (A sans, D/E avec `00160837`) → normaliser.
4. Bloc B : 3 colonnes SPECTRO fusionnées → colonnes vides parasites.
5. Doublons de Ref (normal, plusieurs PO/CA) → clé ≠ Ref seule.
6. Bloc E : colonnes S/D/M/C/R **dupliquées** (côté CA vs BL) → collision de noms à gérer.

## Prochaine étape
Trancher le grain (A reco), puis coder `transform_suivi_analyses` (UNION A+D → `qualite_suivi`) + `transform_facturation` (E → `qualite_facturation`). Blocs référentiels (B/F/G) hors POC.
