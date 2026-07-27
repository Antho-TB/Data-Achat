# FUSEAU — Passation mise en prod (poste Marlène) — 23/07

> **Pour un Claude/Cowork ouvert sur le poste de Marlène.** Tu n'as aucun contexte de la
> session qui a produit ce document — lis-le en entier avant d'agir. Objectif : faire
> arriver le code à jour (GitHub `main`, commit `f8fd29d`) sur le poste de Marlène, sans
> rien casser sur une application **déjà en production**, et vérifier que ça fonctionne.
>
> **Ce document remplace/complète** `docs/20260629_FUSEAU_DeploiementPosteMarlene_Cowork_v1.md`
> pour la partie "code applicatif". Le doc du 29/06 reste la référence pour le branchement
> Gmail (§3) et la config `.env` (§1) — ne le refais pas, contente-toi de la mise à jour du code.

---

## 1. État réel au moment d'écrire ceci

- **GitHub à jour** : `main` = `f8fd29d`, tout est poussé, rien en attente côté dépôt distant.
- **Application déjà déployée** sur le poste de Marlène (pas un premier déploiement) : tâche
  planifiée Windows `FUSEAU-API` (voir `deploy/install_service_windows.ps1`), démarre à
  l'ouverture de session, redémarre seule en cas de crash, écoute sur `127.0.0.1:5050`
  (+ port LAN ouvert pour Andréa, décision 23/07).
- **Toutes les migrations SQL de cette session ont déjà été jouées côté base par Antho**
  (login admin, poste Antho) directement sur `dtpf_sylob_prod` — **rien à rejouer côté poste
  Marlène**. En particulier `sql/20260723_suivi_dates_eta_evenements.sql` est déjà appliqué.
  Ne relance aucun script dans `sql/` depuis ce poste : le login `platform_team` utilisé ici
  n'a de toute façon pas les droits `CREATE`/`ALTER` (ça échouerait proprement, mais autant
  ne pas essayer).

## 2. ⚠️ Point non résolu — comment le code arrive-t-il sur ce poste ?

Deux mécanismes coexistent dans le repo et je (session précédente, sandbox sans accès réseau
bureau) n'ai **pas pu vérifier lequel est réellement utilisé aujourd'hui** :

1. **Partage réseau** `A:\DATA\PARTAGE\Data-Achat` → `deploy/setup_poste_marlene.ps1` fait un
   `robocopy` de ce partage vers `C:\Users\<toi>\dev\Data-Achat` (exclut `.git`, `.env`,
   secrets). **Si c'est ce chemin qui est utilisé : quelqu'un doit d'abord mettre à jour le
   contenu de `A:\DATA\PARTAGE\Data-Achat` avec le commit `f8fd29d` avant de relancer ce
   script** — sans ça tu recopieras du code périmé.
2. **Git direct** : il existe une paire de clés `deploy/marlene_deploy_key(.pub)` (clé de
   déploiement SSH) mais **elle n'est référencée nulle part dans le code ou les scripts** —
   probablement préparée pour un chantier jamais terminé. Si le poste a un `.git` fonctionnel
   avec cette clé configurée, un simple `git pull` suffit et c'est le chemin le plus fiable
   (pas de dépendance au partage réseau).

