# FUSEAU — Déploiement poste Marlène + branchement Gmail (connecteur Cowork)

_2026-06-29 · runbook consolidé · auteur : Anthony (lead Data/AI)_
_Remplace pour l'exécution : checklist du `20260610_FUSEAU_DeploiementProdMarlene_v1.md` (toujours valable comme référence)._

> **But.** Mettre FUSEAU en service sur le poste de Marlène (poste vierge), brancher sa
> boîte Gmail sur l'ETL via le **connecteur Gmail de Cowork**, et finaliser sa configuration
> Cowork sur le projet.
>
> **Décisions actées le 29/06 (Anthony) :**
> 1. **Write-path Gmail** = écriture directe dans `achat.commande` → on **étend les droits**
>    de `platform_team` (cf. §2). Impact gouvernance assumé.
> 2. **Boîte cible** = **Marlène** pour l'instant (connecteur Cowork déjà connecté). On
>    mesure ensuite les PO « sans fil retrouvé » pour décider d'élargir à Andréa avant le 31/07.
>
> **Ce que je ne peux pas exécuter à votre place** (réseau A:/VPN hors sandbox, poste Windows) :
> tout ce qui est `python`, `pip`, VPN, `psql`/pgAdmin, et la connexion d'un connecteur dans
> Cowork. Ces étapes sont à lancer sur le poste — elles sont détaillées ci-dessous.

---

## 1. Déploiement de l'ERP sur le poste de Marlène

Prérequis : Python 3.11, accès au repo `Antho-TB/Data-Achat`, VPN Stormshield installé.

1. **Récupérer le code** (commit ≥ `bd68bec`, branche `main`) :
   ```powershell
   cd C:\Users\<marlene>\dev
   git clone https://github.com/Antho-TB/Data-Achat   # ou git pull si déjà cloné
   cd Data-Achat
   ```
2. **Dépendances** :
   ```powershell
   pip install -r requirements.txt
   ```
3. **Config `config\.env`** (copier le modèle `config\marlene.env` du poste test, puis renseigner) :
   ```
   KEY_VAULT_NAME=            # VIDE — pas d'az login sur le poste Marlène
   PG_HOST=psql-dtpf-psql-prod.postgres.database.azure.com
   PG_PORT=5432
   PG_DB=dtpf_sylob_prod
   PG_USER=platform_team
   PG_PASSWORD=***            # mot de passe platform_team (ne jamais committer)
   PG_SSLMODE=require
   API_KEY=<même clé que le test>
   API_HOST=127.0.0.1
   API_PORT=5050
   API_RELOAD=0
   DATA_DIR=Service_Achat     # ou le partage réseau réel \\Srv-files-pom\partage\ADA\METIER\...
   ```
   > `KEY_VAULT_NAME` **vide** = aucun appel Azure ; les credentials DB viennent du `.env`.
4. **VPN Stormshield actif**, puis lancer l'API :
   ```powershell
   python run_api.py        # -> http://127.0.0.1:5050
   ```
5. **Contrôle santé** : ouvrir http://127.0.0.1:5050/api/health
   → attendu `db: connected` **et** `write_enabled: true`.
6. Si le port 5050 est tenu par un worker uvicorn orphelin (piège Windows connu) :
   ```powershell
   Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'run_api|spawn_main' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
   ```

✅ À ce stade FUSEAU tourne en lecture sur le DWH depuis le poste de Marlène.

---

## 2. Étendre les droits `platform_team` (décision write-path)

**Pourquoi.** Par défaut `platform_team` a `SELECT` partout mais `INSERT/UPDATE` uniquement
sur `commande_annotation` et `artwork`. Pour que le flux Gmail écrive **directement dans
`achat.commande`**, il faut lui accorder l'écriture sur cette table.

**Où / qui.** À exécuter **une fois**, par un rôle propriétaire du schéma `achat`
(login admin / `myreport`) — donc **depuis le poste Antho** (VPN + `az login`) ou via pgAdmin
en compte admin. `platform_team` ne peut pas se l'auto-accorder.

Fichier prêt : `sql/20260629_grant_platform_team_commande.sql`

```sql
GRANT INSERT, UPDATE ON achat.commande TO platform_team;
-- Si des INSERT s'appuient sur une séquence (clé technique) :
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA achat TO platform_team;
```

**Vérification** (après application) :
```sql
SELECT grantee, privilege_type
FROM information_schema.role_table_grants
WHERE table_schema='achat' AND table_name='commande' AND grantee='platform_team';
-- attendu : SELECT, INSERT, UPDATE
```

> ⚠️ **Gouvernance.** On ouvre l'écriture sur la table cœur depuis un poste utilisateur.
> Recommandations : conserver les scripts destructeurs (TRUNCATE/DROP) hors de `platform_team`,
> tracer chaque écriture Gmail avec `source='gmail'` + `updated_at`, et revoir ce grant à la
> sortie du POC. Le `ON CONFLICT ... DO UPDATE` (UPSERT) évite les doublons.

---

## 3. Brancher la boîte Gmail de Marlène (connecteur Cowork)

