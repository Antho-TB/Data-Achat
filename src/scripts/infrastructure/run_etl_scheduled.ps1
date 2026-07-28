# =============================================================================
# SCRIPT DE PLANIFICATION INFRA (Windows Server / Task Scheduler)
# =============================================================================
# Description : Exécute le pipeline ETL FUSEAU et l'auto-sync Git sur le serveur.
# Fréquence recommandée : Tous les jours à 02:00 (nocturne).
# Auteur : Anthony Bezille (Lead Data & AI Engineer) / Équipe Infra
# =============================================================================

$ErrorActionPreference = "Stop"

# 1. Définition des répertoires du projet FUSEAU sur le serveur
$ProjectDir = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$LogDir = Join-Path $ProjectDir "logs"
if (!(Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir | Out-Null
}

$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$LogFile = Join-Path $LogDir "etl_scheduled_$Timestamp.log"

# Fonction d'écriture de log
function Write-Log {
    param([string]$Message)
    $FormattedMsg = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') [INFO] $Message"
    Write-Host $FormattedMsg
    Add-Content -Path $LogFile -Value $FormattedMsg
}

Write-Log "=== DÉMARRAGE PIPELINE ETL PLANIFIÉ FUSEAU (Serveur) ==="
Write-Log "Répertoire projet : $ProjectDir"

Set-Location $ProjectDir

# 2. Sync Git automatique
# Le pull cible explicitement le repertoire du depot et refuse d'ecraser des
# modifications locales. Un --ff-only garantit qu'on n'invente pas un merge
# automatique sur un poste serveur sans personne pour le resoudre.
$Branche = if ($env:BRANCHE_DEPLOIEMENT) { $env:BRANCHE_DEPLOIEMENT } else { "main" }
try {
    $Modifs = & git -C $ProjectDir status --porcelain
    if ($Modifs) {
        Write-Log "[ATTENTION] Modifications locales non commitees, pull annule. ETL lance sur le code local."
    } else {
        Write-Log "Synchronisation sur $Branche..."
        $GitOutput = & git -C $ProjectDir pull origin $Branche --ff-only 2>&1
        Write-Log "Git result: $GitOutput"
    }
} catch {
    Write-Log "[ATTENTION] Probleme lors du git pull (poursuite avec le code existant) : $_"
}

# 3. Détection de l'environnement virtuel Python
$VenvPython = Join-Path $ProjectDir ".venv311\Scripts\python.exe"
if (!(Test-Path $VenvPython)) {
    $VenvPython = "python.exe"
}

# 4. Lancement de l'ETL
Write-Log "Lancement de l'ETL FUSEAU via $VenvPython..."
try {
    $EtlOutput = & $VenvPython -m src.scripts.etl.pipeline 2>&1
    Write-Log "ETL Output:`n$EtlOutput"
    Write-Log "=== FIN DU PIPELINE ETL PLANIFIÉ [SUCCÈS] ==="
} catch {
    Write-Log "[ERREUR] Échec de l'exécution de l'ETL : $_"
    exit 1
}
