# Passation Antigravity — FUSEAU / Data-Achat — 21/07/2026 matin

## Contexte
Repo : `C:\Users\abezille\dev\Data-Achat` (branche `main`, tout est pushé jusqu'à `1ee472a`).
API FastAPI (`app/main.py`) + frontend mono-fichier (`frontend/index.html`) + DWH Azure PostgreSQL (`achat.*`).
Connexion DB : `Config.get_pg_url()` / `config/.env` (creds `dtpf_sylob_anthony_bezille_prod`), host `psql-dtpf-psql-prod.postgres.database.azure.com`, db `dtpf_sylob_prod`. `psql` = `C:\Program Files\PostgreSQL\16\bin\psql.exe`. Venv projet = `.venv311`.

## ⚠️ Règle absolue
Toute édition de fichier et toute opération git (add/commit/push) sur ce repo passe par le terminal Windows local (PowerShell), **jamais** par un sandbox/conteneur Linux distant. Un sandbox Linux précédent servait du CRLF alors que les commits sont en LF → corruption garantie (git diff 100% churn, null bytes). Édite et commit uniquement depuis le poste, en réseau bureau (c'est aussi ce qui permet d'atteindre le DWH Azure directement).

## Ce qui a été fait ce matin (déjà commité/pushé)
1. **Design System TB appliqué** (`ffaf7de`) : tokens couleur/typo remappés dans `frontend/index.html` (`:root`), radius à 0, Archivo/Roboto/Roboto Mono. Reste : teintes tertiaires encore en dur (fonds badges, zebra table, texte clair header `#a8c0d8`), et `.kpi-card.orange` rend maintenant identique aux cartes bleues par défaut (perte de distinction catégorielle à surveiller en démo).
2. **Bug artwork "Validé = 0" corrigé** (`aed9ab5`) : `src/scripts/etl/transform_artwork.py`, `parse_fr_date()` ne gérait pas le format ISO (`"2024-06-06 00:00:00"`) produit par pandas/openpyxl pour les cellules Excel typées date — seulement le texte FR (`6-juin-24`) ou JJ/MM/AAAA. Fixé avec un pattern ISO ajouté en premier.
3. **Backfill artwork PARTIEL** : la vraie source (gsheet Drive `LIS-CON-28-0 Suivi des artworks-import`, 384 articles réels avec statuts/dates de validation) n'avait jamais été chargée — seul un fichier de test à 2 lignes l'avait été. **2 lots sur 10 chargés** (80/384 lignes upsertées dans `achat.artwork_statut`, dont ~78 "Validé"). **Reste à faire : 8 lots.**
4. **Audit retours métier mis à jour** (`aed9ab5`) : `docs/20260721_FUSEAU_Audit_RetoursMetier_v1.md` intègre les points de la note Calendar du 23/06 (acompte versé, lien Drive qualité, désignation article, CA fournisseur 3 ans, statut quarantaine, alertes imprévu, chemin critique).
5. **Quick wins qualité** (`1ee472a`) : `/api/qualite` joint maintenant `qualite_doc` (lien Drive via `ref_rapport`) et `qualite_analyse` (conformité labo). Frontend : N° inspection cliquable vers Drive + colonne Conformité. NB : désignation article, acompte versé et CA fournisseur 3 ans étaient **déjà** exposés bout en bout (backend + frontend) — vérifié, aucun code à écrire dessus.

## À faire ce matin — priorité 1 : finir le backfill artwork
Le gsheet source est déjà téléchargé et transformé (384 records JSON). Le plus simple : reproduire proprement le pipeline documenté plutôt que rejouer mes fichiers SQL ad hoc :
1. Télécharger le gsheet Drive `LIS-CON-28-0 Suivi des artworks-import` (2 onglets : "Artworks en attente" + "Liste artworks") en xlsx.
2. `python -m src.scripts.etl.transform_artwork --file <fichier> --out data/_artwork.json` (sur CHAQUE onglet, ou fusionner les deux blocs — voir docstring du script, il gère nativement "2 blocs empilés").
3. `python -m src.scripts.gmail.load_artwork --file data/_artwork.json --dry-run` puis sans `--dry-run` pour committer.
4. Vérifier : `SELECT statut_artwork, count(*) FROM achat.artwork_statut GROUP BY 1;` → attendu ~380 "Validé", 4 "Nouveau".
Repartir de zéro est plus propre que reprendre mes lots SQL manuels (fichiers `artwork_batch_*.sql` dans le dossier outputs de la session Claude, non repris dans le repo).

## Priorité 2 — reste du polissage UI (backlog déjà cadré, cf. audit)
- Design System : teintes tertiaires restantes (badges, zebra table, header).
- Dashboard : statut "Inconnu" (reclasser/exclure), segmenter "en cours de livraison" (dans les délais / en retard) + indicateur "déjà livré".
- Suivi commande : redéfinir "Dans les délais", reprendre les codes couleurs d'Andréa, statuts manquants, infobulle date d'inspection.
- Prévisionnel : lever l'ambiguïté "à payer EN RETARD", corriger le bug "Prochaines arrivées" (ETD vs ETA).
- Qualité : filtre par référence article (n'a aujourd'hui que fournisseur/résultat/BAT).

## À NE PAS coder sans validation métier (cf. audit, section 🔬)
Statut de réception "actif" jusqu'à fin contrôle qualité (quarantaine, impacte le modèle `commande`/`qualite_suivi`), alertes imprévu majeur (aucune source de donnée identifiée), chemin critique (notion à définir avec le métier), sémantique `etd_confirme`/consolidation conteneur, code article/prototype Circuit A.

## Référence
Audit complet : `docs/20260721_FUSEAU_Audit_RetoursMetier_v1.md`. État du code : `C:\Users\abezille\dev\claude\.ai_memory\architecture\12_fuseau_etat_implementation.md`. Standards de dev (Python, commits FR pédagogiques) : skill `standards-dev-antho-tb`.
