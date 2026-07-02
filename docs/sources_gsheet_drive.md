# Sources gsheet/Drive — captation Achats (consolidé)

> Consolide les profils #3 (artworks), #1/#2 (inspections DEKRA + analyses labo),
> #5 (suivi analyses), #4 (suivi maritime) — profilés le 2026-06-30 via le
> connecteur Drive, mails Andréa du 25/06. Remplace les 4 fichiers `profil_*.md`
> individuels (fusionnés le 02/07, décisions désormais tranchées et
> implémentées — cf. `docs/plan_action.md`).

---

## #3 — Suivi des artworks

- **Source :** gsheet `1FTr2nloJGIgLELjbEVkODVhLz4oaAjhaqtrWqXJ4Jrc` (Drive « Design et Achat », LIS-CON-28-0).
- **Structure :** 2 tableaux empilés — Bloc 1 (~58 lignes, nouveautés) + Bloc 2 (~415 lignes, principal). Clé = `Référence` (grain **article**, pas de PO — décalage avec `achat.artwork` qui est par `(po_number, code_article)`).
- **Décision retenue :** table dédiée `achat.artwork_statut` (PK `code_article`), découplée, fusionnée à la lecture avec `achat.artwork` par `code_article`. Implémentée (`src/scripts/gmail/load_artwork.py`, insert-only — le statut est saisi/validé par Clarisse, l'ETL ne l'écrase jamais).
- **Gotchas à retenir si on réingeste** : `#N/A` échappés dans les dates, `Référence = "PAS DE REF"` (~6, à filtrer), doublons de référence, dates FR hétérogènes (`26/03/2024`, `8-avr.-25`...), ~31 lignes vides en fin de Bloc 2, `Valideur` mélange personne/enseigne.

## #1/#2 — Inspections DEKRA & analyses labo

- **Organisation Drive :** `Purchasing department / Purchasing orders / {TB|GDD} / PO <po>-<desc>-<frn>-<date>/` puis `Inspection/` (DEKRA, #1) et `Results of analysis/<stade> samples/` (labo, #2). Racine TB profilée : `1R3NdXoVGNT7vnaJsLLEPrOZvUp1mjzV0`.
- **Prod (source faisant foi) :** serveur `\\Srv-files-pom\...\ANALYSES ET INSPECTIONS`.
- **Convention de nommage** : `PO181325 SP lg herit fromage 3 p éch1 couperet DK CA183435.pdf` → PO (sans zéros de tête) / stade (MAT/SP/BAT) / produit-lot / n° échantillon / composant / DEKRA / réf rapport (`CA...`, clé de jointure).
- **#2 analyses labo :** ⚠️ correction 02/07 — l'hypothèse initiale « texte natif extractible, pas d'OCR » était **fausse** : les PDF SPECTRO/AMETEK n'ont aucune couche texte (0 caractère, 234 images/page, vérifié pdfplumber). OCR obligatoire (render 300dpi + tesseract). `Cr` (chrome %) fiablement extractible (position fixe dans le tableau, validé par recoupement contre une valeur de référence connue) ; `Hardness (HRC)` et la conformité alimentarité (décret 1976) ne sont pas capturés de façon fiable par un OCR généraliste — laissés NULL plutôt que devinés.
- **#1 DEKRA :** format non confirmé (dossier vide sur le PO échantillonné) — probable scan → OCR si besoin un jour.
- **Décision retenue :** `achat.qualite_doc` (index rapports, lien FAIL→PDF via `drive_url`, pilote 8 fichiers/2 PO) + `achat.qualite_analyse` (chrome extrait par OCR, pilote 8/8). Pipeline : `load_qualite_doc_drive.py` + `load_qualite_analyse_ocr.py`. Lien vue Qualité : `achat.qualite` ↔ `qualite_doc` par `po_number` + `ref_rapport`.

## #5 — Suivi des analyses (facturation labo)

- **Source :** gsheet Drive « Qualité et achat » — 6 blocs empilés dans 1 classeur : A (en cours, ~60), D (archive, ~276, UNION avec A), E (facturation labo, ~107), B/C/F/G = référentiels hors POC.
- **Clés Bloc A/D :** `Ref`→code_article, `PO FRS`→po_number, `CA`→`ref_rapport` (jointure vers qualite_doc/qualite_analyse), `Stade` ∈ {MAT, SP, BAT, RECEP}.
- **Décalage de grain :** `achat.qualite` est UNIQUE (po_number, code_article) = 1 ligne/article/PO ; le suivi analyses a plusieurs analyses par (PO, article) (plusieurs stades/CA).
- **Décision retenue :** `achat.qualite_suivi` (grain échantillon, UNION Bloc A+D) + `achat.qualite_facturation` (grain CA facturé, Bloc E) — `achat.qualite` inchangée. Tables créées le 30/06 (`sql/20260630_qualite_suivi.sql`).
- **Gotchas à retenir** : `#N/A` de padding, en-têtes multi-lignes, PO multi-valeurs (`173654-177438`) et non numériques (`POLYFLAME`), colonnes SPECTRO fusionnées (Bloc B), colonnes S/D/M/C/R dupliquées côté CA vs BL (Bloc E).

## #4 — Suivi maritime

- **Source POC (lisible) :** gsheet `1hP73oivXrB8o8I7pkrGh7y6nPzn0ccfW` (partagé transitaire). **Source prod (faisant foi) :** serveur `\\Srv-files-pom\...\SUIVI CDES IMPORT\2026\TRANSITAIRE`.
- **Structure :** 1 feuille, 2 zones — Zone 1 = données conteneurs (à ingérer : `FOURNISSEUR | COMMANDE | REF QUALITAIR | TYPE | POL | POD | NAVIRE | ETD | ETA | CONTENEUR | ATD | ETA(2) | BL | ...`), Zone 2 = calendrier hebdo visuel (à ignorer).
- **Décision retenue :** `achat.ot_transport` (PK `n_conteneur`), pattern A découplé. Bootstrap initial (57 lignes) venait de cette feuille ; alimenté depuis le 02/07 par `transform_maritime.py` (bug de parsing de date ISO corrigé le même jour).
- **Gotchas à retenir** : dates textuelles anglaises sans année (rollover déc→mars = année+1), 2 colonnes ETA (estimée vs confirmée, prendre la confirmée), `COMMANDE` multi-PO à éclater, bookings futurs sans conteneur (pas de PK, hors `ot_transport`).

---

**Règle transverse rappelée par Antho (02/07) :** le gsheet maritime est collaboratif avec le transitaire — **aucune modification, lecture seule**.
