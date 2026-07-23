<#
  FUSEAU - Installation de la Tache Planifiee "FUSEAU-API"
  ------------------------------------------------------------------------
  Remplace le mode "laisser la fenetre PowerShell ouverte" par une Tache
  Planifiee Windows native (pas de logiciel tiers a installer -- coherent
  avec le pattern deja utilise pour l'ETL Gmail, cf. run_gmail_etl.ps1).

  Ce que fait la tache installee :
    - Declencheur "A l'ouverture de session" de l'utilisateur courant
      (Marlene) -- pas besoin de stocker un mot de passe de service.
    - Redemarrage automatique si le process crashe : jusqu'a 999 tentatives,
      toutes les 1 minute (couvre les coupures VPN passageres, crash Python).
    - Fenetre cachee (pas de PowerShell qui traine sur le bureau).

  Limite assumee : la tache ne tourne QUE si Marlene est ouverte-session sur
  le poste (pas "tourne meme deconnecte", ce qui eviterait de stocker un mot
  de passe en clair dans le planificateur). Suffisant pour l'usage vise
  (Marlene + Andrea consultent en journee, poste allume).

  Usage (PowerShell EN ADMINISTRATEUR, sur le poste de Marlene) :
      cd C:\Users\<marlene>\dev\Data-Achat\deploy
      .\install_service_windows.ps1

  Pour desinstaller : Unregister-ScheduledTask -TaskName "FUSEAU-API" -Confirm:$false
#>

[CmdletBinding()]
param(
    [string]$TaskName = "FUSEAU-API",
    [string]$Repo     = "$PSScriptRoot\..",
    [int]$Port        = 5050,
    # Andrea accede depuis son propre poste (LAN bureau, cf. decision 23/07) :
    # on ouvre le firewall mais SCOPE au sous-reseau local uniquement (jamais
    # "Any"). Mettre -OpenFirewall:$false si acces limite au poste local seul.
    [switch]$OpenFirewall = $true
)

$ErrorActionPreference = "Stop"

if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Ce script doit etre lance en PowerShell ADMINISTRATEUR (clic droit > Executer en tant qu'administrateur)."
}

$WrapperScript = Join-Path $Repo "deploy\run_api_service.ps1"
if (-not (Test-Path $WrapperScript)) {
    throw "Introuvable : $WrapperScript"
}

Write-Host "FUSEAU - installation de la tache planifiee '$TaskName'" -ForegroundColor Cyan

# Supprime une tache existante du meme nom (idempotent, permet de re-executer
# ce script apres une mise a jour du wrapper sans erreur "tache deja existante").
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Write-Host "  Tache existante detectee, suppression avant recreation..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

$Action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$WrapperScript`""

# Declencheur : a l'ouverture de session de l'utilisateur courant (celui qui
# execute ce script d'install -- a lancer en etant connecte en tant que Marlene).
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"

$Settings = New-ScheduledTaskSettingsSet `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Days 0) `
    -DontStopOnIdleEnd `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings `
    -Description "FUSEAU - API FastAPI + frontend (achat.*). Demarre a l'ouverture de session, redemarre auto en cas de crash. Logs : deploy\logs\api_*.log" `
    | Out-Null

Write-Host "`nTache '$TaskName' installee." -ForegroundColor Green
Write-Host "Elle se lancera a la prochaine ouverture de session."
Write-Host "Pour la lancer maintenant sans attendre : Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "Pour verifier : Get-ScheduledTask -TaskName '$TaskName' | Get-ScheduledTaskInfo"
Write-Host "Sante API une fois lancee : http://127.0.0.1:5050/api/health"

# ── Firewall (acces LAN pour Andrea) ────────────────────────────────────────
# Decision 23/07 : Andrea accede depuis son propre poste (LAN bureau), pas
# seulement Marlene en local. On ouvre donc le port, mais UNIQUEMENT pour le
# sous-reseau local (RemoteAddress LocalSubnet), jamais pour "Any"/Internet.
# Prerequis cote config\.env : API_HOST=0.0.0.0 (sinon uvicorn n'ecoute que
# 127.0.0.1 et la regle firewall ne sert a rien -- verifier avant de tester
# depuis le poste d'Andrea).
if ($OpenFirewall) {
    $fwName = "FUSEAU-API (LAN bureau)"
    if (Get-NetFirewallRule -DisplayName $fwName -ErrorAction SilentlyContinue) {
        Remove-NetFirewallRule -DisplayName $fwName
    }
    New-NetFirewallRule -DisplayName $fwName -Direction Inbound -Protocol TCP `
        -LocalPort $Port -Action Allow -RemoteAddress LocalSubnet -Profile Domain,Private `
        | Out-Null
    Write-Host "`nRegle firewall '$fwName' creee : port $Port ouvert au sous-reseau local uniquement (Domain/Private, pas Public)." -ForegroundColor Green
    Write-Host "RAPPEL : verifier API_HOST=0.0.0.0 dans config\.env (defaut actuel = 127.0.0.1, a changer manuellement)." -ForegroundColor Yellow
} else {
    Write-Host "`n-OpenFirewall:`$false : aucune regle firewall creee (acces reste limite au poste local)." -ForegroundColor Yellow
}
