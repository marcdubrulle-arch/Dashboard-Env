<#
.SYNOPSIS
    Génère les rapports XRAY pour XITG et XMQ1, puis les publie sur Confluence.
.DESCRIPTION
    Lance xray_rapport_du_jour.py pour chaque environnement et met à jour
    les pages Confluence correspondantes sous la page parent 468779106.
.NOTES
    Prérequis : JIRA_TOKEN et CONFLUENCE_TOKEN dans les variables d'env. utilisateur.
#>

$ErrorActionPreference = "Stop"

# ── Chemins ──────────────────────────────────────────────────────────────────
$ScriptDir      = $PSScriptRoot
$PythonScript   = Join-Path $ScriptDir "xray_rapport_du_jour.py"
$LogFile        = Join-Path $ScriptDir "run_rapport_daily.log"
$ParentPageId   = "468779106"
$Today          = Get-Date -Format "dd/MM/yyyy"

# ── Résolution Python (portable) ─────────────────────────────────────────────
$PythonCommand = $null
if (Get-Command python -ErrorAction SilentlyContinue) {
    $PythonCommand = @("python")
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $PythonCommand = @("py", "-3")
} else {
    Write-Host "[ERREUR] Python introuvable dans le PATH." -ForegroundColor Red
    exit 1
}

function Invoke-Python {
    param(
        [Parameter(Mandatory=$true)]
        [string[]]$Args
    )

    if ($PythonCommand.Length -gt 1) {
        & $PythonCommand[0] $PythonCommand[1] @Args
    } else {
        & $PythonCommand[0] @Args
    }
}

$PageTitles = @{
    "XITG" = "Rapport XRAY - XITG"
    "XMQ1" = "Rapport XRAY - XMQ1"
}

# ── Logger ────────────────────────────────────────────────────────────────────
function Write-Log([string]$msg) {
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  $msg"
    Write-Host $line
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

# ── Chargement des tokens depuis le registre si absents de la session ───────
foreach ($varName in @('JIRA_TOKEN','CONFLUENCE_TOKEN')) {
    if (-not (Get-Item "env:$varName" -ErrorAction SilentlyContinue)) {
        $val = (Get-ItemProperty -Path 'HKCU:\Environment' -Name $varName -ErrorAction SilentlyContinue).$varName
        if ($val) { Set-Item "env:$varName" $val }
    }
}

# ── Vérification du token JIRA ───────────────────────────────────────────────
if (-not $env:JIRA_TOKEN -or $env:JIRA_TOKEN -eq 'VOTRE_TOKEN_ICI') {
    Write-Log '[ERREUR] JIRA_TOKEN non défini. Lancez register_task.ps1 pour le configurer.'
    exit 1
}
if (-not $env:CONFLUENCE_TOKEN) {
    Write-Log '[ERREUR] CONFLUENCE_TOKEN non défini dans le registre.'
    exit 1
}

# ── Génération + publication Confluence pour chaque environnement ─────────────
$DateStr = Get-Date -Format "yyyy-MM-dd"
foreach ($xrayEnv in @('XITG', 'XMQ1')) {
    $outFile   = Join-Path $ScriptDir "rapport_${xrayEnv}_${DateStr}.html"
    $pageTitle = $PageTitles[$xrayEnv]
    Write-Log "Génération et publication Confluence pour $xrayEnv (page : '$pageTitle') ..."
    try {
        $argList = @(
            $PythonScript,
            '--env',                   $xrayEnv,
            '--output',                $outFile,
            '--confluence',
            '--confluence-page-title', $pageTitle,
            '--confluence-parent-id',  $ParentPageId
        )
        $env:PYTHONUTF8 = '1'
        $confUrl = ''
        Invoke-Python -Args $argList | ForEach-Object {
            Write-Host $_
            if ($_ -match '\[CONFLUENCE_URL\]') {
                $confUrl = $_ -replace '.*\[CONFLUENCE_URL\]\s*', ''
            }
        }
        if ($LASTEXITCODE -ne 0) { throw "Code de sortie $LASTEXITCODE" }
        if ($confUrl) {
            Write-Log "  → $xrayEnv publie sur Confluence avec succes : $confUrl"
        } else {
            Write-Log "  → $xrayEnv publie sur Confluence avec succes."
        }
    } catch {
        Write-Log "[ERREUR] Echec $xrayEnv : $_"
    }
}

Write-Log 'Rapport journalier termine.'

# ── Génération de la page d'accueil ──────────────────────────────────────────
Write-Log 'Génération de la page d''accueil (accueil.html) ...'
try {
    $env:PYTHONUTF8 = '1'
    $accueilScript = Join-Path $ScriptDir "generate_accueil.py"
    $accueilFile   = Join-Path $ScriptDir "accueil.html"
    Invoke-Python -Args @($accueilScript, '--output', $accueilFile) | ForEach-Object { Write-Host $_ }
    if ($LASTEXITCODE -eq 0) {
        Write-Log "  → Page d'accueil générée : $accueilFile"
    } else {
        Write-Log "[ERREUR] Génération page d'accueil échouée (code $LASTEXITCODE)"
    }
} catch {
    Write-Log "[ERREUR] Génération page d'accueil : $_"
}
