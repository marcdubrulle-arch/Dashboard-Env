<#
.SYNOPSIS
    Enregistre la tâche planifiée Windows pour l'envoi quotidien du rapport XRAY.
.NOTES
    À exécuter UNE SEULE FOIS, en tant qu'administrateur, depuis PowerShell :
        Right-click PowerShell > "Exécuter en tant qu'administrateur"
        cd "c:\Users\WHDD0146\XRAY Rapport"
        .\register_task.ps1

    La tâche se déclenchera tous les jours à 07:30 (jours ouvrés uniquement).
    Pré-requis : JIRA_TOKEN défini dans les variables d'environnement utilisateur.
#>

$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$PS1Script  = Join-Path $ScriptDir "run_rapport_daily.ps1"
$TaskName   = "XRAY_Rapport_Journalier"
$TaskDesc   = "Envoie chaque matin le rapport XRAY (XITG + XMQ1) par email à marc.dubrulle@orange.com"

# ── Vérification que le script existe ────────────────────────────────────────
if (-not (Test-Path $PS1Script)) {
    Write-Error "Script introuvable : $PS1Script"
    exit 1
}

# ── Vérification / invite pour le token JIRA ─────────────────────────────────
if (-not $env:JIRA_TOKEN -or $env:JIRA_TOKEN -eq "VOTRE_TOKEN_ICI") {
    $token = Read-Host "Entrez votre JIRA_TOKEN (il sera enregistré dans vos variables d'env. utilisateur)"
    [Environment]::SetEnvironmentVariable("JIRA_TOKEN", $token, "User")
    Write-Host "JIRA_TOKEN enregistré dans les variables d'environnement utilisateur." -ForegroundColor Green
}

# ── Définition du déclencheur : lun-ven à 07:30 ──────────────────────────────
$trigger = New-ScheduledTaskTrigger -Weekly `
               -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday `
               -At "07:30"

# ── Action : PowerShell en mode silencieux ────────────────────────────────────
$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$PS1Script`""

# ── Paramètres ───────────────────────────────────────────────────────────────
$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit  (New-TimeSpan -Hours 1) `
    -StartWhenAvailable `
    -WakeToRun:$false `
    -MultipleInstances  IgnoreNew

# ── Principal : s'exécute en tant que l'utilisateur courant (session interactive)
# Nécessaire pour que Outlook COM soit accessible.
$principal = New-ScheduledTaskPrincipal `
    -UserId    $env:USERNAME `
    -LogonType Interactive `
    -RunLevel  Limited

# ── Enregistrement (remplace si existe) ──────────────────────────────────────
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Tâche existante '$TaskName' supprimée." -ForegroundColor Yellow
}

Register-ScheduledTask `
    -TaskName   $TaskName `
    -Trigger    $trigger `
    -Action     $action `
    -Settings   $settings `
    -Principal  $principal `
    -Description $TaskDesc

Write-Host ""
Write-Host "✅ Tâche '$TaskName' enregistrée avec succès." -ForegroundColor Green
Write-Host "   Déclenchement : lundi-vendredi à 07:30"
Write-Host "   Script        : $PS1Script"
Write-Host "   Log           : $(Join-Path $ScriptDir 'run_rapport_daily.log')"
Write-Host ""
Write-Host "Pour tester immédiatement :"
Write-Host "   Start-ScheduledTask -TaskName '$TaskName'"
Write-Host ""
Write-Host "Pour désactiver :"
Write-Host "   Disable-ScheduledTask -TaskName '$TaskName'"
