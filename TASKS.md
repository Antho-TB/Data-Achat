# TASKS — FUSEAU / Data-Achat

> Suivi déploiement poste Marlène + branchement Gmail + sources Andréa. Maj 2026-06-30.
> Runbook : `docs/20260629_FUSEAU_DeploiementPosteMarlene_Cowork_v1.md`

## Déploiement poste Marlène ✅ TERMINÉ (29/06)

- [x] Dossier sur C:\Users\mmontbrizon\Documents\Claude\Data-Achat
- [x] `config\.env` aligné (platform_team, KEY_VAULT_NAME vide ; creds perso Antho retirés)
- [x] `pip install -r requirements.txt` (+ SQLAlchemy remonté en 2.0.51 pour Python 3.13)
- [x] `/api/health` = db connected, **write_enabled:true**
- [x] GRANT INSERT/UPDATE platform_team sur achat.commande (via Antigravity)

> ⚠️ Dette technique : poste en Python 3.13, requirements épingle sqlalchemy==2.0.30 (cassé en 3.13).
> Décision 30/06 : venv Python 3.11 sur les 2 postes + bump `SQLAlchemy>=2.0.36,<2.1` ; migrer vers `uv` (gère version Python + lock). Docker = au passage serveur.

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
- [~] Parseur PDF dédié — **scaffold livré** `src/scripts/gmail/parse_bl.py` (texte pdfplumber + fallback OCR, regex conteneur/BL/ETD/ETA/PO, 11 tests OK sur fixture). RESTE : valider/affiner les regex sur un **vrai BL QUALITAIR** (data/PJ poste Marlène) + installer binaires OCR (tesseract+poppler) + exploiter la docx organisation PJ d'Andréa.
- [ ] Mapper → **`achat.ot_transport`** (UPSERT par n_conteneur, pattern A) — PAS achat.commande. Brancher le JSON de `parse_bl` sur le loader ot_transport ; tester d'abord en base TEST `dtpf_sylob_test`.
- [ ] Élargir périmètre expéditeurs (dekra.com, TB China) + gérer l'OCR pour les PDF scannés
- [ ] Documenter la **liste expéditeurs/domaines fournisseurs** comme paramètre de config `--query` (risque : expéditeur absent = mail ignoré silencieusement) ; réparer le label auto plus tard

## Write ETD/ETA → achat.commande (échelon 4, après test env)

