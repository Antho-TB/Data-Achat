# Poste Marlène — Brief de session (FUSEAU / Data-Achat)

> But : tout ce qui ne peut se faire QUE depuis le poste de Marlène (sa session Gmail
> `achat.import@tb-groupe.fr`, son Cowork, son accès réseau/VPN).
> Poste : `C:\Users\mmontbrizon\Documents\Claude\Data-Achat` · Python **3.11** (venv) · VPN Stormshield requis.
> Dernière MAJ : **2026-07-22** (session Cowork sur le poste de Marlène).

---

## 📌 Journal d'avancement — 22/07 (session Cowork en cours)

> Suivi live de la mise en prod de l'ETL Gmail (corps de mails + PJ) depuis la boîte de Marlène.

**✅ Fait aujourd'hui**
- [x] **Resync du poste** : le dossier était figé au 30/06 (74ade51), 104 commits de retard + un `.git/index.lock` bloqué. Lock supprimé, `reset --hard origin/main` → poste aligné sur **`a3f7a63`**, working tree propre.
- [x] **venv Python 3.11** (`.venv311`) créé via `uv` + dépendances (`requirements.txt` + `requirements-gmail.txt`). Fin de la dette 3.13.
- [x] **OCR installé** : Tesseract 5.4.0 (langues `eng` + `fra`) + Poppler 26.02.0, ajoutés au PATH utilisateur.
- [x] **Token Gmail re-consenti** : scopes `gmail.readonly` + `drive.readonly` (débloque aussi le crawl Drive qualité). Ancien token sauvegardé en `config/token.json.bak`.
- [x] **Preflight 100% vert** : OCR / Token / DWH / Python 3.11 / git — « Poste prêt : le pipeline Gmail peut démarrer. »
- [x] **Cartographie des expéditeurs** (dry-run, 432 PJ / 205 mails depuis sept. 2025) : source `ot_transport` = **QUALITAIR** (`qualitairsea.com`, Lucie Bonnet / Aline Le Provost / Julien Jenck). Le gros du volume (114 « technicien qualité », interne tb-groupe, DHL courrier) n'alimente pas le transport maritime.

- [x] **Fetch QUALITAIR borné au 31/12/2025** (décision 22/07) : 398 PJ téléchargées, 0 erreur, jusqu'au 02/01/2026.
- [x] **parse_bl** : 334 enregistrements → `data/PJ/_parsed.json` (202 avec conteneur, 74 BL ; ETD 4 / ETA 2 — extraction faible, cf. chantier ci-dessous).
- [x] **OCR chinois ajouté** : `chi_sim` + `chi_tra` (fournisseurs Chine / TB China). `parse_bl` supporte `--ocr-lang "eng+fra+chi_sim"`.
- [x] **✅ 1er WRITE PROD** : `load_ot_gmail` COMMIT → 202 conteneurs upsert (COALESCE). `achat.ot_transport` : 90 → **127 conteneurs** (100 avec ETD, 99 avec ETA, préservés du fichier maritime). Write-path Gmail→prod prouvé.

- [x] **✅ AUTOMATISATION PJ** : script `deploy/run_gmail_etl.ps1` (preflight-gated : skip propre si VPN/DWH down) + tâche planifiée Windows `FUSEAU_Gmail_ETL` (toutes les 2h, 08h–18h, jours ouvrés inclus, sous session ouverte, sans admin). Testé de bout en bout (COMMIT 202 conteneurs). **Tourne sans Cowork → le PC peut être rendu.** Logs : `logs/gmail_etl_AAAAMMJJ.log`.

