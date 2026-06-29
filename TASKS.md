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

## Hors périmètre immédiat (rappel)

- PJ Gmail (PDF proforma/BL) : Plan A `fetch_attachments` (OAuth) / Plan B n8n — non couvert par le connecteur Cowork
- Ingestion SUIVI MARITIME (ETD/ETA réels) : attend accès dossier transitaire