- [x] Script `src/scripts/gmail/apply_etd_eta.py` (modes --check / --dry-run / --file)
- [x] Voie d'écriture validée (Windows PowerShell + platform_team) ; dry-run OK
- [] Normalisation des PO (les PO mail ne matchent pas tels quels) + table fournisseurs
- [ ] 1er write réel (en base de TEST d'abord — voir échelon 3)

## ✅ Contrainte UNIQUE + lignes de frais — RÉSOLU (30/06, vérifié prod)

- [x] Contrainte `uq_commande_po_article UNIQUE (po_number, code_article)` **déjà en prod** (vérifiée psql 30/06 ; l'ancien « à créer » était périmé). 636 lignes, 0 doublon (po, article) non-null.
- [x] Lignes de frais sans REF (molding fee MEN 25081) : `code_article` NULL échappait à la contrainte (NULL distinct en Postgres). → code synthétique `FRAIS-<slug(designation)>`. UPDATE prod 3 lignes (id 634-636) + patch `transform_commande` (règle miroir) pour full-refresh idempotent.
- [ ] **Porter la même règle dans le write-path Gmail** (voir décision ci-dessous) — le patch `transform.py` ne couvre QUE l'ETL Excel.

### 🔴 Décision — write-path Gmail vs full-refresh Excel

`achat.commande` = full-refresh (TRUNCATE+INSERT) par l'ETL Excel. Le snippet upsert du skill `achat-gmail-dwh` (`INSERT … ON CONFLICT`) est en tension :

- lignes INSÉRÉES par Gmail = effacées au prochain run Excel ;
- frais sans REF → `code_article` NULL → `ON CONFLICT` ne matche pas → doublons à chaque run Gmail ;
- le snippet insère une colonne **`source` qui n'existe pas** dans le DDL réel → planterait `column "source" does not exist`.

→ Modèle propre : Gmail **UPDATE par PO** (comme `apply_etd_eta.py`), pas INSERT. INSERT réservé au cas où Gmail crée des lignes neuves. À trancher + retravailler le snippet du skill avant d'activer la tâche planifiée Gmail.

## AiOps — environnements & GitHub

- [ ] **GitHub (échelon 2)** : pousser le travail validé. Identité Git réglée (Marlène),
      .tmp nettoyés. Bloqué tant que Marlène n'a pas accepté l'invitation collaborateur.
      → on garde l'invitation, on abandonne la clé de déploiement.
- [ ] **Env de test (échelon 3)** : base `dtpf_sylob_test` existe → créer `config/.env.test`
      + garde-fou anti-prod. Tester les writes là avant la prod.
- [ ] Réconcilier avec ce qu'Antigravity a poussé (`.agents/AGENTS.md`) avant tout push.

## ⏳ À FAIRE — MARLÈNE (laissé par Antho, 29/06)

> 📌 Centralisé et tenu à jour dans **`TASKS_POSTE_MARLENE.md`** (tout ce qui se fait depuis son poste).

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

## Branchement sources réelles Andréa (mail 25/06 — cibles par onglet)

> Accès Drive ET serveur `\\Srv-files-pom\partage\ADA\METIER\SUIVI CDES IMPORT\2026\`.
> Serveur = source faisant foi (MAJ manuelle Andréa, AD+VPN) ; Drive = copie pour itérer vite (POC).
> **Une seule source de vérité par fichier — ne pas brancher Drive + serveur sur la même table.**

- [~] **Onglet Artwork** ← `LIS-CON-28-0 Suivi des artworks-import` (gsheet `1FTr2nl…J4Jrc`, Drive *Design et Achat*). **PROFILÉ 30/06** → `docs/profil_artworks.md` (2 tableaux empilés ~473 lignes, 8 gotchas). **Décision actée (pattern A)** : table **`achat.artwork_statut`** (PK code_article) + vue **`v_artwork`** (merge sur code_article, statut design prioritaire) — **créées en prod**. `transform_artwork.py` **codé + tests OK** (2 blocs, dates FR, dérivation statut, dédoublonnage). RESTE (poste) : déposer export gsheet → `transform_artwork` → upsert `artwork_statut` (dry-run/COMMIT) + rebrancher l'onglet Artwork du frontend sur `v_artwork`.
- [~] **Onglet Prévisionnel/Retards** ← `SUIVI MARITIME TARRERIAS 2026` (gsheet `1hP73oiv…ccfW` / serveur `TRANSITAIRE`) → table `achat.ot_transport`. **PROFILÉ 30/06** (lu via connecteur Drive) → `docs/profil_suivi_maritime.md` (structure, mapping, 7 gotchas). Source de vérité = **gsheet POC, bascule serveur xlsx en prod** (30/06). `transform_maritime.py` **codé + 16 tests OK** (rollover année, explosion multi-PO, arrêt calendrier, skip bookings) → émet des records `load_ot_gmail`. RESTE (poste, VPN) : déposer un export gsheet→`data/_maritime.csv` (ou pointer le xlsx serveur TRANSITAIRE), puis `transform_maritime --file … --out data/_maritime.json` → `load_ot_gmail --file … --dry-run` (feuille complète) → COMMIT (à valider). Clé = CONTENEUR. **Débloque le calcul retard sur ETA réel** (vues déjà câblées sur ot_transport).
- [ ] **Onglet Qualité — #5** ← `SUIVI DES ANALYSES` (gsheet `1lE9te1…Jzi-c`, Drive *Qualité et achat*, clé Ref+PO FRS) → `achat.qualite`. À profiler/coder.
- [~] **Onglet Qualité — #1/#2** Inspections DEKRA + Analyses labo (Drive *Purchasing department* / serveur `ANALYSES ET INSPECTIONS`). **PROFILÉ 30/06** → `docs/profil_inspections_analyses.md`. Structure `<PO>/Inspection|Results of analysis/<stade>/`, nommage décodé (PO+stade+éch+DK+CA<réf>). **#2 labo = texte SPECTRO extractible (chrome/dureté/conformité, PAS d'OCR).** **Décision B actée** : tables `achat.qualite_doc` (index/lien) + `achat.qualite_analyse` (extraction) **créées en prod** ; `parse_qualite.py` (parseur nom + extracteur SPECTRO) **codé + 7 tests OK**. RESTE (poste) : crawler Drive (POC) walk TB/GDD→PO→Inspection/Results→fichiers → upsert `qualite_doc` ; extraction labo `cr_pct` fiable via pdfplumber sur PDF réel → `qualite_analyse` ; lien FAIL→URL dans l'onglet Qualité. DEKRA (#1) format à confirmer sur un PO inspecté.
- [ ] Choisir Drive vs serveur par fichier et figer la source de vérité dans le code ETL.

## Décisions actées

- (29/06) Lecture seule sur Gmail (pas de label posé ; ingestion tracée côté DWH).
- (29/06) Source Excel : copie FIGÉE pour le POC, bascule prod en dernière minute.
- (29/06) Write-path Gmail : écriture directe dans achat.commande (droits platform_team étendus).
- (29/06) Boîte cible : Marlène pour l'instant ; arbitrer accès Andréa avant 31/07.
- (30/06) Runtime Python figé en 3.11 (venv → uv) ; filtrage Gmail par `--query` expéditeur (label KO).

## Hors périmètre immédiat (rappel)

- PJ Gmail (PDF proforma/BL) : Plan A `fetch_attachments` (OAuth) / Plan B n8n — non couvert par le connecteur Cowork
- ~~Ingestion SUIVI MARITIME (ETD/ETA réels) : attend accès dossier transitaire~~ → **levé le 25/06** (Andréa a partagé l'accès, voir section branchement ci-dessus)
