# Profil source #3 — Suivi des artworks (Andréa, mail 25/06)

> Profilé le 2026-06-30 (gsheet lu via connecteur Drive, ~59k → sous-agent).
> gsheet `1FTr2nloJGIgLELjbEVkODVhLz4oaAjhaqtrWqXJ4Jrc` (Drive « Design et Achat », LIS-CON-28-0).
> Cible envisagée : onglet Artwork / `achat.artwork`. Suivi des validations design (Clarisse).

## Structure — DEUX tableaux empilés (à traiter séparément)

**Bloc 1** (~58 lignes, 10 col — nouveautés/créations) :
`Référence | Désignation | Date de dernière version | Date de dernière validation | Date de demande artwork | Niveau de priorité 1->5 | Valideur | Commentaire Andréa | Commentaire Clarisse / Thomas | Date d'application`

**Bloc 2** (~384 lignes utiles, 6 col — principal) :
`Référence | Désignation | Date de dernière version | Date de dernière validation | Valideur | Commentaire sur dernière version`

Volume total ~473 lignes (~58 + ~415 dont ~31 vides à exclure).

## 🔴 Décalage de grain (décision requise)

- Le gsheet est **par ARTICLE** (clé = `Référence`), **aucune colonne PO/commande**.
- `achat.artwork` est **par `(po_number, code_article)`** (contrainte UNIQUE), peuplée aujourd'hui depuis l'IMPORT Excel (633 lignes, avec PO).
- → On ne peut pas injecter ce gsheet dans `achat.artwork` tel quel sans inventer un `po_number`. C'est le **même schéma que ot_transport** : une source niveau-X (article) qui doit vivre dans sa propre zone et être fusionnée à la lecture.

## Gotchas

1. **2 tableaux empilés** (en-têtes/colonnes différents) → ingestion séparée.
2. **`#N/A`** (~50, échappés `\#N/A`) dans les colonnes date → NULL.
3. **`Référence` = « PAS DE REF »** (~6) → pas de clé ; à filtrer.
4. **Doublons de Référence** (`443850`, `Comp0806`, `10320023`…) → conflit si clé = code_article seul.
5. **Dates FR hétérogènes** : `26/03/2024`, `8-avr.-25`, `6-juin-24`, `24-févr.-26`, `22/1/2026` + littéraux `NOUVEAU`, `/` → parsing FR + NULL.
6. **~31 lignes vides** en bas du Bloc 2 (seul `Valideur` rempli) → filtrer.
7. **`Valideur`** mélange personne et enseigne (`Clarisse`, `Carrefour`, `Siplec`).
8. **Pas de colonne statut native** → `statut_artwork` à dériver (flag `NOUVEAU` / commentaire).

## Mapping proposé (sous réserve de la décision de grain)

| source | → cible | note |
|---|---|---|
| `Référence` | `code_article` | clé ; filtrer « PAS DE REF » |
| `Désignation` | `designation` | direct |
| `Date de demande artwork` (B1) / `Date de dernière validation` (B2) | `date_demande` | parsing FR ; NULL si `#N/A`/`/`/`NOUVEAU` |
| `Date de dernière validation` | `date_validation` (nouvelle col ?) | suivi validation |
| dérivé `Commentaire`/`NOUVEAU` | `statut_artwork` | pas de colonne native |
| — (absent) | `po_number` | **pas de source** |

## Décision à trancher (analogue pattern A)

- **A (reco)** : nouvelle table **`achat.artwork_statut`** (PK `code_article`) alimentée par ce gsheet ; la vue/onglet Artwork fusionne `achat.artwork` (par PO) ↔ `artwork_statut` (par article) sur `code_article`. Découplé, survit au full-refresh.
- **B** : UPDATE `achat.artwork` par `code_article` (toutes les lignes PO de l'article) — mais effacé au full-refresh + duplication de grain.
- **C** : `po_number` sentinelle — casse la sémantique UNIQUE. À éviter.
