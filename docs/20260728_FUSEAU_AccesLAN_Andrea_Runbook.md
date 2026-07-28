# Ouvrir l'accès FUSEAU à Andréa depuis le poste de Marlène

> **Destinataire : l'assistant Claude installé sur le poste de Marlène.**
> Rédigé le 28/07/2026 par Antho. Objectif : Andréa accède à FUSEAU depuis son
> propre poste, avec son navigateur, **sans rien installer chez elle**.
>
> ⚠️ **Une démo métier est en cours au moment où ce document est écrit.**
> L'étape 3 redémarre l'API et coupe l'application pendant environ 20 secondes.
> **Ne pas exécuter l'étape 3 sans l'accord explicite d'Antho ou de Marlène.**
> Les étapes 1, 2 et 4 sont sans impact et peuvent être préparées immédiatement.

---

## Pourquoi surtout ne pas copier le dossier sur le poste d'Andréa

La question a été posée, la réponse est non. Trois raisons, la dernière étant
rédhibitoire :

1. Le dossier pèse 315 Mo dont 294 Mo de `.venv311`, un environnement Python qui
   embarque des chemins absolus vers le poste d'origine. Copié ailleurs, il ne
   démarre pas.
2. `config/.env` contient des identifiants nominatifs et la clé d'écriture de
   l'API. Ils se retrouveraient en clair sur un second poste.
3. **Deux instances écriraient dans la même base de production.** Deux ETL
   faisant `TRUNCATE achat.commande` en même temps, deux tâches Gmail ingérant
   les mêmes mails. C'est la panne de données garantie.

FUSEAU est une application web : **une seule instance tourne, plusieurs
personnes la consultent avec leur navigateur.** C'est exactement ce que fait
déjà Marlène en ouvrant `http://127.0.0.1:5050`.

---

## Étape 1 — Constater l'état actuel (sans risque)

```powershell
cd C:\Users\<utilisateur>\dev\Data-Achat   # adapter au chemin réel du poste

# a. Sur quelle interface l'API écoute-t-elle aujourd'hui ?
Get-Content config\.env | Select-String -Pattern '^API_HOST|^API_PORT'

# b. Le port est-il déjà ouvert dans le pare-feu ?
Get-NetFirewallRule -DisplayName "*FUSEAU*" -ErrorAction SilentlyContinue |
    Select-Object DisplayName, Enabled, Direction, Action

# c. Quelle est l'adresse IP du poste sur le réseau bureau ?
Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -like '192.168.*' } |
    Select-Object IPAddress, InterfaceAlias
```

Interprétation :

- `API_HOST` absent du fichier ou égal à `127.0.0.1` → l'API n'écoute qu'en
  local, Andréa ne peut pas s'y connecter. Il faut l'étape 2.
- `API_HOST=0.0.0.0` → déjà bon, passer directement à l'étape 4.
- Aucune règle pare-feu FUSEAU → il faut l'étape 2b.

Noter l'adresse IP obtenue en (c), elle servira à l'étape 4.

---

## Étape 2 — Préparer l'ouverture réseau (sans impact sur l'application)

### 2a. Faire écouter l'API sur le réseau

Modifier `config\.env`. Si la ligne `API_HOST` existe, la remplacer ; sinon
l'ajouter :

```
API_HOST=0.0.0.0
API_PORT=5050
```

`0.0.0.0` signifie « accepter les connexions sur toutes les interfaces réseau ».
La modification ne prend effet qu'au redémarrage de l'API, donc **cette étape ne
coupe rien**.

> Ne pas toucher aux autres lignes du fichier, en particulier `PG_PASSWORD` et
> `API_KEY`. Et ne jamais committer `config\.env`, il est dans `.gitignore`.

### 2b. Ouvrir le port dans le pare-feu Windows

**PowerShell en tant qu'administrateur**, une seule fois :

```powershell
New-NetFirewallRule -DisplayName "FUSEAU API (LAN)" `
    -Direction Inbound -Protocol TCP -LocalPort 5050 `
    -Action Allow -Profile Domain,Private
```

`-Profile Domain,Private` limite l'ouverture au réseau de l'entreprise : le port
reste fermé si le poste se connecte à un réseau public.

Si la commande échoue avec un refus d'accès, c'est que la console n'est pas
administrateur. Demander à Marlène de valider l'élévation, ou passer par
l'informatique.

---

## Étape 3 — Redémarrer l'API ⚠️ COUPURE DE 20 SECONDES

**À ne faire qu'avec l'accord d'Antho ou de Marlène, jamais pendant une démo.**

