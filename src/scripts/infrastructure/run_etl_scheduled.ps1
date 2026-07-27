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
try {
    Write-Log "Exécution du git pull origin main..."
    $GitOutput = & git pull origin main 2>&1
    Write-Log "Git result: $GitOutput"
} catch {
    Write-Log "[ATTENTION] Problème lors du git pull (tentative de continuation avec le code existant) : $_"
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
