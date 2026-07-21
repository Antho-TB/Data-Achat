# Passation Antigravity — FUSEAU / Data-Achat — 21/07/2026

## Contexte
Repo : `C:\Users\abezille\dev\Data-Achat` (branche `main`, tout est pushé jusqu'à `fe0c3e8`).
API FastAPI (`app/main.py`) + frontend mono-fichier (`frontend/index.html`) + DWH Azure PostgreSQL (`achat.*`).
Connexion DB : `Config.get_pg_url()` / `config/.env` (creds `dtpf_sylob_anthony_bezille_prod`), host `psql-dtpf-psql-prod.postgres.database.azure.com`, db `dtpf_sylob_prod`. `psql` = `C:\Program Files\PostgreSQL\16\bin\psql.exe`. Venv projet = `.venv311`.
API locale : `python run_api.py` (port 5050, PAS de reload auto sauf `API_RELOAD=1` dans `.env` — redémarrer le process après tout changement de `app/main.py`).

## ⚠️ Règle absolue
Toute édition de fichier et toute opération git (add/commit/push) sur ce repo passe par le terminal Windows local (PowerShell), **jamais** par un sandbox/conteneur Linux distant. Un sandbox Linux précédent servait du CRLF alors que les commits sont en LF → corruption garantie (git diff 100% churn, null bytes). Édite et commit uniquement depuis le poste, en réseau bureau (c'est aussi ce qui permet d'atteindre le DWH Azure directement).

## Fait le 21/07 (tout commité/pushé sur main)
1. **Design System TB appliqué** (`ffaf7de`) : tokens couleur/typo remappés dans `frontend/index.html`. Reste : teintes tertiaires en dur (badges, zebra table, header), `.kpi-card.orange` identique aux cartes bleues (perte de distinction catégorielle).
2. **Bug artwork "Validé = 0" — corrigé définitivement** (`aed9ab5`, `feec5b5`) : 3 bugs empilés au total.
   - `parse_fr_date()` ne gérait pas le format ISO pandas/openpyxl.
   - `_read_rows()` ne lisait que le 1er onglet du xlsx (le gsheet a 2 onglets, pas 2 blocs dans 1 seule feuille) — le 2e onglet ("Liste artworks", 465 lignes, la quasi-totalité des articles réels) était ignoré en silence.
   - `/api/artwork` et le KPI Dashboard lisaient `achat.artwork` (table brute, ne connaît jamais le statut de validation) au lieu de `achat.v_artwork` (la vue qui fusionne `achat.artwork_statut`) — la vue existait mais rien ne l'interrogeait.
   - Backfill complet relancé (gsheet récupéré via connecteur Drive) : `achat.artwork_statut` = 384 lignes (380 Validé, 4 Nouveau). `artwork_valides` API : 284 → 374/792 (chiffre réel).
3. **Bug ETD/ETA "Prochaines arrivées"** (`aa37b21`) : code mort retiré côté backend (la vue avait déjà été remplacée par l'onglet Conteneurs, qui distingue correctement ETD/ETA/Livraison).
4. **Qualité** (`1ee472a`, `b8afdc6`, `2d293e0`) : lien Drive + conformité labo sur N° inspection, filtre par référence article, infobulles sur toutes les colonnes du tableau produit.
5. **Dashboard** (`17b3605`) : statut "Inconnu" et "Déjà livré" rendus visibles (2 KPI + camembert 4 tranches) — avant, ces lignes disparaissaient silencieusement des compteurs En retard/Dans les délais.
6. **Suivi commande** (`19207c3`) : badge parti/pas-parti (rouge/bleu) au lieu d'un texte discret.
7. **Audit retours métier** (`aed9ab5`, `4b1a950`, `fe0c3e8`) : réorganisé en 4 blocs (sémantique à arbitrer avec Andréa, données manquantes à la source, constructions substantielles non démarrées, à revalider à l'écran) — voir le fichier pour le détail à jour.

## Priorité 1 — constructions substantielles (scope validé, pas démarrées)
Chacune de ces lignes est un vrai chantier, pas du polish de fin de session :
- **Onglets Article et Promo** : net new, aucun code existant. Article = suivi changement fournisseur dans le temps. Promo = opérations promo/fidélité type COSTCO.
- **Flag promo/urgence** sur la commande : aucun flag dans le modèle actuel, migration schéma nécessaire.
- **Non-conformité par mail** (rejet Eric T) : parsing corps de mail boîte Commerce, pipeline à construire, hors du flux BL/PJ actuel.
- **HITL** : point de validation humaine en cas de conflit entre sources (ex. date mail vs Sylob).
- **Fiche Achat Phase B** : génération PDF/xlsx (Phase A formulaire pré-rempli déjà livrée).
- **Courbe dédiée prévisionnel financier** : l'échéancier `cash_echeances` existe déjà (`/api/previsionnel`), manque la visualisation 2-3 mois dédiée.
- **Packing list comme déclencheur de paiement** (Q13) : AUCUNE colonne packing list dans le schéma, `est_a_payer` ne vérifie même pas BL/facture aujourd'hui (seulement `date_paiement IS NULL`). Avant de coder : identifier la source de la donnée avec Andréa/Marlène — ne pas inventer de colonne.

## À NE PAS coder sans validation métier (cf. audit, section 🔬)
- Sémantique `etd_confirme`/consolidation conteneur (impacte le KPI retard ET l'ambiguïté "à payer EN RETARD") — à capter avec **Andréa avant le 31/07**.
- Codes couleurs et redéfinition "Dans les délais" du Suivi commande — aucune spec écrite, idem.
- Statut de réception "actif" jusqu'à fin contrôle qualité (quarantaine) — impacte le modèle `commande`/`qualite_suivi`.
- Alertes imprévu majeur — aucune source de donnée identifiée.
- Chemin critique sur le suivi de commande — notion à définir avec le métier.
- Code article/prototype Circuit A — relation plusieurs-à-plusieurs à arbitrer avec Olivier.

## À revalider à l'écran (pas un blocage, juste pas encore fait)
Cumul des retards fournisseur (vue mise à jour le 21/07, jamais rouverte depuis à l'écran).

## Référence
Audit complet : `docs/20260721_FUSEAU_Audit_RetoursMetier_v1.md`. Plan d'action global (jalons, priorités, arbitrages) : `docs/plan_action.md`. État du code : `C:\Users\abezille\dev\claude\.ai_memory\architecture\12_fuseau_etat_implementation.md`. Standards de dev (Python, commits FR pédagogiques) : skill `standards-dev-antho-tb`.