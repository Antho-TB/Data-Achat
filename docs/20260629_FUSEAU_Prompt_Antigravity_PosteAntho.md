# Prompt Antigravity — Tâches FUSEAU sur le poste Antho (2026-06-29)

> Copiez tout le bloc ci-dessous dans Antigravity. Il est auto-suffisant (ne suppose pas
> le contexte de la conversation Cowork). Les étapes « HUMAIN » ne sont pas automatisables
> par l'agent (console web, VPN, consentement OAuth, réglages Cowork) — elles sont signalées.

---

## CONTEXTE

Projet **FUSEAU** : POC d'ERP Achat import de TB Groupe. ETL Python (Excel/Sylob) → DWH Azure
PostgreSQL (schéma `achat`), API FastAPI + frontend. Repo local sur mon poste :
`C:\Users\abezille\dev\Data-Achat` (branche `main`). Le DWH n'est joignable que via **VPN
Stormshield**. J'ai un accès **admin** au DWH (login `myreport`/admin) et `az login` configuré.

On déploie FUSEAU sur le poste d'une utilisatrice métier (Marlène) et on branche sa boîte
Gmail sur l'ETL via le connecteur Gmail de Cowork. **Ce prompt couvre uniquement ce que JE
dois faire sur MON poste (Antho).**

Décisions actées le 29/06 :
1. Le flux Gmail écrira **directement dans `achat.commande`** → il faut **étendre les droits**
   du rôle `platform_team` (qui aujourd'hui n'a que SELECT partout + INSERT/UPDATE sur
   `commande_annotation` et `artwork`).
2. Boîte cible = Marlène pour l'instant.

Coordonnées DWH : host `psql-dtpf-psql-prod.postgres.database.azure.com`, port `5432`,
base `dtpf_sylob_prod`, schéma `achat`, `sslmode=require`.

## OBJECTIFS (sur mon poste)

A. Étendre les droits d'écriture de `platform_team` sur `achat.commande`.
B. Committer/propager les livrables de déploiement déjà rédigés (runbook, SQL, skill corrigé, TASKS).
C. Régénérer et préparer le skill `achat-gmail-dwh` corrigé pour réinstallation.
D. (Optionnel) Initialiser le projet Google Cloud / OAuth du « Plan A » (téléchargement des PJ PDF).

---

## TÂCHE A — GRANT platform_team (prérequis du write-path Gmail)

1. **HUMAIN** : activer le VPN Stormshield.
2. Vérifier la présence du fichier `sql\20260629_grant_platform_team_commande.sql`. S'il
   n'existe pas, le créer avec ce contenu :
   ```sql
   GRANT INSERT, UPDATE ON achat.commande TO platform_team;
   GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA achat TO platform_team;
   ```
3. L'exécuter **avec mon login admin** (pas `platform_team`, qui ne peut pas s'auto-accorder).
   Si `psql` est disponible :
   ```powershell
   psql "host=psql-dtpf-psql-prod.postgres.database.azure.com port=5432 dbname=dtpf_sylob_prod user=<ADMIN> sslmode=require" -f sql\20260629_grant_platform_team_commande.sql
   ```
   (Le mot de passe admin/myreport peut être récupéré via Key Vault `kv-dtpf-prod` si `az login`
   est actif — secrets `psql-prod-sylob-myreport-login` / `psql-prod-sylob-myreport-password`.)
4. **Vérifier** le résultat (attendu : SELECT, INSERT, UPDATE) :
   ```sql
   SELECT grantee, privilege_type
   FROM information_schema.role_table_grants
   WHERE table_schema='achat' AND table_name='commande' AND grantee='platform_team';
   ```
> NE PAS accorder TRUNCATE/DELETE/DROP à platform_team. Les scripts destructeurs restent admin.

## TÂCHE B — Propager les livrables dans le repo

Ces fichiers existent déjà sur le partage `A:\DATA\PARTAGE\Data-Achat` ; s'assurer qu'ils sont
présents dans le repo git local et les committer :
- `docs\20260629_FUSEAU_DeploiementPosteMarlene_Cowork_v1.md` (runbook consolidé)
- `sql\20260629_grant_platform_team_commande.sql`
- `docs\20260629_FUSEAU_SkillCorrige_achat-gmail-dwh.md` (SKILL.md corrigé)
- `deploy\setup_poste_marlene.ps1` (script de mise en place poste local Marlène)
- `TASKS.md`

Commit suggéré :
```powershell
cd C:\Users\abezille\dev\Data-Achat
git add docs/20260629_FUSEAU_* sql/20260629_grant_platform_team_commande.sql deploy/setup_poste_marlene.ps1 TASKS.md
git commit -m "FUSEAU: deploiement poste Marlene + write-path Gmail (grant platform_team) + skill corrige"
git push
```
> Vérifier que `config\.env`, `credentials.json`, `token.json` restent **gitignorés** (jamais committés).

## TÂCHE C — Skill `achat-gmail-dwh` corrigé

Le skill installé est périmé (auth Key Vault au lieu de `.env`, colonnes `date_etd/type_mail/source`
au lieu de `etd_confirme/etd_reel/eta`). La version corrigée est dans
`docs\20260629_FUSEAU_SkillCorrige_achat-gmail-dwh.md`.

1. Localiser le dossier source du plugin `achat-gmail-pipeline` (skill `achat-gmail-dwh`) dans le repo.
2. Remplacer son `SKILL.md` par le contenu corrigé (DDL réel + auth via la classe `Config`/`.env`
   + UPSERT sur `(po_number, code_article)` + `source='gmail'`).
3. Reconstruire le `.plugin` si applicable.
4. **HUMAIN** : réinstaller le skill via **Cowork > Paramètres > Capabilities** (le cache de
   session est en lecture seule).

## TÂCHE D — (Optionnel) Plan A : projet Google Cloud / OAuth (PJ PDF)

> Le connecteur Cowork lit le texte des fils mais ne télécharge pas les PJ PDF (proforma/BL).
> Le Plan A couvre ce besoin. À ne faire que si on veut les PJ maintenant.

1. **HUMAIN** (console web https://console.cloud.google.com) :
   - Projet dédié (ex. `tb-fuseau-achats`) → APIs & Services > Library > **Gmail API** > Enable.
   - OAuth consent screen : User type **Internal**, app `FUSEAU Achats`, support `a.bezille@tb-groupe.fr`,
     scope `.../auth/gmail.readonly`.
   - Credentials > Create credentials > OAuth client ID > **Desktop app** → Download JSON.
2. Renommer le JSON en `credentials.json` et le placer dans `config\` (gitignoré).
3. Le **premier consentement interactif** (`python -m src.scripts.gmail.fetch_attachments --dry-run`)
   doit être lancé **sur le poste de Marlène avec SON compte Google** — pas sur mon poste.

---

## CRITÈRES DE VALIDATION

- [ ] A — `role_table_grants` renvoie SELECT, INSERT, UPDATE pour platform_team sur achat.commande.
- [ ] B — Les 5 livrables sont committés/poussés ; aucun secret committé.
- [ ] C — `SKILL.md` corrigé en place, plugin reconstruit, réinstallé via Capabilities.
- [ ] D — (si fait) `config\credentials.json` présent sur le poste cible, consentement à faire chez Marlène.

## CONTRAINTES

- Le bash/agent ne peut pas atteindre le DWH sans VPN actif (Windows).
- Ne jamais committer `config\.env`, `credentials.json`, `token.json`.
- Ne pas exécuter d'écriture Gmail automatique tant que le skill corrigé n'est pas réinstallé
  ET que le GRANT (Tâche A) n'est pas appliqué.