> Architecture retenue (pas d'OAuth/`fetch_attachments` ici) :
> ```
> Gmail Marlène (connecteur Cowork)
>   → search_threads (filtre fournisseurs)  → get_thread (corps)
>   → skill achatanalyser-mail (extraction structurée : PO, prix, ETD, BL...)
>   → script Python local (Windows + VPN)   → UPSERT achat.commande
> ```
> **Limite connue à garder en tête :** le connecteur Cowork lit le **texte** des fils et liste
> les pièces jointes (`attachment_ids`) mais **ne télécharge pas les PDF** (proforma/BL). Le
> téléchargement des PJ reste le chantier Plan A (`fetch_attachments`, OAuth) / Plan B (n8n) —
> **hors périmètre de ce branchement**. Ici on capte les **données de corps de mail**.

### 3.1 Préparer la boîte Gmail
- Créer le label **`Achats/Fournisseurs`** dans Gmail (= valeur par défaut `GMAIL_LABEL`).
- Ajouter un **filtre automatique** : expéditeurs TB China / transitaire / fournisseurs →
  applique le label. (Alternative : pointer `GMAIL_LABEL` vers un label existant dans `config\.env`.)

### 3.2 Vérifier le connecteur dans Cowork
- Cowork > Paramètres > Connecteurs : **Gmail = connecté** sur le compte de Marlène (déjà fait).

### 3.3 Lancer le pipeline
Dans Cowork, déclencher le skill `achat-gmail-pipeline:achat-gmail-dwh`
(« extraire les mails fournisseurs » / « alimenter la base depuis Gmail »). Le flux :
1. `search_threads` sur les fils non traités (ex. `newer_than:1d` + expéditeurs connus / label).
2. `get_thread` pour le corps de chaque fil.
3. `achatanalyser-mail` pour l'extraction structurée + détection d'incohérences vs base.
4. Génération + exécution du script Python local (UPSERT) — **via PowerShell sur le poste**,
   car le bash Cowork (Linux) n'atteint pas le DWH (VPN requis côté Windows).

> ⚠️ **Le script du skill installé est à corriger avant le premier run** (DDL périmé + auth
> Key Vault au lieu de `.env`). Voir §5 — utiliser le script aligné fourni.

### 3.4 Automatiser (optionnel, après validation manuelle)
Tâche planifiée toutes les 2h en heures ouvrées, via le skill `schedule` :
- Cron : `0 8-18/2 * * 1-5`
- Prérequis : VPN actif + Cowork ouvert sur le poste de Marlène.

---

## 4. Configurer le compte Cowork de Marlène sur le projet

| Élément | État / action |
|---|---|
| Plugin `achat-gmail-pipeline` (skills achat*) | ✅ déjà installé sur le poste Marlène |
| Connecteur Gmail | ✅ connecté (compte Marlène) |
| Connecteurs Drive / Agenda | présents dans la session — vérifier qu'ils pointent sur ses comptes |
| `CLAUDE.md` projet (`A:\DATA\PARTAGE\Data-Achat\CLAUDE.md`) | ✅ présent (rôle, stack, standards) |
| Profil ton/email | `C:\Users\mmontbrizon\Desktop\Claude\Utility\profil_ton_email_marlene.md` — vérifier présence |
| `TASKS.md` projet | ✅ créé ce jour (cf. racine repo) — suivi du déploiement |
| Skill `achat-gmail-dwh` | ⚠️ à réinstaller corrigé (§5) |

Rien d'autre à installer : le plugin et les connecteurs sont en place. Le seul correctif
bloquant est le skill `achat-gmail-dwh` (§5).

---

## 5. Correctif requis — skill `achat-gmail-dwh`

Le SKILL.md installé n'est **pas exécutable en l'état sur le poste Marlène** :

| Problème | Skill actuel | Réel poste Marlène |
|---|---|---|
| **Auth** | `DefaultAzureCredential` + Key Vault + login `myreport` | `KEY_VAULT_NAME` vide → credentials `platform_team` lus dans `config\.env` |
| **Colonnes** | `date_etd`, `type_mail`, `source` | `etd_confirme` / `etd_reel` / `eta` (pas de `date_etd`) |
| **Droits** | écrit `achat.commande` (échouait sans le grant §2) | OK **après** le GRANT du §2 |

Le SKILL.md aligné est fourni : `docs/skills_corrections/achat-gmail-dwh.SKILL.md`.
Il lit les credentials via la classe `Config` (`.env`), écrit en UPSERT sur
`(po_number, code_article)` avec les vraies colonnes, et `source='gmail'`.

**Installation :** le cache de session est en lecture seule — réinstaller le skill corrigé
via **Cowork > Paramètres > Capabilities** (ou régénérer le `.plugin`). Tant que ce n'est pas
fait, ne pas lancer l'étape d'écriture en automatique.

---

## 6. Checklist d'exécution (à cocher sur le poste)

- [ ] §1 — `git clone/pull`, `pip install`, `config\.env` (platform_team), VPN, `run_api.py`, `/api/health` OK.
- [ ] §2 — GRANT `platform_team` appliqué depuis poste Antho (admin) + vérification.
- [ ] §3.1 — label `Achats/Fournisseurs` + filtre Gmail créés.
- [ ] §5 — skill `achat-gmail-dwh` corrigé réinstallé.
- [ ] §3.3 — premier run **manuel** du pipeline (contrôler les lignes écrites + incohérences).
- [ ] §3.4 — tâche planifiée 2h activée (après validation).
- [ ] Mesure « quasi » : nombre de PO de l'IMPORT sans fil retrouvé dans la boîte Marlène → arbitrage Andréa.

---

## 7. Pièges connus (rappel)

1. **`total_prix`** (col T Excel) = SUMIF par PO répété par ligne → jamais de SUM ligne à ligne.
2. **Workers uvicorn orphelins** (Windows) : purger par `Get-CimInstance ... -match 'run_api|spawn_main'` ; `API_RELOAD=0`.
3. **DWH = VPN obligatoire** : le bash Cowork (Linux) n'atteint jamais le DWH ; les écritures passent par PowerShell local.
4. **PJ Gmail (PDF)** : non couvertes par le connecteur Cowork — chantier Plan A/B séparé.
