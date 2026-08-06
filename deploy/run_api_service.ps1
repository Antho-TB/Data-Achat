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
    # Vide par defaut, et surtout PAS "$PSScriptRoot\..".
    #
    # Constate le 06/08/2026 sur le poste de Marlene : au lancement par la tache
    # planifiee, $PSScriptRoot etait vide dans la valeur par defaut du parametre.
    # $Repo valait donc "\..", ce qui produisait deux effets qui se masquaient
    # l'un l'autre. Le venv etait cherche dans "\..\.venv311\", introuvable, donc
    # sortie en code 1. Et le journal partait dans C:\deploy\logs au lieu du
    # depot, ce qui a fait conclure a une absence totale de log. La tache
    # echouait ainsi a chaque ouverture de session depuis le 23/07, sans trace
    # visible la ou on la cherchait.
    [string]$Repo = ""
)

$ErrorActionPreference = "Continue"

# --- Journal de secours -----------------------------------------------------
# Determine AVANT toute autre chose : si la racine du depot est fausse, le
# message d'echec doit atterrir quelque part de lisible. Un wrapper de tache
# planifiee qui echoue sans laisser de trace est indistinguable d'un wrapper qui
# n'a jamais ete appele, et c'est precisement ce qui a coute deux semaines ici.
$LogDeSecours = Join-Path $env:TEMP ("fuseau_api_secours_{0}.log" -f (Get-Date -Format "yyyyMMdd"))
function LogSecours($m) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$ts  $m" | Out-File -FilePath $LogDeSecours -Append -Encoding utf8
}

# --- Resolution de la racine du depot ---------------------------------------
# Deux sources, dans cet ordre, puis echec explicite. On ne devine jamais un
# chemin de repli : uvicorn lance depuis le mauvais dossier demarrerait sur un
# code different de celui qu'on croit deployer.
if (-not $Repo) {
    $base = $PSScriptRoot
    if (-not $base -and $MyInvocation.MyCommand.Path) {
        $base = Split-Path -Parent $MyInvocation.MyCommand.Path
    }
    if ($base) { $Repo = Join-Path $base ".." }
}

if (-not $Repo) {
    LogSecours "[ECHEC] Racine du depot indeterminable (`$PSScriptRoot et `$MyInvocation vides). Relancer la tache avec -Repo explicite : powershell.exe -NoProfile -ExecutionPolicy Bypass -File <chemin>\deploy\run_api_service.ps1 -Repo <chemin du depot>"
    exit 1
}

$resolu = Resolve-Path -LiteralPath $Repo -ErrorAction SilentlyContinue
if (-not $resolu) {
    LogSecours ("[ECHEC] Racine du depot introuvable : '{0}'." -f $Repo)
    exit 1
}
$Repo = $resolu.Path

# Controle d'identite du depot. Sans lui, un $Repo plausible mais faux (la racine
# du disque, par exemple) creerait un C:\deploy\logs et echouerait plus loin sur
# un message trompeur parlant du venv.
if (-not (Test-Path (Join-Path $Repo "run_api.py"))) {
    LogSecours ("[ECHEC] '{0}' ne contient pas run_api.py : ce n'est pas la racine du depot FUSEAU." -f $Repo)
    exit 1
}

Set-Location $Repo

$LogDir = Join-Path $Repo "deploy\logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Log = Join-Path $LogDir ("api_{0}.log" -f (Get-Date -Format "yyyyMMdd"))
function Log($m) { $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"; "$ts  $m" | Tee-Object -FilePath $Log -Append }

Log "=== DEMARRAGE wrapper FUSEAU-API ==="
Log ("[INFO] Racine du depot : {0}" -f $Repo)

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
