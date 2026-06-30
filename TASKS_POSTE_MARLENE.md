# Poste Marlène — Tâches centralisées (FUSEAU / Data-Achat)

> But : tout ce qui ne peut se faire QUE depuis le poste de Marlène (sa session Gmail
> `achat.import@tb-groupe.fr`, son Cowork, son accès réseau). À alimenter au fil de l'eau
> pour que la prochaine prise en main du poste soit immédiate.
> Poste : `C:\Users\mmontbrizon\Documents\Claude\Data-Achat` · Python **3.11** (venv) · VPN Stormshield requis.
> Dernière MAJ : 2026-06-30.

---

## 0. Pré-vol (à chaque prise de poste)

- [ ] VPN Stormshield actif (sinon DWH Azure injoignable → `ETIMEDOUT`).
- [ ] `cd C:\Users\mmontbrizon\Documents\Claude\Data-Achat` puis `git pull` (récupérer le dernier code poussé depuis le poste Antho).
- [ ] Cowork ouvert, connecteur **Gmail** connecté sur `achat.import@tb-groupe.fr`.
- [ ] `python run_api.py` → vérifier `http://127.0.0.1:5050/api/health` = `write_enabled:true` + DWH connecté.
- [ ] Si port 5050 occupé : `Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'run_api|spawn_main' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }`

---

## 1. ✅ Initialisation poste Marlène — RÉGLÉ (obsolète, conservé pour archive)

- [x] Invitation GitHub acceptée (compte `achat.import@tb-groupe.fr`).
- [x] `Correspondance_Fournisseurs_FUSEAU.xlsx` traitée.
- [x] **Organisation des PJ** : sondage complété **par Andréa JAMET** (`a.jamet@tb-groupe.fr`, Assistante Achats), reçu le 30/06 — doc `Sondage_Organisation_PJ_FUSEAU.docx` en PJ du mail « Re: » à `achat.import`. ⏩ **À exploiter** : règles de nommage/rangement des PJ pour le parseur BL (lire la docx sur le poste Marlène).
- [x] Consentement Gmail effectué (token en cache).

---

## 2. À faire PAR Antho quand il prend le poste

- [ ] **Run pipeline Gmail (PJ → ot_transport)** — VPN actif :
  ```
  python -m src.scripts.gmail.fetch_attachments --query "from:<expéditeur>"   # le filtre par label NE marche pas
  python -m src.scripts.gmail.parse_bl --folder data/PJ --out data/PJ/_parsed.json
  python -m src.scripts.gmail.load_ot_gmail --file data/PJ/_parsed.json --dry-run   # vérifier
  python -m src.scripts.gmail.load_ot_gmail --file data/PJ/_parsed.json             # COMMIT
  ```
  → dépôt PDF dans `data/PJ`, parsing BL, upsert `achat.ot_transport`. Liste expéditeurs/domaines = param de config (sinon mail ignoré silencieusement).
- [ ] **Installer l'OCR** (BL scannés) : `tesseract-ocr` + langue `fra` + `poppler` (binaires système) ; libs Python déjà dans `requirements-gmail.txt`. Sans OCR, les BL images ressortent vides.
- [ ] **Valider/affiner le parseur** `parse_bl` sur un vrai BL QUALITAIR de `data/PJ` (regex calées sur l'exemple documenté seulement).
- [ ] **Vérifier le profil Cowork** : ton/email + connecteurs Drive/Agenda.
- [ ] **Élargir périmètre expéditeurs** : ajouter `dekra.com`, TB China au `--query`.
- [ ] Récupérer ce que Marlène a rempli (xlsx correspondance, sondage PJ) → reverser dans le repo / l'ETL.

---

## 3. Spécificités / pièges du poste Marlène

- `KEY_VAULT_NAME` **vide** dans `config\.env` → pas de Key Vault, credentials lus depuis `.env` (`PG_USER=platform_team`). Ne jamais forcer un client Key Vault ici.
- `platform_team` a `SELECT/INSERT/UPDATE` sur `achat.commande` (GRANT 29/06) mais **pas** de DDL/DELETE → toute migration de schéma se fait depuis le poste Antho (owner des tables = son login perso).
- Python **3.11** obligatoire (le poste était en 3.13 → cassait `sqlalchemy==2.0.30`). Cible : venv 3.11 + `SQLAlchemy>=2.0.36,<2.1`, migration `uv`.
- Secrets protégés par `.gitignore` (`credentials.json`, `client_secret*`, `token.json`) — ne jamais committer.

---

## 4. Historique / décisions liées au poste

- (29/06) Déploiement terminé : `/api/health` write_enabled:true.
- (29/06) Lecture seule Gmail (pas de label posé ; traçabilité côté DWH).
- (30/06) Runtime figé Python 3.11 ; filtrage Gmail par `--query` expéditeur.

> Voir aussi : `TASKS.md` (suivi global) et `docs/plan_action.md` (plan stratégique).
