# FUSEAU — Runbook service Windows (poste Marlène)

_Rédigé le 2026-07-23, suite décision mise en prod du 27/07 (mardi) : Marlène +
Andréa en utilisatrices, Antho reste en dev sur son poste (localhost)._

## 1. Installation (une fois)

Sur le poste de Marlène, PowerShell **en administrateur** :

```powershell
cd C:\Users\<marlene>\dev\Data-Achat\deploy
.\install_service_windows.ps1
```

Ce script :
- installe la Tâche Planifiée Windows `FUSEAU-API` (démarre à l'ouverture de
  session de Marlène, redémarre automatiquement en cas de crash — jusqu'à
  999 tentatives, 1 par minute) ;
- ouvre le firewall Windows sur le port 5050, **scopé au sous-réseau local
  uniquement** (Domain/Private, jamais Public/Internet), pour qu'Andréa
  puisse y accéder depuis son propre poste.

**Avant de lancer le script**, dans `config\.env` :
- Mettre `API_HOST=0.0.0.0` (sinon l'API n'écoute que `127.0.0.1` et la règle
  firewall ne sert à rien).
- Vérifier `CORS_ORIGINS` (ajouter l'URL LAN si besoin, ex.
  `http://192.168.x.x:5050`).

Pas de mot de passe de service stocké : la tâche tourne sous la session
Windows de Marlène (limite acceptée : elle ne redémarre pas si Marlène est
déconnectée, contrairement à un vrai service Windows avec compte dédié).

## 2. Vérifier que ça tourne

```powershell
Get-ScheduledTask -TaskName "FUSEAU-API" | Get-ScheduledTaskInfo
```
`LastTaskResult` doit valoir `0`. Puis dans un navigateur :
`http://127.0.0.1:5050/api/health` (sur le poste de Marlène) →
`db: connected`, `write_enabled: true`.

Depuis le poste d'Andréa (une fois le firewall ouvert) :
`http://<IP-LAN-Marlene>:5050/api/health`.

## 3. Logs

`deploy\logs\api_YYYYMMDD.log` — un fichier par jour, contient les logs
uvicorn/FastAPI + les messages du wrapper (`[NETTOYAGE]`, `[ATTENTION]`,
`[INFO]`, `[ECHEC]`).

## 4. Relancer manuellement (sans attendre un crash ou une ouverture de session)

```powershell
Start-ScheduledTask -TaskName "FUSEAU-API"
```

## 5. Coupure VPN Stormshield

Le wrapper (`run_api_service.ps1`) détecte l'absence de VPN au démarrage et le
signale dans les logs (`[ATTENTION] Aucun adaptateur VPN...`), mais démarre
quand même : l'API dégrade proprement (health check `db: unreachable`,
KPIs à 0) plutôt que de planter. Reconnecter le VPN suffit à rétablir la
connexion DB sans redémarrer l'API (le pool SQLAlchemy retente à la prochaine
requête).

## 6. Mettre à jour le code (nouvelle version de FUSEAU)

```powershell
cd C:\Users\<marlene>\dev\Data-Achat
git pull
Stop-ScheduledTask -TaskName "FUSEAU-API"    # ou laisser le restart auto le relancer
Start-ScheduledTask -TaskName "FUSEAU-API"
```

## 7. Désinstaller

```powershell
Unregister-ScheduledTask -TaskName "FUSEAU-API" -Confirm:$false
Remove-NetFirewallRule -DisplayName "FUSEAU-API (LAN bureau)"
```

## 8. Piège connu (hérité du mode manuel)

Workers uvicorn orphelins bloquant le port 5050 : le wrapper les purge
automatiquement à chaque démarrage (`Get-CimInstance Win32_Process ...
-match 'run_api|spawn_main'`). Si le symptôme réapparaît malgré tout
(`OSError: [Errno 10048]` dans les logs), le confirmer à la main :

```powershell
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'run_api|spawn_main' } | Select ProcessId, CommandLine
```
