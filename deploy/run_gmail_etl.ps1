<#
  FUSEAU - Orchestrateur ETL Gmail (PJ -> achat.ot_transport)
  ----------------------------------------------------------------
  Pipeline deterministe et non-supervise (OAuth Gmail, pas de Cowork requis) :
    fetch_attachments (PJ QUALITAIR)  ->  parse_bl  ->  load_ot_gmail (COMMIT)

  Concu pour une tache planifiee Windows sur le poste de Marlene.
  Prerequis runtime : VPN Stormshield actif (sinon DWH injoignable -> skip propre).

  Parametres : editer $Query / $Since ci-dessous si besoin d'elargir les expediteurs.
#>

# Continue (pas Stop) : les scripts Python ecrivent leurs logs sur stderr ; sous "Stop"
# PowerShell transforme ce stderr en exception. On se fie donc au code de sortie ($LASTEXITCODE).
$ErrorActionPreference = "Continue"
$Repo = "C:\Users\mmontbrizon\Documents\Claude\Data-Achat"
$Py   = Join-Path $Repo ".venv311\Scripts\python.exe"
$Query = "from:qualitairsea.com newer_than:3d"   # fenetre glissante (le manifeste dedoublonne)
$Parsed = Join-Path $Repo "data\PJ\_parsed.json"

# OCR sur le PATH (Tesseract + Poppler) pour parse_bl
$env:Path = "$env:Path;$env:LOCALAPPDATA\Programs\Tesseract-OCR;$env:LOCALAPPDATA\Programs\poppler\poppler-26.02.0\Library\bin"

# Log horodate
$LogDir = Join-Path $Repo "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Log = Join-Path $LogDir ("gmail_etl_{0}.log" -f (Get-Date -Format "yyyyMMdd"))
function Log($m) { $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"; "$ts  $m" | Tee-Object -FilePath $Log -Append }

Set-Location $Repo
Log "=== DEBUT ETL Gmail (query='$Query') ==="

# 0. Pre-vol DWH : si VPN down / DWH injoignable -> skip propre (pas d'echec bruyant)
& $Py -m src.scripts.gmail.preflight_gmail *>> $Log 2>&1
if ($LASTEXITCODE -ne 0) { Log "[SKIP] preflight KO (VPN/DWH/OCR ?) - on arrete proprement."; exit 0 }

# 1. Fetch PJ (OAuth)
Log "[1/3] fetch_attachments"
& $Py -m src.scripts.gmail.fetch_attachments --query $Query *>> $Log
if ($LASTEXITCODE -ne 0) { Log "[ERREUR] fetch_attachments exit=$LASTEXITCODE"; exit 1 }

# 2. Parse BL (texte + OCR eng+fra+chi_sim)
Log "[2/3] parse_bl"
& $Py -m src.scripts.gmail.parse_bl --folder "data\PJ" --out $Parsed --ocr-lang "eng+fra+chi_sim" *>> $Log
if ($LASTEXITCODE -ne 0) { Log "[ERREUR] parse_bl exit=$LASTEXITCODE"; exit 1 }

# 3. Load -> achat.ot_transport (COMMIT, upsert COALESCE)
Log "[3/3] load_ot_gmail (COMMIT)"
& $Py -m src.scripts.gmail.load_ot_gmail --file $Parsed *>> $Log
if ($LASTEXITCODE -ne 0) { Log "[ERREUR] load_ot_gmail exit=$LASTEXITCODE"; exit 1 }

Log "=== FIN ETL Gmail OK ==="
exit 0
