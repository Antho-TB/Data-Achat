<#
  FUSEAU - Orchestrateur ETL quotidien (sources lentes)
  ----------------------------------------------------------------
  Deux sources qui ne changent pas assez vite pour justifier un passage toutes
  les 2 heures, mais qui etaient jusqu'ici alimentees a la main -- donc pas du
  tout. Constat du 28/07 : achat.artwork_statut fige au 22/07, achat.qualite_doc
  et achat.qualite_analyse figees au 02/07 avec 8 lignes chacune.

    1. Artwork  : gsheet LIS-CON-28-0 (Clarisse) -> achat.artwork_statut
    2. Qualite  : Drive "ANALYSES ET INSPECTIONS" -> achat.qualite_doc / _analyse
    3. Sylob    : dimensions, referentiel article et CA fournisseur 3 ans
                  -> achat.produit et achat.fournisseur_ca

  Complement de run_gmail_etl.ps1 (PJ Gmail, toutes les 2 h) et de la tache
  Cowork (decisions metier depuis le corps des mails, toutes les 2 h).

  Frequence recommandee : 1 fois par jour, 07h00, avant l'arrivee du service.
  Prerequis : VPN Stormshield actif, config/credentials.json et config/token.json
  presents, token portant le scope spreadsheets.readonly (cf. plus bas).

  Installation (PowerShell administrateur, sur le poste qui heberge FUSEAU) :
    $A = New-ScheduledTaskAction -Execute "powershell.exe" `
         -Argument '-NoProfile -ExecutionPolicy Bypass -File "<REPO>\deploy\run_daily_etl.ps1"'
    $T = New-ScheduledTaskTrigger -Daily -At 07:00
    Register-ScheduledTask -TaskName "FUSEAU_Daily_ETL" -Action $A -Trigger $T `
         -Description "FUSEAU : artwork gsheet + Drive qualite, 1x/jour" -RunLevel Limited

  ATTENTION SCOPE OAUTH : le scope spreadsheets.readonly a ete ajoute apres la
  creation du token.json existant. Google ne le signale qu'a la premiere requete
  Sheets, par une erreur "insufficient scope". Si l'etape 1 echoue la-dessus,
  supprimer config\token.json et relancer le script A LA MAIN une fois : un
  navigateur s'ouvre pour le consentement. Impossible en tache planifiee, donc
  a faire avant d'installer la tache.
#>

# Continue et non Stop : les scripts Python journalisent sur stderr, que
# PowerShell transformerait en exception. On se fie au code de sortie.
$ErrorActionPreference = "Continue"

$Repo = Split-Path -Parent $PSScriptRoot
$Py   = Join-Path $Repo ".venv311\Scripts\python.exe"
$ArtworkJson = Join-Path $Repo "data\_artwork.json"

$LogDir = Join-Path $Repo "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Log = Join-Path $LogDir ("daily_etl_{0}.log" -f (Get-Date -Format "yyyyMMdd"))
function Log($m) { $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"; "$ts  $m" | Tee-Object -FilePath $Log -Append }

Set-Location $Repo
Log "=== DEBUT ETL quotidien ==="

# Chaque source est independante : l'echec de l'artwork ne doit pas empecher le
# rafraichissement de la qualite. On compte les echecs et on sort en erreur a la
# fin, pour que le Planificateur de taches les signale sans perdre le reste.
$Echecs = 0

# --- 1. Artwork : lecture directe du gsheet de Clarisse -----------------------
Log "[1/2] artwork : lecture du gsheet LIS-CON-28-0"
& $Py -m src.scripts.etl.transform_artwork --gsheet --out $ArtworkJson *>> $Log
if ($LASTEXITCODE -ne 0) {
    Log "[ERREUR] transform_artwork exit=$LASTEXITCODE (scope OAuth ? partage du classeur ?)"
    $Echecs++
} else {
    # load_artwork est insert-only : le statut appartient a Clarisse, l'ETL ne
    # l'ecrase jamais. Rejouer le script est donc sans risque.
    & $Py -m src.scripts.gmail.load_artwork --file $ArtworkJson *>> $Log
    if ($LASTEXITCODE -ne 0) { Log "[ERREUR] load_artwork exit=$LASTEXITCODE"; $Echecs++ }
    else { Log "[SUCCES] artwork rafraichi" }
}

# --- 2. Qualite : crawl du Drive puis chargement ------------------------------
Log "[2/2] qualite : crawl Drive ANALYSES ET INSPECTIONS"
& $Py -m src.scripts.etl.crawl_drive_qualite --commit *>> $Log
if ($LASTEXITCODE -ne 0) {
    Log "[ERREUR] crawl_drive_qualite exit=$LASTEXITCODE"
    $Echecs++
} else {
    & $Py -m src.scripts.etl.load_qualite_doc_drive --commit *>> $Log
    if ($LASTEXITCODE -ne 0) { Log "[ERREUR] load_qualite_doc_drive exit=$LASTEXITCODE"; $Echecs++ }
    else { Log "[SUCCES] documents qualite rafraichis" }
}

# --- 3. Enrichissements depuis le DWH Sylob on-premise -----------------------
# Ne tournaient pas sur le poste de Marlene faute d'identifiants SYLOB_* dans
# config/.env, ce qui avait ete pris pour un dysfonctionnement du code. Verifie
# le 28/07 depuis le poste d'Antho : 1188 articles enrichis en dimensions, 1195
# en prix et delai, 21 fournisseurs en CA 3 ans.
#
# Si les identifiants manquent, get_sylob_url() leve et les trois etapes
# echouent proprement, sans empecher les deux sources precedentes.
Log "[3/3] enrichissements Sylob (dimensions, referentiel, CA fournisseur)"
foreach ($Mod in @("enrich_dimensions", "enrich_from_sylob", "enrich_ca")) {
    & $Py -m "src.scripts.etl.$Mod" *>> $Log
    if ($LASTEXITCODE -ne 0) {
        Log "[ERREUR] $Mod exit=$LASTEXITCODE (identifiants SYLOB_* dans config/.env ? VPN ?)"
        $Echecs++
    } else {
        Log "[SUCCES] $Mod"
    }
}

if ($Echecs -gt 0) { Log "=== FIN ETL quotidien : $Echecs echec(s) ==="; exit 1 }
Log "=== FIN ETL quotidien OK ==="
exit 0
