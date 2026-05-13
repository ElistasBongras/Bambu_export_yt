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
& $python (Join-Path $scriptDir 'bambu_export_yt_gui.py')
