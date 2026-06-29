<#
  FUSEAU - Mise en place poste local Marlene
  2026-06-29 - copie le repo depuis le partage A: vers le C: local,
  cree l'arborescence config\ et depose un modele .env a completer.

  Usage (PowerShell, sur le poste de Marlene) :
      .\setup_poste_marlene.ps1
      .\setup_poste_marlene.ps1 -Destination "C:\Users\marlene\dev\Data-Achat"

  Le script NE copie PAS : .git, config\.env, credentials.json, caches Python.
  Le script N'ECRASE PAS un .env deja present.
#>

[CmdletBinding()]
param(
    [string]$Source      = "A:\DATA\PARTAGE\Data-Achat",
    [string]$Destination = "$env:USERPROFILE\dev\Data-Achat"
)

$ErrorActionPreference = "Stop"
Write-Host "FUSEAU - mise en place poste local" -ForegroundColor Cyan
Write-Host "  Source      : $Source"
Write-Host "  Destination : $Destination"

if (-not (Test-Path $Source)) {
    throw "Source introuvable : $Source (le partage A: est-il monte ?)"
}

# 1. Copie via robocopy, en excluant code git, secrets et caches
$exclDirs  = @(".git", "__pycache__", ".pytest_cache", "05_ARCHIVES")
$exclFiles = @(".env", "credentials.json", "token.json", "*.pyc")

Write-Host "`n[1/3] Copie du repo (robocopy, exclusions appliquees)..." -ForegroundColor Yellow
$roboArgs = @($Source, $Destination, "/E", "/R:1", "/W:1", "/NFL", "/NDL")
$roboArgs += "/XD"; $roboArgs += $exclDirs
$roboArgs += "/XF"; $roboArgs += $exclFiles
robocopy @roboArgs | Out-Null
# robocopy : codes 0-7 = succes
if ($LASTEXITCODE -ge 8) { throw "Echec robocopy (code $LASTEXITCODE)" }
Write-Host "      OK - code robocopy $LASTEXITCODE"

# 2. Arborescence config\
$configDir = Join-Path $Destination "config"
if (-not (Test-Path $configDir)) {
    New-Item -ItemType Directory -Path $configDir | Out-Null
    Write-Host "[2/3] Dossier config\ cree." -ForegroundColor Yellow
} else {
    Write-Host "[2/3] Dossier config\ deja present." -ForegroundColor Yellow
}

# 3. Modele .env (sans ecraser un existant)
$envPath = Join-Path $configDir ".env"
if (Test-Path $envPath) {
    Write-Host "[3/3] config\.env deja present - NON ecrase." -ForegroundColor Green
} else {
@"
# FUSEAU - config poste Marlene (NE JAMAIS COMMITTER)
KEY_VAULT_NAME=
PG_HOST=psql-dtpf-psql-prod.postgres.database.azure.com
PG_PORT=5432
PG_DB=dtpf_sylob_prod
PG_USER=platform_team
PG_PASSWORD=__A_COMPLETER__
PG_SSLMODE=require
API_KEY=__MEME_CLE_QUE_LE_TEST__
API_HOST=127.0.0.1
API_PORT=5050
API_RELOAD=0
DATA_DIR=Service_Achat
# Plan A PJ Gmail (optionnel) :
# GMAIL_LABEL=Achats/Fournisseurs
# GMAIL_PJ_DIR=
"@ | Set-Content -Path $envPath -Encoding UTF8
    Write-Host "[3/3] Modele config\.env cree - completez PG_PASSWORD et API_KEY." -ForegroundColor Green
}

Write-Host "`nTermine." -ForegroundColor Cyan
Write-Host "Etapes suivantes :"
Write-Host "  1. Editez $envPath (PG_PASSWORD platform_team + API_KEY)."
Write-Host "  2. cd `"$Destination`"  ;  pip install -r requirements.txt"
Write-Host "  3. VPN Stormshield actif  ;  python run_api.py"
Write-Host "  4. http://127.0.0.1:5050/api/health  -> db connected, write_enabled true"
