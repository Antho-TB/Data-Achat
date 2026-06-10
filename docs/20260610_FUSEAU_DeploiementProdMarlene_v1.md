# FUSEAU — Déploiement prod sur le poste Marlène
_2026-06-10 · env test = poste Antho · env prod = poste Marlène_

## 1. Checklist déploiement

1. `git pull` (ou copie du repo) sur le poste Marlène — commit ≥ `bd68bec`.
2. `pip install -r requirements.txt` (fichier unifié, mêmes versions que le test).
3. `config/.env` (copier depuis `config/marlene.env` du test) :
   - `KEY_VAULT_NAME=` (vide — pas d'az login sur son poste), `PG_USER=platform_team`,
     `PG_PASSWORD=***`, `API_KEY=<même clé que le test>`, `API_RELOAD=0` (défaut).
4. VPN Stormshield actif → `python run_api.py` → http://127.0.0.1:5050.
5. Vérifier `/api/health` : `write_enabled: true` + DWH connecté.
6. Grants `platform_team` : déjà posés par l'ETL (SELECT sur tout, INSERT/UPDATE sur
   `commande_annotation` et `artwork`). ⚠️ L'ETL et les scripts destructeurs restent
   sur le poste Antho (platform_team n'a pas TRUNCATE).
7. Source Excel : sur son poste, `DATA_DIR` peut pointer vers le partage réseau réel
   (`\\Srv-files-pom\partage\ADA\METIER\...`) — l'ETL n'y tourne PAS pour l'instant
   (ingestion centralisée côté Antho sur le réplica).
8. Tâche planifiée (plus tard) : `python -m src.scripts.etl.pipeline` quotidien sur le
   poste qui voit le fichier source — à trancher quand le réplica sera remplacé.

## 2. Compétences (skills) à mettre à jour

| Skill | Modification nécessaire |
|---|---|
| `achatcircuit-b` | Artwork : la source est IMPORT col N, statuts natifs (Aucun/A envoyer/Envoyé/Attente Clarisse/Attente Carrefour), granularité (PO, article). Volumétrie : 636 lignes/101 PO post-nettoyage. Bloc qualité AA-AH documenté. Gotcha : total_prix = SUMIF par PO, jamais sommé ligne à ligne. |
| `achat-gmail-pipeline:achat-gmail-dwh` | Réaligner sur le DDL réel de `achat.commande` (etd_confirme/etd_reel/eta, pas de date_etd/type_mail/source) ; écrire en UPSERT sur (po_number, code_article) ; annotations → `achat.commande_annotation`. |
| `achatsuivi-commande` | Référencer la vue `achat.v_retard_article` (retard PAR article) et l'ETD effectif COALESCE(etd_reel, etd_confirme). |
| `achathistorique-prix` | Table `achat.historique_prix` toujours à créer (P4) ; fallback actuel = `achat.commande` (prix_unitaire par date_commande). |
| `achatcircuit-a` | RAS (déjà conforme : PK code article, code provisoire JJMMAAHHMM). |

→ Skills modifiables via Settings > Capabilities (cache session en lecture seule).
Sur demande : génération des `.skill` corrigés prêts à installer.

## 3. Mémoires mises à jour ce jour

- `.ai_memory/decisions_log/20260610_erp_achat_modele_donnees.md` (ADR + addendum gotchas)
- `.ai_memory/INDEX.md` (lien ADR)
- Mémoire auto Claude : `project_data_achat_erp.md` (FUSEAU, clés, comptes, gotchas)

## 4. Gotchas d'exploitation (les 3 pièges du jour)

1. **total_prix** (col T Excel) = SUMIF par PO répété par ligne → jamais de SUM ligne à ligne.
2. **« Lecture seule recommandée »** sur IMPORT 2026.xlsx → COM Excel doit ouvrir avec
   IgnoreReadOnlyRecommended sinon Save() silencieusement sans effet.
3. **Workers uvicorn orphelins** (Windows) : un kill du parent laisse le worker répondre
   sur le port avec du vieux code → toujours purger par
   `Get-CimInstance ... -match 'run_api|spawn_main'` ; reload désactivé par défaut (API_RELOAD=0).
