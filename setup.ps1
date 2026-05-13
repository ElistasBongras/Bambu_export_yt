$ErrorActionPreference = 'Stop'

function Get-PythonCommand {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) { return $py.Source }
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) { return $python.Source }
    throw "Python n'est pas trouvé. Installez Python 3.10+ et relancez ce script."
}

$python = Get-PythonCommand
Write-Host '== Configuration du projet Bambu_export_yt ==' -ForegroundColor Cyan

$sourceDir = Read-Host "Chemin du dossier contenant les vidéos timelapse (source_dir)"
$destDir = Read-Host "Chemin du dossier de destination pour les fichiers renommés (dest_dir)"
$clientSecrets = Read-Host "Nom du fichier client_secrets OAuth (par défaut client_secrets.json)"
if ([string]::IsNullOrWhiteSpace($clientSecrets)) { $clientSecrets = 'client_secrets.json' }
$credentialsFile = Read-Host "Nom du fichier de token d'authentification YouTube (par défaut youtube_credentials.json)"
if ([string]::IsNullOrWhiteSpace($credentialsFile)) { $credentialsFile = 'youtube_credentials.json' }

$defaultTitle = Read-Host 'Titre YouTube par défaut (utilisez {date} pour la date)'
if ([string]::IsNullOrWhiteSpace($defaultTitle)) { $defaultTitle = 'Timelapse imprimante 3D BambuLab X1C - {date}' }
$defaultDescription = Read-Host 'Description YouTube par défaut'
if ([string]::IsNullOrWhiteSpace($defaultDescription)) { $defaultDescription = 'Timelapse automatique BambuLab X1C uploadé sur YouTube.' }
$tags = Read-Host 'Tags YouTube séparés par des virgules'
if ([string]::IsNullOrWhiteSpace($tags)) { $tags = 'BambuLab,X1C,impression 3D,timelapse' }
$privacy = Read-Host 'Statut de confidentialité YouTube (private, unlisted, public)'
if ([string]::IsNullOrWhiteSpace($privacy)) { $privacy = 'private' }
$category = Read-Host 'ID de catégorie YouTube (par défaut 28 = Science & Technology)'
if ([string]::IsNullOrWhiteSpace($category)) { $category = '28' }

$config = [PSCustomObject]@{
    source_dir = $sourceDir
    dest_dir = $destDir
    rename_pattern = 'BambuLab_X1C_{date}_{time}'
    processed_state_file = 'processed_videos.json'
    youtube = [PSCustomObject]@{
        client_secrets_file = $clientSecrets
        credentials_file = $credentialsFile
        default_title = $defaultTitle
        default_description = $defaultDescription
        privacy_status = $privacy
        tags = ($tags -split ',') | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne '' }
        category_id = $category
    }
}

$configPath = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Definition) 'config.json'
$config | ConvertTo-Json -Depth 5 | Out-File -FilePath $configPath -Encoding utf8NoBom

Write-Host "Fichier de configuration créé : $configPath" -ForegroundColor Green
Write-Host 'Installation des dépendances Python...' -ForegroundColor Cyan
& $python -m pip install -r (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Definition) 'requirements.txt')

Write-Host ''
Write-Host 'Configuration terminée.' -ForegroundColor Green
Write-Host 'Placez votre fichier client OAuth dans le dossier du projet et nommez-le' -NoNewline
Write-Host " $clientSecrets" -ForegroundColor Yellow
Write-Host 'Ensuite, lancez' -NoNewline
Write-Host ' .\run.ps1' -ForegroundColor Yellow
