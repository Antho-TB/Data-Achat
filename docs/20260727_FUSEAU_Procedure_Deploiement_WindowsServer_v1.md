# FUSEAU — Procédure de déploiement sur serveur Windows Server

> **Rédigé le 27/07/2026** par Anthony Bezille (Lead Data & AI Engineer).  
> **Objectif** : Héberger FUSEAU (API FastAPI + frontend) sur un serveur dédié Windows Server toujours allumé, indépendant du poste de Marlène. Chacun (Marlène, Andréa, Maxence) y accède via son navigateur sur `http://<serveur>:5050`.

---

## 0. Ce qu'il faut valider AVANT avec Samuel

Ces points conditionnent tout le reste :

1. **Toujours allumé** : le serveur ne s'éteint pas la nuit (sinon on retombe sur le problème du poste Marlène).
2. **Réseau — accès sortants obligatoires depuis le serveur** :
   - **DWH Azure PostgreSQL** : `psql-dtpf-psql-prod.postgres.database.azure.com` port `5432` (via le lien qui remplace le VPN — à confirmer selon le segment réseau du serveur).
   - **Sylob DWH V25 (SRV-ERP-DATA)** : `192.168.102.41` port `5432`.
   - **API Google (Gmail + Drive)** : `*.googleapis.com` port `443` (pour les ETL).
