$ErrorActionPreference = 'Stop'

function Get-PythonCommand {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) { return $py.Source }
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) { return $python.Source }
    throw "Python n'est pas trouvé. Installez Python 3.10+ et relancez ce script."
}

$python = Get-PythonCommand
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$configPath = Join-Path $scriptDir 'config.json'
if (-not (Test-Path $configPath)) {
    Write-Error "Fichier de configuration introuvable : $configPath. Lancez d'abord setup.ps1."
    exit 1
}

$dryRunAnswer = Read-Host 'Faire une simulation sans upload ? (o/n)'
$dryRun = $dryRunAnswer -match '^[Oo]'
$watchAnswer = Read-Host 'Intervalle de surveillance en secondes (0 = une seule passe)'
if ($watchAnswer -match '^[0-9]+$') {
    $watch = [int]$watchAnswer
} else {
    $watch = 0
}

$args = @('--config', $configPath)
if ($dryRun) { $args += '--dry-run' }
if ($watch -gt 0) { $args += '--watch'; $args += $watch }

Write-Host 'Lancement du traitement...' -ForegroundColor Cyan
& $python (Join-Path $scriptDir 'bambu_export_yt.py') @args
