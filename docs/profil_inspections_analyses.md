# Profil sources #1 (inspections DEKRA) & #2 (analyses labo) — Andréa, mail 25/06

> Profilé le 2026-06-30 via connecteur Drive.
> POC = Google Drive ; prod = serveur `\\Srv-files-pom\…\ANALYSES ET INSPECTIONS`.
> Objectif métier : depuis un statut **FAIL** (onglet Qualité), ouvrir le bon rapport.

## Organisation Drive

`Purchasing department / Purchasing orders / {TB | GDD} / PO <po>-<desc>-<frn>-<date> /`
puis, dans chaque dossier PO :
- `Inspection/` — rapports d'inspection **DEKRA** (#1) *(vide sur le PO échantillonné)*
- `Results of analysis/<stade> samples/` — rapports d'**analyse labo** (#2), triés par **stade d'échantillon** (`Semi-production samples`, …)
- `Artwork/`, `Purchase sheet - PS/`

Racine TB profilée : `1R3NdXoVGNT7vnaJsLLEPrOZvUp1mjzV0` (≈ 1 dossier par PO).

## Convention de nommage (décodée)

`PO181325 SP lg herit fromage 3 p éch1 couperet DK CA183435.pdf`

| Fragment | Sens |
|---|---|
| `PO181325` | PO (sans zéros de tête ; commande = `00181325`) |
| `SP` | stade (SP = Semi-Production ; aussi MAT/production…) |
| `lg herit fromage 3 p` | produit / lot |
| `éch1` | n° échantillon |
| `couperet` / `tartineur` / `manche` | composant |
| `DK` | DEKRA |
| `CA183435` | **réf rapport** (clé) |

## #2 Analyses labo — CONTENU TEXTE EXTRACTIBLE (pas d'OCR)

Rapport = sortie instrument **SPECTRO** (AMETEK), texte natif. Champs exploitables :
- **`Hardness (HRC)`** + `Hardness Compliance`
- **`Cr`** (chrome %) — ex. 13.36 — et tous les éléments (Mn, P, Mo, Ni, Cu, Pb, Fe…)
- **Conformité** : `Alimentarité acier inox (décret 1976)` → `Conformity`
- `Sample Name` (= reprend PO + stade + échantillon + DK), réf `CA183435`, date/heure, opérateur.

→ On peut alimenter directement le besoin BI « taux de chrome / dureté / conformité » (concept manquant #6).

## #1 Inspections DEKRA — à profiler sur un PO inspecté

Dossier `Inspection/` vide sur le PO échantillon → format non confirmé (rapport de contrôle visuel, potentiellement **scan → OCR**). À revérifier sur un PO ayant une inspection.

## Modèle proposé (pattern A — zone découplée)

Table **`achat.qualite_doc`** (index des rapports, pour le lien FAIL→rapport) :
`po_number, societe (TB/GDD), type (analyse|inspection), stade, ref_rapport (CA…), composant, echantillon, fichier, drive_file_id, drive_url, source_fichier, charge_le`.

Option **extraction #2** : table `achat.qualite_analyse` (ou colonnes) :
`ref_rapport, po_number, echantillon, hardness_hrc, cr_pct, conformite (bool/text), norme, date_mesure` — dérivées du texte SPECTRO.

Lien vue Qualité : `achat.qualite` ↔ `qualite_doc` via `po_number` (+ `ref_rapport` déjà en base) → URL cliquable sur FAIL.

## Crawler
POC = connecteur Drive (walk TB+GDD → PO → Inspection/Results → fichiers → parse nom).
Prod = walk serveur `ANALYSES ET INSPECTIONS`. Même parseur de nom + même extraction PDF.

## Décision à trancher
- **A** : index seul (`qualite_doc` + URL) — sert l'objectif « ouvrir le rapport depuis FAIL ». Rapide.
- **B (reco)** : A **+ extraction labo** (chrome/dureté/conformité, texte → `qualite_analyse`). Faisable sans OCR, débloque un concept BI manquant. DEKRA (#1) reste en lien seul tant que le format n'est pas confirmé.
