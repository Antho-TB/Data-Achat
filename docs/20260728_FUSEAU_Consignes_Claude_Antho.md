# FUSEAU — Consignes pour le Claude du poste d'Antho (à committer)

> Rédigé le 28/07/2026 depuis le poste de Marlène, après mise à jour GitHub + application de migrations + ouverture de l'accès Andréa.
> **Ce fichier est à committer/pusher depuis le poste d'Antho** (jamais depuis le poste de Marlène : un commit local y casse le `git pull --ff-only` de l'auto-sync). Une fois traité, ranger dans `docs/`.

## Contexte
Session du 28/07 sur le poste de Marlène : `git pull` de `dd5d57f` → `cb8404b` (48 commits), 3 migrations appliquées, API redémarrée, accès LAN Andréa préparé. Restent des actions qui exigent soit le rôle propriétaire DWH, soit des droits admin Windows, soit une correction à la source du dépôt.

## 1. `.gitignore` — FAIT (corrigé à la source le 28/07)
L'API écrit `deploy/logs/api_AAAAMMJJ.log.err`. L'extension `.log.err` n'est **pas** couverte par le motif `*.log`, donc `git status` n'était jamais vide → l'auto-pull de `run_api.py` s'annulait à chaque redémarrage (`[GIT] [ECHEC] Modifications locales`).
- **Corrigé** : `deploy/logs/` ajouté au `.gitignore` **versionné** et poussé sur `main` — tous les postes (Andréa, serveur Samuel) en bénéficient désormais.
- Le contournement local `.git/info/exclude` du poste Marlène devient redondant (sans effet de bord, peut rester).
- Rien à faire ici, point conservé pour traçabilité.

## 2. Migration SQL restante — `sql/20260728_grant_articles3.sql` — ✅ FAIT
**Appliquée le 28/07 vers 13h40 depuis le poste d'Antho**, avec le rôle propriétaire
`dtpf_sylob_myreport_prod` (mot de passe tiré du Key Vault au moment de l'exécution,
jamais affiché). Le constat de ce document était juste, l'action a simplement été
faite en parallèle de sa rédaction.

Vérifié depuis le compte applicatif : `SELECT count(*) FROM public.articles3` renvoie
39 531 lignes / 33 061 articles distincts, et le log `[ATTENTION] public.articles3
inaccessible` a disparu. La recherche article interroge désormais le référentiel
Sylob : « couteau » remonte des codes `Comp0740009` et `Prod0740054`, absents de
`achat.produit`.

- **Déjà appliquées le 28/07 (compte anthony_bezille, OK)** : `20260727_reception_sylob.sql`, `20260728_commande_enrichissement.sql`, `20260728_paiement_annotation.sql`.
- Rien à refaire. Point conservé pour traçabilité.

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

## 5. Persistance de l'API (tâche planifiée absente) — constat retenu
Le runbook `docs/20260728_FUSEAU_AccesLAN_Andrea_Runbook.md` supposait une tâche planifiée `FUSEAU-API` avec redémarrage auto. Sur le poste de Marlène **elle n'existe pas** : `run_api.py` tourne en process manuel. Conséquence : l'API ne redémarre pas seule après reboot ou fermeture de session.

**Corrigé côté doc le 28/07** : le runbook et le README affirmaient tous deux que l'API tournait en tâche planifiée. C'était faux, l'installation via `deploy\install_service_windows.ps1` n'a jamais été jouée sur ce poste. Le runbook propose désormais les deux cas de figure (tâche présente ou process manuel) et l'étape d'installation de la tâche.

Décision à prendre : installer la tâche sur le poste de Marlène, ou considérer que ça ne vaut pas le coup à trois semaines du serveur de Samuel et assumer le lancement manuel. Dans le second cas, prévenir Andréa que l'accès dépend d'un lancement par Marlène.

## 6. Fichiers locaux sortis du dépôt (poste Marlène)
Déplacés dans `C:\Users\mmontbrizon\Documents\Claude\_FUSEAU_hors_depot\` (ils bloquaient l'auto-pull car non suivis) :
- `config/.env.bak_20260727` : sauvegarde d'un `.env` (contient des secrets en clair) → à supprimer avant restitution du poste si plus utile.
- `deploy/install_service_v2.ps1` : script d'install v2 non versionné → à réviser puis committer dans `deploy/` s'il fait référence, sinon écarter.

## Rappels
- Ne jamais committer **sans pousser** depuis le poste de Marlène (un commit local non poussé casse le `pull --ff-only` ; un commit poussé est sûr).
- `achat.commande` / `achat.qualite` en full-refresh : écrire uniquement via `commande_annotation` / `commande_enrichissement`.
- IP LAN actuelle du poste Marlène : `192.168.104.144` (Wi-Fi) — peut changer ; envisager une réservation DHCP ou le passage serveur.
