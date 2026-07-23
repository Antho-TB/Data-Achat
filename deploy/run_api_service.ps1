<#
  FUSEAU - Wrapper d'execution de l'API pour la tache planifiee Windows
  ----------------------------------------------------------------------
  Ne PAS lancer ce script a la main pour un usage quotidien : c'est la
  Tache Planifiee "FUSEAU-API" (installee par install_service_windows.ps1)
  qui l'appelle. Il peut aussi etre lance manuellement pour tester avant
  d'installer la tache.

  Ce que fait ce wrapper :
    1. Purge les eventuels workers uvicorn orphelins (piege Windows connu,
       cf. README.md / docs/20260629_FUSEAU_DeploiementPosteMarlene_Cowork_v1.md
       section 7 "Pieges connus").
    2. Verifie que le VPN Stormshield est actif (sinon le DWH est injoignable ;
       on log un avertissement mais on demarre quand meme -- l'API degrade
       proprement, deja gere cote code app/main.py).
    3. Lance uvicorn au premier plan (la Tache Planifiee garde le process
       vivant ; c'est elle qui gere le restart en cas de crash).

  Logs : deploy\logs\api_YYYYMMDD.log (cree si absent).
#>

[CmdletBinding()]
param(
    [string]$Repo = "$PSScriptRoot\.."
)

$ErrorActionPreference = "Continue"
Set-Location $Repo

$LogDir = Join-Path $Repo "deploy\logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Log = Join-Path $LogDir ("api_{0}.log" -f (Get-Date -Format "yyyyMMdd"))
function Log($m) { $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"; "$ts  $m" | Tee-Object -FilePath $Log -Append }

Log "=== DEMARRAGE wrapper FUSEAU-API ==="

# 1. Purge des workers uvicorn orphelins (piege connu : reload=1 laisse parfois
#    un spawn_main fantome qui bloque le port au redemarrage).
$orphans = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match 'run_api|spawn_main' -and $_.ProcessId -ne $PID }
if ($orphans) {
    Log ("[NETTOYAGE] {0} process(us) orphelin(s) detecte(s), arret force." -f $orphans.Count)
    $orphans | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 2
}

# 2. VPN Stormshield -- controle non bloquant (juste un avertissement log).
#    Adapter le nom si l'adaptateur VPN local s'appelle differemment.
$vpn = Get-NetAdapter -ErrorAction SilentlyContinue | Where-Object { $_.Name -match 'Stormshield|VPN' -and $_.Status -eq 'Up' }
if (-not $vpn) {
    Log "[ATTENTION] Aucun adaptateur VPN Stormshield actif detecte -- le DWH sera probablement injoignable (l'API demarre quand meme, mode degrade)."
} else {
    Log "[INFO] VPN Stormshield actif."
}

# 3. Lancement uvicorn (premier plan -- la Tache Planifiee gere le restart).
$Py = Join-Path $Repo ".venv311\Scripts\python.exe"
if (-not (Test-Path $Py)) {
    Log "[ECHEC] venv introuvable ($Py) -- lancer 'pip install -r requirements.txt' d'abord."
    exit 1
}

Log "[INFO] Lancement run_api.py..."
& $Py run_api.py *>> $Log
Log ("[FIN] run_api.py s'est arrete (code sortie {0})." -f $LASTEXITCODE)
exit $LASTEXITCODE