**Avant de toucher au code sur ce poste** :
```powershell
cd C:\Users\<toi>\dev\Data-Achat   # adapte le chemin réel
Test-Path .git                     # $true -> chemin git direct possible
git remote -v                      # si ça répond, tente : git pull
git log -1 --oneline               # doit finir par f8fd29d après pull
```
Si `.git` n'existe pas (repo = simple copie de fichiers, pas un clone), tu es sur le chemin
**robocopy depuis A:\** — dans ce cas, **vérifie avec Antho que `A:\DATA\PARTAGE\Data-Achat`
est à jour AVANT de lancer `deploy\setup_poste_marlene.ps1`**, sinon tu écraseras la config
locale (`.env`) avec du code obsolète (le script n'écrase pas `.env`, mais écrasera bien
`app/main.py`, `frontend/index.html` etc. avec une version périmée si la source ne l'est pas).

## 3. Procédure de mise à jour (une fois la source de code confirmée à jour)

```powershell
# 1. Arrêter proprement la tâche planifiée avant de toucher aux fichiers
Stop-ScheduledTask -TaskName "FUSEAU-API" -ErrorAction SilentlyContinue
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'run_api|spawn_main' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

# 2a. Chemin GIT (si .git présent et fonctionnel) :
git pull origin main

# 2b. Chemin ROBOCOPY (si pas de .git) -- APRES avoir confirmé A:\ à jour :
# .\deploy\setup_poste_marlene.ps1

# 3. Dépendances (au cas où requirements.txt aurait changé -- pas le cas cette session,
#    mais gratuit à vérifier) :
.venv311\Scripts\python.exe -m pip install -r requirements.txt --quiet

# 4. Relancer le service
Start-ScheduledTask -TaskName "FUSEAU-API"
Start-Sleep -Seconds 6
Invoke-RestMethod http://127.0.0.1:5050/api/health
# Attendu : status=ok, db=connected, write_enabled=true
```

## 4. Smoke test après redémarrage (ce qui est NOUVEAU cette session, à vérifier à l'écran)

- **Onglet Prévisionnel** (ordre revu 23/07) :
  1. "Échéancier de paiement" — graphique en **barres empilées par conteneur** (pas par
     tranche comme avant). Vérifier qu'il s'affiche (pas d'erreur JS console).
  2. "Mesures prévisionnelles" (inchangé).
  3. "B/L en attente ou bloqués — par conteneur puis fournisseur" (nouvelle section, table
     imbriquée conteneur → fournisseur).
  4. "Par fournisseur" (inchangé, déplacé en dernier).
- **Onglet Conteneurs** : colonnes ETA/Livraison doivent pouvoir afficher un petit point
  coloré (orange/rouge/violet) s'il y a eu des changements — **normalement aucun point
  visible aujourd'hui** (cf. §5, le pipeline qui écrit ces événements est bloqué).
- **Dashboard > Actions prioritaires** : ne doit pas planter même si aucun changement ETA
  n'existe encore (le bloc est conçu pour être silencieux dans ce cas).
- **Onglet Fournisseurs** : les doublons GUANGWEI/DIAMOND TRACK, SMART IRON/JIT GLOBAL et
  AOYAM/HIAMEA doivent apparaître fusionnés en une seule ligne chacun (22 fournisseurs au
  total, pas 24). Si l'ETL `enrich_ca.py` n'a pas encore tourné sur cette base, la fusion
  n'apparaîtra qu'après le prochain run.
- **Onglet Promo/Opé** : le filtre ne doit plus remonter que les libellés commençant par
  "OP" ou "NOUVEAU", avec une colonne Prioritaire vide.

## 5. Blocage connu — NE PAS essayer de réparer depuis ce poste

`achat.transport_evenement` (table qui doit recevoir les changements d'ETA/livraison)
appartient à `platform_team`, et même le login admin d'Antho n'est pas membre de ce rôle —
`INSERT` refusé sur `transport_evenement_id_seq` (permission denied), confirmé le 23/07.
**Ça ne casse rien** : le code gère l'échec proprement (transaction annulée), l'API et le
dashboard fonctionnent normalement, seuls les badges couleur ETA resteront vides tant que ce
n'est pas réglé. La correction nécessite l'identité admin Entra/`azure_pg_admin` — **hors
portée du poste Marlène**, à traiter par Antho séparément. Détail complet dans
`docs/plan_action.md` (section "Alertes changement ETA/livraison").

## 6. Point ouvert non bloquant (peut attendre après la mise en prod)

Sur le graphique "Échéancier de paiement" par conteneur, une partie des lignes non payées
(~1,22M$) n'a pas de conteneur renseigné dans `achat.commande` (regroupées sous "Sans
conteneur"). Analyse faite le 23/07 : la majorité (En cours/En production, ~1,12M$) est
normale — le conteneur n'est assigné qu'à l'embarquement. Une partie (31 lignes "Livrée",
~94k$) est un vrai trou de traçabilité (déjà livré mais jamais rattaché à un conteneur —
ex. PO 176529/HONGXING, PO 179321/HONGXING). Décision UX en attente (retirer ces lignes du
graphique + encart séparé, vs. garder avec drill-down cliquable) — pas encore tranchée avec
Antho, ne pas bloquer la mise en prod pour ça.

## 7. Contexte projet (mémoire embarquée dans le repo, à lire si besoin)

- `CLAUDE.md` (racine) : rôle du projet, stack, statut, coordination métier.
- `docs/plan_action.md` : source de vérité vivante — décisions actées, chantiers en cours,
  historique de session. **Section "Session 21/07" et au-delà couvre tout ce qui a été fait
  depuis le doc de déploiement du 29/06.**
- `TASKS.md` : suivi opérationnel détaillé (tickets, accès, infra).
- `docs/20260629_FUSEAU_DeploiementPosteMarlene_Cowork_v1.md` : toujours valable pour la
  config `.env`, le GRANT `platform_team` sur `achat.commande`, et le branchement Gmail.

## 8. Checklist finale

- [ ] Confirmé quel mécanisme de sync (git vs robocopy A:\) est réellement utilisé sur ce poste.
- [ ] Code à jour vérifié : `git log -1` (ou date de `app/main.py`) correspond à `f8fd29d`.
- [ ] Tâche planifiée `FUSEAU-API` redémarrée, `/api/health` OK (db connected, write_enabled true).
- [ ] Smoke test §4 fait à l'écran (Prévisionnel, Conteneurs, Fournisseurs, Promo/Opé).
- [ ] Rien touché côté SQL (`sql/`) ni côté GRANT `transport_evenement` (§5, hors portée poste Marlène).