L'API tourne en tâche planifiée Windows nommée `FUSEAU-API`, avec redémarrage
automatique. On la relance par la tâche, jamais en tuant le processus à la main.

```powershell
Stop-ScheduledTask  -TaskName "FUSEAU-API"
Start-Sleep -Seconds 3
Start-ScheduledTask -TaskName "FUSEAU-API"
Start-Sleep -Seconds 15

# Contrôle : l'API répond-elle et voit-elle la base ?
Invoke-WebRequest http://127.0.0.1:5050/api/health -UseBasicParsing |
    Select-Object -ExpandProperty Content
```

Attendu : `{"status":"ok","db":"connected","schema":"achat","write_enabled":true}`

Si `db` n'est pas `connected`, le VPN Stormshield est probablement tombé : le
vérifier avant de chercher plus loin.

> Note : au démarrage, `run_api.py` fait un `git pull` automatique. Si le dépôt
> du poste contient des modifications locales non commitées, le pull est annulé
> et une ligne `[GIT] [ECHEC]` apparaît dans les logs : l'application démarre
> alors sur l'ancien code. Vérifier avec `git status` le cas échéant.

---

## Étape 4 — Vérifier depuis le réseau et transmettre l'adresse

Depuis le poste de Marlène, tester l'accès par l'adresse réseau et non par
`127.0.0.1` :

```powershell
# Remplacer par l'IP relevée à l'étape 1c
Invoke-WebRequest http://192.168.x.x:5050/api/health -UseBasicParsing |
    Select-Object -ExpandProperty StatusCode
```

Attendu : `200`. Si la commande échoue ici, inutile de tester chez Andréa : le
problème est local (étape 2a non appliquée, API non redémarrée, ou pare-feu).

Puis transmettre à Andréa cette unique information :

```
http://192.168.x.x:5050
```

Elle l'ouvre dans son navigateur et met la page en favori. Rien d'autre à
installer chez elle. Le bandeau doit afficher « DWH connecté » en vert.

---

## Ce qu'Andréa peut faire, et ce qu'elle doit savoir

Elle voit **exactement les mêmes données que Marlène, en temps réel** : c'est la
même application, il n'y a qu'une seule instance.

Elle peut consulter tous les onglets, et modifier les champs prévus pour la
saisie métier : statut de retard, ETD, commentaire, et depuis le 28/07 la date
de paiement sur les onglets Prévisionnel et Conteneurs. La première écriture lui
demandera la **clé API** : Marlène la lui communiquera de vive voix, elle est
mémorisée ensuite dans son navigateur.

Deux limites à lui annoncer d'emblée pour éviter les appels :

- **L'application n'est disponible que quand le poste de Marlène est allumé et
  sa session ouverte.** C'est la limite connue de l'hébergement actuel, que le
  Windows Server de Samuel viendra lever.
- **Le VPN Stormshield doit être actif sur le poste de Marlène**, sinon le
  bandeau passe au rouge et les données ne se chargent plus.

---

## En cas d'échec

| Symptôme chez Andréa | Cause la plus probable | Vérification |
|---|---|---|
| Page inaccessible, délai d'attente dépassé | Pare-feu fermé, ou API en `127.0.0.1` | Refaire l'étape 4 depuis le poste de Marlène |
| Page inaccessible, connexion refusée | API arrêtée | `Get-ScheduledTask -TaskName "FUSEAU-API"` |
| Page qui s'affiche mais bandeau rouge | VPN Stormshield tombé | Le relancer sur le poste de Marlène |
| « Clé API invalide » à l'enregistrement | Mauvaise clé saisie | Marlène redonne la clé, Andréa réessaie |
| Page blanche ou affichage cassé | Cache navigateur après mise à jour | Ctrl+F5 chez Andréa |

Logs de l'API : `deploy\logs\api_AAAAMMJJ.log` dans le dépôt.

---

## Après le passage sur le serveur de Samuel

Cette configuration est **provisoire**. Quand le Windows Server sera livré (voir
`docs/20260727_FUSEAU_Procedure_Deploiement_WindowsServer_v1.md`), il faudra :

1. Basculer Marlène et Andréa sur l'adresse du serveur.
2. **Arrêter la tâche `FUSEAU-API` sur le poste de Marlène**, ainsi que la tâche
   `FUSEAU_Gmail_ETL`. Laisser deux instances actives en écriture sur la même
   base est le scénario de corruption à éviter absolument.
3. Retirer la règle de pare-feu devenue inutile :
   `Remove-NetFirewallRule -DisplayName "FUSEAU API (LAN)"`
