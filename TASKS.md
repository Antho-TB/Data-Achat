# TASKS — FUSEAU / Data-Achat

> Suivi déploiement poste Marlène + branchement Gmail. Maj 2026-06-29 ~16h.
> Runbook : `docs/20260629_FUSEAU_DeploiementPosteMarlene_Cowork_v1.md`

## Déploiement poste Marlène ✅ TERMINÉ (29/06)

- [x] Dossier sur C:\Users\mmontbrizon\Documents\Claude\Data-Achat
- [x] `config\.env` aligné (platform_team, KEY_VAULT_NAME vide ; creds perso Antho retirés)
- [x] `pip install -r requirements.txt` (+ SQLAlchemy remonté en 2.0.51 pour Python 3.13)
- [x] `/api/health` = db connected, **write_enabled:true**
- [x] GRANT INSERT/UPDATE platform_team sur achat.commande (via Antigravity)

> ⚠️ Dette technique : poste en Python 3.13, requirements épingle sqlalchemy==2.0.30 (cassé en 3.13).
> Contourné par 2.0.51. À régulariser (assouplir requirements ou installer Python 3.11).

## Plan A — PJ Gmail (récupération des PDF) ✅ PRÊT côté technique (29/06)

- [x] Gmail API activée (projet GCP DataAchat / org tb-groupe)
- [x] OAuth ID client « Application de bureau » → `config\credentials.json` (validé type installed)
- [x] Librairies Gmail installées (`requirements-gmail.txt`)
- [x] Secrets protégés (.gitignore : credentials.json, client_secret*, token.json)
- [x] Consentement Google fait (token.json en cache)
- [x] Requête par EXPÉDITEUR (option `--query` ajoutée ; le filtre par label ne marchait pas — labels non appliqués)
- [x] Téléchargement réel validé : 23 PDF QUALITAIR (BL, embarquement, packing, factures, DAU) dans data/PJ
- [x] ✅ **BOUT EN BOUT PROUVÉ** : lecture `BL-SZSE2606480` → PO 00017281/00017639, conteneur TGBU2004021,
      ETD (on board) 05/06/2026, Bonly → GDD, Shekou → Fos-sur-Mer. Le PO (absent des corps de mail) EST dans la PJ.
- [ ] Parseur PDF dédié (BL / confirmation d'embarquement → JSON : n_bl, n_conteneur, po_number, etd_reel, eta)
- [ ] Mapper vers achat.commande (UPDATE par PO) — d'abord en base TEST dtpf_sylob_test
- [ ] Élargir périmètre expéditeurs (dekra.com, TB China) + gérer l'OCR pour les PDF scannés

## Write ETD/ETA → achat.commande (échelon 4, après test env)

- [x] Script `src/scripts/gmail/apply_etd_eta.py` (modes --check / --dry-run / --file)
- [x] Voie d'écriture validée (Windows PowerShell + platform_team) ; dry-run OK
- [ ] Normalisation des PO (les PO mail ne matchent pas tels quels) + table fournisseurs
- [ ] 1er write réel (en base de TEST d'abord — voir échelon 3)

## AiOps — environnements & GitHub

- [ ] **GitHub (échelon 2)** : pousser le travail validé. Identité Git réglée (Marlène),
      .tmp nettoyés. Bloqué tant que Marlène n'a pas accepté l'invitation collaborateur.
      → on garde l'invitation, on abandonne la clé de déploiement.
- [ ] **Env de test (échelon 3)** : base `dtpf_sylob_test` existe → créer `config/.env.test`
      + garde-fou anti-prod. Tester les writes là avant la prod.
- [ ] Réconcilier avec ce qu'Antigravity a poussé (`.agents/AGENTS.md`) avant tout push.

## ⏳ À FAIRE — MARLÈNE (laissé par Antho, 29/06)

1. **Accepter l'invitation GitHub** (mail de noreply@github.com « Antho-TB invited you »)
   → créer un compte GitHub avec `achat.import@tb-groupe.fr`, puis accepter.
2. **Remplir le tableau de correspondance fournisseurs** : `Correspondance_Fournisseurs_FUSEAU.xlsx`.
3. **Remplir le sondage organisation des PJ** : `Sondage_Organisation_PJ_FUSEAU.docx`.
4. **Lancer le consentement Gmail** (une fois, ouvre le navigateur) :
   ```
   cd C:\Users\mmontbrizon\Documents\Claude\Data-Achat
   python -m src.scripts.gmail.fetch_attachments --dry-run
   ```
   → se connecter avec `achat.import@tb-groupe.fr`, autoriser (lecture seule). Liste les PJ, ne télécharge rien.

## Config Cowork Marlène

- [x] Plugin achat-gmail-pipeline installé (+ skill achat-gmail-dwh corrigé v0.2.0)
- [x] Connecteur Gmail connecté · CLAUDE.md projet présent
- [ ] Vérifier profil ton/email + connecteurs Drive/Agenda

## Décisions actées (29/06)

- Lecture seule sur Gmail (pas de label posé ; ingestion tracée côté DWH).
- Source Excel : copie FIGÉE pour le POC, bascule prod en dernière minute.
- Write-path Gmail : écriture directe dans achat.commande (droits platform_team étendus).
- Boîte cible : Marlène pour l'instant ; arbitrer accès Andréa avant 31/07.
