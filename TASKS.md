# TASKS — FUSEAU / Data-Achat

> Suivi déploiement poste Marlène + branchement Gmail. Maj 2026-06-29.
> Runbook : `docs/20260629_FUSEAU_DeploiementPosteMarlene_Cowork_v1.md`

## Déploiement poste Marlène (en cours)

- [ ] git clone/pull + `pip install -r requirements.txt`
- [ ] `config\.env` renseigné (platform_team, KEY_VAULT_NAME vide)
- [ ] VPN Stormshield + `python run_api.py` → `/api/health` (db connected, write_enabled)
- [ ] GRANT INSERT/UPDATE platform_team sur achat.commande (depuis poste Antho, admin) — `sql/20260629_grant_platform_team_commande.sql`

## Branchement Gmail (connecteur Cowork — boîte Marlène)

- [ ] Label Gmail `Achats/Fournisseurs` + filtre auto expéditeurs
- [ ] Réinstaller skill `achat-gmail-dwh` corrigé — `docs/20260629_FUSEAU_SkillCorrige_achat-gmail-dwh.md`
- [ ] 1er run MANUEL du pipeline (contrôle lignes écrites + incohérences)
- [ ] Tâche planifiée 2h (`0 8-18/2 * * 1-5`) après validation
- [ ] Mesurer PO IMPORT sans fil retrouvé chez Marlène → arbitrer accès Andréa avant 31/07

## Config Cowork Marlène

- [x] Plugin achat-gmail-pipeline installé
- [x] Connecteur Gmail connecté
- [x] CLAUDE.md projet présent
- [ ] Vérifier profil ton/email : `C:\Users\mmontbrizon\Desktop\Claude\Utility\profil_ton_email_marlene.md`
- [ ] Vérifier connecteurs Drive/Agenda pointent sur ses comptes

## Branchement sources réelles Andréa (mail 25/06 — cibles par onglet)

> Accès Drive ET serveur `\\Srv-files-pom\partage\ADA\METIER\SUIVI CDES IMPORT\2026\`.
> Serveur = source faisant foi (MAJ manuelle Andréa, AD+VPN) ; Drive = copie pour itérer vite (POC).
> **Une seule source de vérité par fichier — ne pas brancher Drive + serveur sur la même table.**

- [ ] **Onglet Artwork** ← `LIS-CON-28-0 Suivi des artworks-import` (gsheet `1FTr2nl…J4Jrc`, Drive *Design et Achat*). Clé = Référence. Filtrer les lignes #N/A.
- [ ] **Onglet Prévisionnel/Retards** ← `SUIVI MARITIME TARRERIAS 2026` (gsheet `1hP73oiv…ccfW` / serveur `TRANSITAIRE`) → table `achat.ot_transport`. Clé = CONTENEUR. ⚠ exploser COMMANDE multi-PO ("/"), parser dates mois anglais sans année, 2 colonnes ETA, ignorer le calendrier hebdo en bas. **Débloque le calcul retard sur ETA réel.**
- [ ] **Onglet Qualité** ← 3 sources : `SUIVI DES ANALYSES` (gsheet `1lE9te1…Jzi-c`, Drive *Qualité et achat*, clé Ref+PO FRS) → `achat.qualite` ; Inspections DEKRA + Analyses labo GDD (Drive *Purchasing department* / serveur `ANALYSES ET INSPECTIONS`) → lien rapport depuis statut FAIL.
- [ ] Choisir Drive vs serveur par fichier et figer la source de vérité dans le code ETL.

## Hors périmètre immédiat (rappel)

- PJ Gmail (PDF proforma/BL) : Plan A `fetch_attachments` (OAuth) / Plan B n8n — non couvert par le connecteur Cowork
- ~~Ingestion SUIVI MARITIME (ETD/ETA réels) : attend accès dossier transitaire~~ → **levé le 25/06** (Andréa a partagé l'accès, voir section branchement ci-dessus)
