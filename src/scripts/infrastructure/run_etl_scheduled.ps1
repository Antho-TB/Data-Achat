# =============================================================================
# FUSEAU - Orchestrateur ETL fichiers (IMPORT, qualite, dimensions)
# =============================================================================
# Lance src.scripts.etl.pipeline, qui recharge achat.commande et achat.qualite
# en TRUNCATE + INSERT depuis le classeur IMPORT du partage reseau.
#
# C'est le seul ordonnanceur qui alimente ces deux tables. Sans lui, l'interface
# affiche des donnees figees a la derniere execution manuelle : constate le
# 22/09/2026, les deux tables dataient du 28/07, soit 56 jours, alors que la
# tache Gmail tournait normalement toutes les 2 heures. Deux pipelines, un seul
# automatise.
#
# Fait aussi le git pull du poste : c'est le seul passage quotidien qui met le
# code a jour, run_api.py ne le fera plus une fois l'API basculee sur Azure.
#
# Frequence recommandee : 1 fois par jour, 02h00.
# Prerequis runtime : VPN Stormshield actif, acces au partage reseau.
#
# Installation (PowerShell administrateur, sur le poste qui heberge FUSEAU) :
#   $A = New-ScheduledTaskAction -Execute "powershell.exe" `
#        -Argument '-NoProfile -ExecutionPolicy Bypass -File "<REPO>\src\scripts\infrastructure\run_etl_scheduled.ps1" -Repo "<REPO>"'
#   $T = New-ScheduledTaskTrigger -Daily -At 02:00
#   Register-ScheduledTask -TaskName "FUSEAU_Files_ETL" -Action $A -Trigger $T `
#        -Description "FUSEAU : pipeline fichiers IMPORT + qualite, 1x/jour" -RunLevel Limited
#
#   Passer -Repo explicitement : voir la resolution de racine ci-dessous.
# =============================================================================

[CmdletBinding()]
param(
    # Vide par defaut, et surtout PAS "$PSScriptRoot\..\..\..".
    #
    # Constate le 06/08/2026 sur le poste de Marlene, sur le wrapper de l'API :
    # lance par la tache planifiee, $PSScriptRoot etait vide dans la valeur par
    # defaut du parametre. La racine devenait un chemin relatif bancal, le venv
    # etait introuvable et le journal partait hors du depot, ce qui a fait
    # conclure a tort a une absence totale d'execution.
    [string]$Repo = ""
)

# Continue et non Stop. Les scripts Python journalisent sur stderr, et avec
# "Stop" la premiere ligne de log remontee par 2>&1 leverait une exception :
# le script rapporterait un echec sur un ETL parfaitement reussi. On se fie au
# code de sortie, jamais a la presence de sortie d'erreur.
$ErrorActionPreference = "Continue"

# --- Journal de secours ------------------------------------------------------
# Determine avant tout le reste : si la racine est fausse, le message d'echec
# doit atterrir quelque part de lisible. Une tache planifiee qui echoue sans
# laisser de trace est indistinguable d'une tache qui n'a jamais ete appelee.
$LogDeSecours = Join-Path $env:TEMP ("fuseau_etl_secours_{0}.log" -f (Get-Date -Format "yyyyMMdd"))
function LogSecours($m) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$ts  $m" | Out-File -FilePath $LogDeSecours -Append -Encoding utf8
}

# --- Resolution de la racine du depot ----------------------------------------
# Ce script vit dans src\scripts\infrastructure\, donc TROIS niveaux sous la
# racine. La version precedente n'en remontait que deux : elle se placait dans
# src\ et lancait "python -m src.scripts.etl.pipeline" depuis la, ce qui donne
# un ModuleNotFoundError. Seule trace laissee : un pipeline_run.log de 0 octet
# date du 23/06/2026.
#
# On ne devine jamais un chemin de repli : un pipeline lance depuis le mauvais
# dossier ecrirait en base a partir d'un code different de celui qu'on croit
# deployer.
if (-not $Repo) {
    $base = $PSScriptRoot
    if (-not $base -and $MyInvocation.MyCommand.Path) {
        $base = Split-Path -Parent $MyInvocation.MyCommand.Path
    }
    if ($base) { $Repo = Join-Path $base "..\..\.." }
}