**⏭️ Prochaines étapes**
- [ ] **CORPS de mail → `achat.commande`** (partie non déterministe) : à trancher — soit **tâche planifiée Cowork** (extraction LLM via `achatanalyser-mail`, nécessite Cowork ouvert/connecté sur le poste), soit **parseur déterministe** à écrire (couverture limitée mais 100% autonome). Non livré aujourd'hui.
- [ ] Optimiser `parse_bl` : ne parser que les PJ nouvelles (aujourd'hui re-parse tout le dossier ~4 min/run).
- [ ] **Chantier `parse_bl` extract_table** (cf. `TASKS.md`) : l'ETD/ATD/ETA est dans un tableau que `extract_text()` aplati (en-tête « Chargmt Déchgmt ETD ATD ETA »). Lire via `extract_table`, re-parser (`--ocr-lang eng+fra+chi_sim`), re-run `load_ot_gmail` (COALESCE enrichit).
- [ ] Élargir aux autres expéditeurs BL/transport une fois QUALITAIR calé.
- [ ] Commit `TASKS.md` + `TASKS_POSTE_MARLENE.md` recalés (depuis PowerShell Windows).

**⚙️ Config poste (mémo)**
- venv : `.venv311\Scripts\python.exe`. Tesseract : `%LOCALAPPDATA%\Programs\Tesseract-OCR`. Poppler : `%LOCALAPPDATA%\Programs\poppler\poppler-26.02.0\Library\bin`.
- Plancher d'ingestion par défaut = `after:2025/09/01` (config) ; borné aujourd'hui via `--since 2025-12-31`.

---

## 🎯 Objectif session 21/07

**Capter les pièces jointes fournisseurs de la boîte `achat.import`** (BL, proforma, factures,
packing lists) → les parser → alimenter `achat.ot_transport` (pattern A, découplé du full-refresh).
C'est la dernière brique de l'ETL Gmail avant la deadline du 31/07 (départ d'Andréa).

> Contexte à jour (fait le 20/07, déjà en prod) : correction du calcul de retard déployée,
> suivi maritime chargé (`ot_transport` 87 → 90), code poussé sur GitHub. Détails :
> `docs/plan_action.md` section « Session 20/07 ».

---

## 0. Pré-vol (à faire dans l'ordre en début de session)

1. [ ] **VPN Stormshield actif** (sinon DWH Azure injoignable → `ETIMEDOUT`).
2. [ ] `cd C:\Users\mmontbrizon\Documents\Claude\Data-Achat`
3. [ ] **`git pull`** → ⚠️ ESSENTIEL : ramène tout le code du 20/07 (retard, rollover maritime, `parse_bl`, `load_ot_gmail`, crawl Drive, `google_auth`). Le poste était figé au 29/06.
4. [ ] venv Python **3.11** activé + `pip install -r requirements.txt -r requirements-gmail.txt` si besoin.
5. [ ] **OCR installé** : `tesseract-ocr` (+ langue `fra`) et `poppler` (binaires système). Sans eux, les BL/proformas scannés ressortent vides. *(à vérifier : `tesseract --version`)*
6. [ ] Cowork ouvert, connecteur **Gmail** sur `achat.import@tb-groupe.fr`.
7. [ ] `python run_api.py` → `http://127.0.0.1:5050/api/health` = `write_enabled:true` + DWH connecté.
   - Port 5050 occupé ? `Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'run_api|spawn_main' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }`
8. [ ] **Pré-vol automatique** : `python -m src.scripts.gmail.preflight_gmail` → contrôle en 10 s le token Gmail, Tesseract, Poppler, la synchro git et le DWH. Vert partout = go.

> ⚠️ **OCR (Tesseract + Poppler)** : à installer en tout début de session (Marlène absente aujourd'hui, ça n'a pas pu être fait). C'est le seul prérequis que `git pull` ne règle pas. Le preflight le signalera en rouge tant que ce n'est pas fait.

---

## 1. Pipeline Gmail (PJ → ot_transport) — le cœur de la session

### 1.0 Capter d'abord les expéditeurs fournisseurs (on ne les connaît pas encore)

La liste des domaines fournisseurs n'est PAS connue d'avance : il faut la déduire de la boîte
`achat.import` elle-même. Deux façons :

- Dans Gmail (poste Marlène), rechercher `has:attachment filename:pdf newer_than:6m` et relever les expéditeurs récurrents (transitaire, fournisseurs Chine, DEKRA, labo).
- Ou lancer un fetch large en dry-run puis affiner :
  ```powershell
  python -m src.scripts.gmail.fetch_attachments --query "has:attachment filename:pdf newer_than:6m" --dry-run
  ```
  → le dry-run liste les mails/PJ trouvés avec leur expéditeur, sans rien télécharger. On note les domaines, on construit la `--query` ciblée, on la **fige ici** pour les prochaines sessions.

> Connu à ce stade : `from:qualitairsea.com` (transitaire QUALITAIR). À compléter : TB China, fournisseurs, `dekra.com`.

### 1.1 Pipeline (une fois la `--query` établie)

```powershell
# 1. Lister les PJ sans rien télécharger (re-consent si token expiré, une fois)
python -m src.scripts.gmail.fetch_attachments --query "<REQUETE EXPEDITEURS>" --dry-run

# 2. Télécharger réellement les PDF dans data/PJ
python -m src.scripts.gmail.fetch_attachments --query "<REQUETE EXPEDITEURS>"

# 3. Parser les BL -> JSON
python -m src.scripts.gmail.parse_bl --folder data/PJ --out data/PJ/_parsed.json

# 4. Charger dans achat.ot_transport (dry-run PUIS commit)
python -m src.scripts.gmail.load_ot_gmail --file data/PJ/_parsed.json --dry-run
python -m src.scripts.gmail.load_ot_gmail --file data/PJ/_parsed.json
```

⚠️ Le filtre par label Gmail NE marche pas, cibler par expéditeur (sinon un mail non couvert est ignoré en silence).

Nommage des PJ : suivre les règles du **sondage rempli par Andréa** (`Sondage_Organisation_PJ_FUSEAU.docx`, PJ du mail du 30/06) — conventions par type de doc (PO, PI, PS, BL, PL, CI, ARTWORK, rapports inspection/analyse).

---

## 2. Après le run

- [ ] Vérifier dans FUSEAU (onglet Prévisionnel/Retards) que les ETD/ETA remontent.
- [ ] Valider/affiner `parse_bl` sur un vrai BL QUALITAIR de `data/PJ` (regex calées sur un seul exemple documenté).
- [ ] **Commit depuis le poste Windows** (jamais depuis le sandbox) : `git add ... ; git commit ... ; git push`. Messages en FR (Conventional Commits, corps pédagogique, zéro tiret cadratin).

---

## 3. Pièges du poste Marlène (à connaître avant d'agir)

- **`KEY_VAULT_NAME` vide** dans `config\.env` → credentials lus depuis `.env` (`PG_USER=platform_team`). Ne jamais forcer un client Key Vault ici.
- **DDL interdit depuis ce poste** : `platform_team` a `SELECT/INSERT/UPDATE` sur `achat.commande` mais pas de DDL/DELETE. Toute migration de schéma se fait depuis le poste Antho (owner des tables = son login perso). *(Bascule d'ownership vers `platform_team` en cours, cf. pérennisation infra.)*
- **Python 3.11 obligatoire** (le poste était en 3.13 → cassait `sqlalchemy`).
- Secrets protégés par `.gitignore` (`credentials.json`, `client_secret*`, `token.json`) — ne jamais committer.
- **KPI retard « suspect » = normal** : la sortie actuelle montre beaucoup de lignes « en retard » (point d'investigation ouvert sur `etd_confirme`), ce n'est pas un bug de la session, ne pas essayer de le « corriger » à la volée.

---

## 4. Historique / décisions liées au poste

- (29/06) Déploiement terminé : `/api/health` write_enabled:true. Invitation GitHub acceptée. Consentement Gmail fait (token en cache).
- (30/06) Runtime figé Python 3.11 ; filtrage Gmail par `--query` expéditeur (label KO).
- (20/07) Code du projet poussé sur `origin/main` (6 commits) → `git pull` sur ce poste ramène tout à jour. Retard corrigé + maritime chargé en prod.

> Voir aussi : `TASKS.md` (suivi global), `docs/plan_action.md` (plan stratégique + Session 20/07), `docs/sources_gsheet_drive.md` (cartographie des sources).
