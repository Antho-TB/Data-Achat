# FUSEAU — Consignes pour le Claude du poste d'Antho (à committer)

> Rédigé le 28/07/2026 depuis le poste de Marlène, après mise à jour GitHub + application de migrations + ouverture de l'accès Andréa.
> **Ce fichier est à committer/pusher depuis le poste d'Antho** (jamais depuis le poste de Marlène : un commit local y casse le `git pull --ff-only` de l'auto-sync). Une fois traité, ranger dans `docs/`.

## Contexte
Session du 28/07 sur le poste de Marlène : `git pull` de `dd5d57f` → `cb8404b` (48 commits), 3 migrations appliquées, API redémarrée, accès LAN Andréa préparé. Restent des actions qui exigent soit le rôle propriétaire DWH, soit des droits admin Windows, soit une correction à la source du dépôt.

## 1. `.gitignore` — corriger à la source (sinon auto-pull bloqué)
L'API écrit `deploy/logs/api_AAAAMMJJ.log.err`. L'extension `.log.err` n'est **pas** couverte par le motif `*.log`, donc `git status` n'est jamais vide → l'auto-pull de `run_api.py` s'annule à chaque redémarrage (`[GIT] [ECHEC] Modifications locales`).
- **Contournement déjà en place sur le poste Marlène** : `/deploy/logs/` ajouté à `.git/info/exclude` (local, non versionné).
- **À faire côté dépôt** : ajouter au `.gitignore` versionné une ligne `deploy/logs/` (ou `*.log.err`) pour que tous les postes (Andréa, serveur Samuel) en bénéficient.

## 2. Migration SQL restante — `sql/20260728_grant_articles3.sql`
Non appliquée : elle exige le rôle **propriétaire** `dtpf_sylob_myreport_prod`, pas `dtpf_sylob_anthony_bezille_prod`.
- Se connecter à `psql-dtpf-psql-prod.postgres.database.azure.com:5432` / base `dtpf_sylob_prod` (SSL) avec le login `dtpf_sylob_myreport_prod` (mot de passe : secret Key Vault `psql-prod-sylob-myreport-password` du vault `kv-dtpf-prod`).
- Exécuter le `GRANT SELECT ON TABLE public.articles3 TO group_dtpf_sylob_admin_prod;`.
- Sans ce grant, la recherche article « Sylob-first » (`/api/search/article`, auto-complétion Fiche Achat) retombe silencieusement sur `achat.produit` sans jamais interroger le référentiel Sylob.
- **Déjà appliquées le 28/07 (compte anthony_bezille, OK)** : `20260727_reception_sylob.sql`, `20260728_commande_enrichissement.sql`, `20260728_paiement_annotation.sql`.

## 3. Identifiants DWH Sylob on-premise (192.168.102.41)
Aujourd'hui `get_sylob_url()` lit **uniquement** `config/.env` (pas de Key Vault, contrairement à `get_pg_url()`). Or le poste de Marlène n'a **ni** `KEY_VAULT_NAME` renseigné **ni** `az` CLI → toute la chaîne PG fonctionne via `.env` en clair, pas via Key Vault.
Deux options selon l'horizon :
- **Court terme (poste Marlène)** : ajouter dans `config/.env` (jamais commité) : `SYLOB_HOST=192.168.102.41`, `SYLOB_PORT=5432`, `SYLOB_DB=tarrerias_production_dwh`, `SYLOB_USER=dataviz-admin`, `SYLOB_PASSWORD=…`. **Le mot de passe doit être saisi localement sur le poste, jamais transmis en chat.**
- **Cible serveur dédié (Samuel)** : étendre `get_sylob_url()` pour lire Key Vault (même pattern que `get_pg_url()` / `DefaultAzureCredential`) via le compte de service `svc-dataachat` prévu. À ce moment-là, **plus aucun secret Sylob en clair** sur aucun poste — c'est bien la bonne intuition : sur le serveur dédié, les creds sortent des `.env`.

## 4. Pare-feu Windows sur le poste de Marlène (bloquant pour Andréa)
La règle inbound n'a **pas** pu être créée (console non-admin, « Accès refusé »). À exécuter dans **PowerShell admin** sur le poste de Marlène :
```powershell
New-NetFirewallRule -DisplayName "FUSEAU API (LAN)" -Direction Inbound -Protocol TCP -LocalPort 5050 -Action Allow -Profile Domain,Private
```
Tant qu'elle n'existe pas, Andréa ne peut pas ouvrir `http://192.168.104.144:5050` depuis sa machine (l'API écoute pourtant bien en `0.0.0.0:5050`, testée 200 en local).

## 5. Persistance de l'API (tâche planifiée absente)
Le runbook `docs/20260728_FUSEAU_AccesLAN_Andrea_Runbook.md` suppose une tâche planifiée `FUSEAU-API` avec redémarrage auto. Sur le poste de Marlène **elle n'existe pas** : `run_api.py` tourne en process manuel (relancé à la main aujourd'hui). Conséquence : l'API ne redémarre pas seule après reboot / fermeture de session. À installer si on veut la persistance décrite (sinon documenter que l'accès dépend de la session ouverte de Marlène).

## Rappels
- Ne jamais committer depuis le poste de Marlène (casse le `pull --ff-only`).
- `achat.commande` / `achat.qualite` en full-refresh : écrire uniquement via `commande_annotation` / `commande_enrichissement`.
- IP LAN actuelle du poste Marlène : `192.168.104.144` (Wi-Fi) — peut changer ; envisager une réservation DHCP ou le passage serveur.
