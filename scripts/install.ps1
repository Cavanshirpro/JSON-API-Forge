[CmdletBinding()]
param([switch]$Dev)

$ErrorActionPreference = "Stop"
$python = if ($env:PYTHON) { $env:PYTHON } else { "python" }
& $python -c 'import sys; raise SystemExit(0 if (3, 11) <= sys.version_info[:2] <= (3, 14) else "JSON API Forge requires Python 3.11-3.14")'
& $python -m venv .venv
$venvPython = Join-Path $PWD ".venv\Scripts\python.exe"
& $venvPython -m pip install --upgrade pip
$target = if ($Dev) { ".[dev]" } else { "." }
& $venvPython -m pip install -e $target
& $venvPython -m pip check
Write-Host "Installed JSON API Forge into .venv"
Write-Host "Activate it, then run: forge new MyService --slug my-service"
