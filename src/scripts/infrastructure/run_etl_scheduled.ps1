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
# Codes de sortie (colonne "Dernier resultat" du Planificateur) :
#   0x0 : ETL OK sur le code a jour.
#   0x1 : ETL en echec (ou racine/venv introuvable).
#   0x2 : ETL OK, mais pull bloque : le code execute n'est pas celui de la
#         branche. Detail dans deploy\logs\PULL_BLOQUE.txt.
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
# .gitignore, et un dossier non suivi a la racine encombrerait 'git status'.
# Le marqueur PULL_BLOQUE.txt y vit aussi.
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
# pour le resoudre.
#
# --untracked-files=no : seuls les fichiers SUIVIS modifies bloquent le pull.
# Un fichier non suivi ne gene pas une avance rapide, et c'est pourtant ce qui
# a annule la synchro trois fois (un .log.err le 28/07, une sauvegarde .env le
# 06/08, un .docx du 22 au 24/09 : deux jours d'ETL sur l'ancien code). Si un
# fichier non suivi porte le meme chemin qu'un fichier ajoute par le distant,
# git refuse le merge et on passe par la branche d'erreur.
#
# Un pull bloque n'arrete PAS l'ETL : les donnees du jour comptent plus que la
# version du code. Mais le script finit en exit 2 au lieu de 0, pour que la
# tache passe en anomalie dans le Planificateur ("Dernier resultat" 0x2), et
# laisse deploy\logs\PULL_BLOQUE.txt. Avant, l'echec n'etait visible qu'en
# lisant le journal, donc jamais.
#
# Meme logique cote Python : src\utils\git_sync.py (utilise par run_api.py).
$Branche = if ($env:BRANCHE_DEPLOIEMENT) { $env:BRANCHE_DEPLOIEMENT } else { "main" }
$Marqueur = Join-Path $LogDir "PULL_BLOQUE.txt"
$PullBloque = $false

function Join-GitOutput($o) { (($o | ForEach-Object { "$_" }) -join " | ").Trim() }

function Set-PullBloque([string]$Raison, [string[]]$Fichiers, [string]$HeadLocal, [string]$Distant, $Retard) {
    $script:PullBloque = $true
    Write-Log "[ATTENTION] PULL BLOQUE : $Raison"
    foreach ($f in $Fichiers) { Write-Log "[ATTENTION]   fichier en cause : $f" }
    Write-Log "[ATTENTION] L'ETL tourne sur le code local ($HeadLocal), pas sur $Branche ($Distant). Marqueur : $Marqueur"
    $lignes = @(
        "PULL AUTOMATIQUE BLOQUE : le poste ne tourne PAS sur le code de la branche cible.",
        ("Horodatage   : {0}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss")),
        "Origine      : run_etl_scheduled.ps1 (tache FUSEAU_Files_ETL)",
        "Branche      : $Branche",
        "HEAD local   : $HeadLocal",
        "Distant      : $Distant",
        "Retard       : $Retard commit(s)",
        "Detail       : $Raison",
        "Fichiers en cause :"
    )
    if ($Fichiers -and $Fichiers.Count -gt 0) {
        $lignes += ($Fichiers | ForEach-Object { "  - $_" })
    } else {
        $lignes += "  (aucun, voir Detail)"
    }
    $lignes += @(
        "",
        "A faire : 'git status' a la racine du depot, ranger ou annuler les fichiers",
        "listes ('git restore <fichier>' si la modification est inutile), puis",
        "'git pull origin $Branche --ff-only'. Ce fichier disparait au prochain pull reussi."
    )
    $lignes | Out-File -FilePath $Marqueur -Encoding utf8
}

$HeadAvant = Join-GitOutput (& git -C $Repo rev-parse --short HEAD 2>&1)
Write-Log "[INFO] HEAD local avant synchro : $HeadAvant (cible $Branche)"

# Un seul fetch, puis fusion de FETCH_HEAD : le retard mesure est exactement
# ce qui sera fusionne, y compris si BRANCHE_DEPLOIEMENT pointe un tag.
$FetchOutput = & git -C $Repo fetch origin $Branche 2>&1
if ($LASTEXITCODE -ne 0) {
    Set-PullBloque -Raison ("fetch impossible (VPN, reseau, droits ?) : {0}" -f (Join-GitOutput $FetchOutput)) `
        -Fichiers @() -HeadLocal $HeadAvant -Distant "inconnu" -Retard "inconnu"
} else {
    $Distant = Join-GitOutput (& git -C $Repo rev-parse --short FETCH_HEAD 2>&1)
    $Retard = Join-GitOutput (& git -C $Repo rev-list --count "HEAD..FETCH_HEAD" 2>&1)
    Write-Log "[INFO] $Branche distant : $Distant, retard du poste : $Retard commit(s)"

    # Format porcelain v1 : deux caracteres d'etat, un espace, puis le chemin.
    $Modifs = @(& git -C $Repo status --porcelain --untracked-files=no | Where-Object { $_.Length -gt 3 } | ForEach-Object { $_.Substring(3).Trim() })
    if ($Modifs.Count -gt 0) {
        Set-PullBloque -Raison "fichiers suivis modifies localement, pull annule" `
            -Fichiers $Modifs -HeadLocal $HeadAvant -Distant $Distant -Retard $Retard
    } elseif ($Retard -eq "0") {
        Write-Log "[SUCCES] Deja a jour sur $Branche ($HeadAvant)."
    } else {
        $MergeOutput = & git -C $Repo merge --ff-only FETCH_HEAD 2>&1
        if ($LASTEXITCODE -eq 0) {
            $HeadApres = Join-GitOutput (& git -C $Repo rev-parse --short HEAD 2>&1)
            Write-Log "[SUCCES] Code mis a jour : $HeadAvant -> $HeadApres"
        } else {
            # Cas typique : fichier non suivi en collision avec un fichier
            # ajoute par le distant, ou commits locaux divergents.
            Set-PullBloque -Raison ("merge --ff-only refuse : {0}" -f (Join-GitOutput $MergeOutput)) `
                -Fichiers @() -HeadLocal $HeadAvant -Distant $Distant -Retard $Retard
        }
    }
}

if (-not $PullBloque -and (Test-Path $Marqueur)) {
    Remove-Item -LiteralPath $Marqueur -Force
    Write-Log "[INFO] Marqueur PULL_BLOQUE.txt supprime : la synchro est retablie."
}
$HeadExecute = Join-GitOutput (& git -C $Repo rev-parse --short HEAD 2>&1)
Write-Log "[INFO] HEAD local apres synchro (code execute par l'ETL) : $HeadExecute"

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
    if ($PullBloque) { Write-Log "[ATTENTION] Le pull etait aussi bloque : voir $Marqueur." }
    exit 1
}

# ETL reussi mais sur un code qui n'est pas celui de la branche : exit 2, pour
# que l'anomalie remonte dans le Planificateur sans etre confondue avec un
# echec du pipeline (exit 1).
if ($PullBloque) {
    Write-Log "[ECHEC] ETL termine mais PULL BLOQUE : code $HeadExecute au lieu de $Branche. Voir $Marqueur. exit=2"
    exit 2
}

Write-Log "=== FIN ETL fichiers OK ==="
exit 0