3. **Réseau — accès entrant** : port `5050` ouvert au sous-réseau local (postes de Marlène / Andréa / Maxence).
4. **Compte de service** : idéalement `svc-dataachat` (ticket GLPI du 20/07) pour faire tourner le service sans session ouverte. À défaut, un compte de service dédié avec mot de passe.
5. **Python 3.11** installable sur le serveur (ou droit de l'installer).
6. **Git** installable (ou récupération du code par copie si Git interdit sur le serveur).

---

## 1. Récupérer le code

Le projet « utile » pèse ~10 Mo (le reste = environnement régénérable). Depuis un dossier de déploiement, ex. `D:\Apps` :

```powershell
cd D:\Apps
git clone https://github.com/Antho-TB/Data-Achat.git FUSEAU
cd FUSEAU
```

*Si Git n'est pas autorisé sur le serveur : copier le dossier du repo sans `.venv311`, `.git`, ni `data\` (ces trois se recréent), soit ~10 Mo.*

---

## 2. Créer l'environnement Python

```powershell
py -3.11 -m venv .venv311
.\.venv311\Scripts\python.exe -m pip install --upgrade pip
.\.venv311\Scripts\python.exe -m pip install -r requirements.txt
```

> ⚠️ **Rappel de contrainte connue** : Python 3.11 impératif (`sqlalchemy 2.0.x` casse en 3.13). Le venv fait ~290 Mo une fois installé, c'est normal.

---

## 3. Secrets & configuration (JAMAIS par Git ni par mail en clair)

Trois fichiers non versionnés à recopier manuellement depuis le poste de Marlène (`config\`) vers `config\` du serveur — via une clé USB, un partage réseau sécurisé, ou un coffre :

* `config\.env` — creds DWH, API_KEY, etc.
* `config\credentials.json` — client OAuth Google.
* `config\token.json` — jeton Gmail/Drive déjà consenti.

Puis adapter `config\.env` sur le serveur :

```ini
API_HOST=0.0.0.0
API_PORT=5050
API_RELOAD=0
CORS_ORIGINS=http://<IP-ou-nom-serveur>:5050
```
*Si les PJ doivent aller sur un partage réseau plutôt qu'en local, ajuster `DATA_DIR` / `GMAIL_PJ_DIR`.*

---

## 4. OAuth Google sur un serveur sans écran (point d'attention)

Le `token.json` existant est déjà consenti : s'il est encore valide, le copier suffit, aucune interaction navigateur nécessaire (le refresh token se renouvelle tout seul).

> ⚠️ Si le token est expiré/révoqué, le ré-consentement exige un navigateur — impossible en headless. Dans ce cas : refaire le flow OAuth depuis un poste avec navigateur, puis copier le `token.json` régénéré sur le serveur. À tester lors du 1er run ETL.

---

## 5. Pare-feu (accès des postes clients)

En PowerShell administrateur sur le serveur :

```powershell
New-NetFirewallRule -DisplayName "FUSEAU-API (LAN bureau)" -Direction Inbound `
  -Protocol TCP -LocalPort 5050 -Action Allow -RemoteAddress LocalSubnet -Profile Domain,Private
```

*Scoper au sous-réseau local (`LocalSubnet`), jamais `Any`/Internet.*

---

## 6. Faire tourner l'API en vrai service (sans session ouverte)

C'est le gain principal vs. le poste de Marlène (qui dépendait d'une session interactive). Deux options :

### Option A — NSSM (recommandée, la plus simple)
NSSM transforme n'importe quel exécutable en service Windows natif, avec redémarrage auto et logs.

```powershell
# Installer nssm (https://nssm.cc) puis :
nssm install FUSEAU-API "D:\Apps\FUSEAU\.venv311\Scripts\python.exe" "run_api.py"
nssm set FUSEAU-API AppDirectory "D:\Apps\FUSEAU"
nssm set FUSEAU-API AppStdout "D:\Apps\FUSEAU\deploy\logs\api_service.log"
nssm set FUSEAU-API AppStderr "D:\Apps\FUSEAU\deploy\logs\api_service.log"
nssm set FUSEAU-API ObjectName ".\svc-dataachat" "<mot_de_passe>"   # compte de service
nssm set FUSEAU-API Start SERVICE_AUTO_START
nssm start FUSEAU-API
```

### Option B — Tâche planifiée « que l'utilisateur soit connecté ou non »
Comme le script `install_service_v2.ps1` du repo, mais avec `New-ScheduledTaskPrincipal -LogonType Password -UserId svc-dataachat` (mot de passe stocké) au lieu de Interactive. Nécessite le compte de service.

*Dans les deux cas : le service démarre au boot, redémarre en cas de crash, et tourne sans qu'aucun utilisateur soit connecté.*

---

## 7. Vérifier

```powershell
Invoke-WebRequest http://127.0.0.1:5050/api/health -UseBasicParsing | Select-Object -Expand Content
```

**Attendu** : `status: ok, db: connected, schema: achat, write_enabled: true`. Puis depuis un poste client : `http://<IP-ou-nom-serveur>:5050/api/health`.

---

## 8. Basculer les utilisateurs & décommissionner le poste Marlène

1. Communiquer l'URL `http://<serveur>:5050` à Marlène, Andréa et Maxence (favori navigateur, rien à installer).
2. Une fois la bascule validée, arrêter l'instance sur le poste de Marlène (tâche `FUSEAU-API` locale si elle avait été installée) pour éviter deux instances concurrentes en écriture.

---

## 9. Rapatrier les ETL planifiés sur le serveur

Le poste de Marlène porte une tâche `FUSEAU_Gmail_ETL` (extraction PJ Gmail toutes les 2 h). À recréer sur le serveur sous le compte de service, pour que la collecte tourne indépendamment du poste. Prévoir aussi les prérequis OCR si le parsing BL tourne sur le serveur (Tesseract + Poppler, cf. état poste Marlène).

---

## 10. Mises à jour futures

```powershell
cd D:\Apps\FUSEAU
git pull --ff-only origin main
.\.venv311\Scripts\python.exe -m pip install -r requirements.txt   # si dépendances changées
Restart-Service FUSEAU-API     # (ou Restart-ScheduledTask selon l'option choisie)
```

---

## 📋 Récapitulatif des prérequis à demander à Samuel

| Besoin | Détail |
|---|---|
| **Serveur always-on** | Ne s'éteint pas la nuit |
| **Sortant 5432** | vers DWH Azure `psql-dtpf-psql-prod.postgres.database.azure.com` et DWH Sylob V25 `192.168.102.41` |
| **Sortant 443** | vers `*.googleapis.com` (ETL Gmail/Drive) |
| **Entrant 5050** | depuis le sous-réseau des postes clients |
| **Python 3.11** | installé ou installable |
| **Compte de service** | `svc-dataachat` (ticket GLPI 20/07) avec mot de passe |
| **Droits admin** | pour créer le service + la règle pare-feu (une fois) |
