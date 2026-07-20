# Poste Marlène — Brief de session (FUSEAU / Data-Achat)

> But : tout ce qui ne peut se faire QUE depuis le poste de Marlène (sa session Gmail
> `achat.import@tb-groupe.fr`, son Cowork, son accès réseau/VPN).
> Poste : `C:\Users\mmontbrizon\Documents\Claude\Data-Achat` · Python **3.11** (venv) · VPN Stormshield requis.
> Dernière MAJ : **2026-07-20** (par Antho depuis son poste). Prochaine session prévue : **21/07**.

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

---

## 1. Pipeline Gmail (PJ → ot_transport) — le cœur de la session

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

**`<REQUETE EXPEDITEURS>` à figer avec Antho** (le filtre par label NE marche pas, il faut cibler par expéditeur, sinon un mail non couvert est ignoré en silence). Base connue :
`from:qualitairsea.com OR from:dekra.com` → **à compléter** : TB China, principaux fournisseurs.

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