if (-not $Repo) {
    LogSecours "[ECHEC] Racine du depot indeterminable (`$PSScriptRoot et `$MyInvocation vides). Relancer la tache avec -Repo explicite."
    exit 1
}

$resolu = Resolve-Path -LiteralPath $Repo -ErrorAction SilentlyContinue
if (-not $resolu) {
    LogSecours ("[ECHEC] Racine du depot introuvable : '{0}'." -f $Repo)
    exit 1
}
$Repo = $resolu.Path

# Controle d'identite. Sans lui, une racine plausible mais fausse echouerait
# plus loin sur un message trompeur parlant du venv ou d'un module Python.
if (-not (Test-Path (Join-Path $Repo "run_api.py"))) {
    LogSecours ("[ECHEC] '{0}' ne contient pas run_api.py : ce n'est pas la racine du depot FUSEAU." -f $Repo)
    exit 1
}

Set-Location $Repo

# Journal dans deploy\logs, comme les deux autres orchestrateurs, plutot que
# dans un dossier logs\ a la racine : l'emplacement est deja couvert par le
# .gitignore, et un dossier non suivi a la racine annulerait le git pull.
$LogDir = Join-Path $Repo "deploy\logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Log = Join-Path $LogDir ("etl_files_{0}.log" -f (Get-Date -Format "yyyyMMdd"))
function Write-Log($m) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$ts  $m" | Tee-Object -FilePath $Log -Append
}

Write-Log "=== DEBUT ETL fichiers FUSEAU ==="
Write-Log ("[INFO] Racine du depot : {0}" -f $Repo)

# --- 1. Synchronisation du code ----------------------------------------------
# --ff-only : on n'invente pas un merge automatique sur un poste sans personne
# pour le resoudre. Un depot modifie localement annule le pull, et c'est
# signale en ATTENTION plutot qu'avale en silence.
# --untracked-files=no : un fichier non suivi (un rapport depose dans docs\)
# ne gene pas un pull en avance rapide. Il a pourtant bloque la synchro du
# 22 au 24/09. Si le pull devait l'ecraser, git refuse et on passe par la
# branche d'erreur ci-dessous.
$Branche = if ($env:BRANCHE_DEPLOIEMENT) { $env:BRANCHE_DEPLOIEMENT } else { "main" }
$Modifs = & git -C $Repo status --porcelain --untracked-files=no
if ($Modifs) {
    Write-Log "[ATTENTION] Modifications locales non commitees, pull annule. L'ETL tourne sur le code local, qui n'est pas celui de $Branche."
} else {
    Write-Log "[INFO] Synchronisation sur $Branche..."
    $GitOutput = & git -C $Repo pull origin $Branche --ff-only 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Log "[SUCCES] Code a jour : $GitOutput"
    } else {
        Write-Log "[ATTENTION] Pull impossible, poursuite sur le code local : $GitOutput"
    }
}

# --- 2. Pipeline ETL ----------------------------------------------------------
$Py = Join-Path $Repo ".venv311\Scripts\python.exe"
if (-not (Test-Path $Py)) {
    Write-Log "[ECHEC] venv introuvable ($Py). Lancer 'pip install -r requirements.txt' d'abord."
    exit 1
}

Write-Log "[INFO] Lancement du pipeline fichiers..."
& $Py -m src.scripts.etl.pipeline *>> $Log
if ($LASTEXITCODE -ne 0) {
    Write-Log "[ECHEC] pipeline exit=$LASTEXITCODE"
    exit 1
}

Write-Log "=== FIN ETL fichiers OK ==="
exit 0
