# ============================================================
# setup-windows-mcp.ps1
# Pre-installe le venv Windows-MCP avant le lancement de Claude Desktop
# A executer UNE SEULE FOIS en PowerShell sur le poste de Marlene
# ============================================================

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "=== Setup Windows-MCP pour Claude Desktop ===" -ForegroundColor Cyan
Write-Host ""

# --- 1. Lire claude_desktop_config.json ---
$configPath = "$env:APPDATA\Claude\claude_desktop_config.json"
if (-not (Test-Path $configPath)) {
    Write-Host "[ERREUR] $configPath introuvable." -ForegroundColor Red
    Write-Host "         Cree le dossier $env:APPDATA\Claude et relance le script." -ForegroundColor Yellow
    exit 1
}

Write-Host "[OK] Config Claude trouvee : $configPath" -ForegroundColor Green
$config = Get-Content $configPath -Raw | ConvertFrom-Json

# --- 2. Trouver le chemin Windows-MCP dans la config ---
$mcpDir = $null
$servers = $config.mcpServers.PSObject.Properties

foreach ($server in $servers) {
    $args = $server.Value.args
    if ($args -contains "--directory" -or $server.Name -like "*windows*") {
        # Chercher --directory dans les args
        for ($i = 0; $i -lt $args.Count; $i++) {
            if ($args[$i] -eq "--directory" -and $i + 1 -lt $args.Count) {
                $mcpDir = $args[$i + 1]
                Write-Host "[OK] Windows-MCP trouve : '$($server.Name)' -> $mcpDir" -ForegroundColor Green
                break
            }
        }
        # Fallback : chercher un chemin qui contient 'windows-mcp' dans les args
        if (-not $mcpDir) {
            foreach ($arg in $args) {
                if ($arg -match "windows.mcp" -and (Test-Path $arg -PathType Container)) {
                    $mcpDir = $arg
                    Write-Host "[OK] Windows-MCP trouve (fallback) : $mcpDir" -ForegroundColor Green
                    break
                }
            }
        }
    }
    if ($mcpDir) { break }
}

if (-not $mcpDir) {
    Write-Host "[ERREUR] Impossible de trouver le dossier Windows-MCP dans la config." -ForegroundColor Red
    Write-Host "         Contenu des serveurs MCP configures :" -ForegroundColor Yellow
    $servers | ForEach-Object { Write-Host "  - $($_.Name)" }
    Write-Host ""
    Write-Host "Colle le chemin manuellement et relance :" -ForegroundColor Yellow
    Write-Host '  $mcpDir = "C:\chemin\vers\windows-mcp"' -ForegroundColor White
    Write-Host '  cd $mcpDir ; uv venv ; uv sync' -ForegroundColor White
    exit 1
}

if (-not (Test-Path $mcpDir)) {
    Write-Host "[ERREUR] Le dossier $mcpDir n'existe pas sur ce poste." -ForegroundColor Red
    exit 1
}

# --- 3. Verifier que uv est installe ---
try {
    $uvVersion = uv --version 2>&1
    Write-Host "[OK] uv detecte : $uvVersion" -ForegroundColor Green
} catch {
    Write-Host "[ERREUR] uv non trouve dans le PATH." -ForegroundColor Red
    Write-Host "         Installe uv via :" -ForegroundColor Yellow
    Write-Host '  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"' -ForegroundColor White
    Write-Host "         Puis ferme et reouvre PowerShell avant de relancer ce script." -ForegroundColor Yellow
    exit 1
}

# --- 4. Pre-installer le venv ---
Write-Host ""
Write-Host "Installation du venv Windows-MCP (peut prendre 1-2 minutes)..." -ForegroundColor Cyan
Set-Location $mcpDir

Write-Host "  uv venv..." -ForegroundColor Gray
uv venv 2>&1 | Write-Host

Write-Host "  uv sync..." -ForegroundColor Gray
uv sync 2>&1 | Write-Host

# --- 5. Verifier que le venv est pret ---
$venvPath = Join-Path $mcpDir ".venv"
if (Test-Path $venvPath) {
    Write-Host ""
    Write-Host "[SUCCES] Venv installe dans : $venvPath" -ForegroundColor Green
    Write-Host ""
    Write-Host "Tu peux maintenant lancer Claude Desktop normalement." -ForegroundColor Cyan
    Write-Host "Windows-MCP se connectera sans timeout." -ForegroundColor Cyan
} else {
    Write-Host ""
    Write-Host "[AVERTISSEMENT] Le dossier .venv n'a pas ete trouve apres l'install." -ForegroundColor Yellow
    Write-Host "Verifie les erreurs ci-dessus ou contacte a.bezille@tb-groupe.fr" -ForegroundColor Yellow
}

Write-Host ""
