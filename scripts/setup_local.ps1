param(
  [switch]$SkipPlaywright
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Set-Location $PSScriptRoot\..

if (-not (Test-Path '.env')) {
  Copy-Item '.env.example' '.env'
  Write-Host 'Created .env from .env.example'
}

if (-not (Test-Path '.venv')) {
  py -3.13 -m venv .venv
}

$py = '.\.venv\Scripts\python.exe'
& $py -m pip install --upgrade pip
& $py -m pip install -r requirements.txt

if (-not $SkipPlaywright) {
  & $py -m playwright install chromium
}

Write-Host 'Setup complete. Next: run scripts\start_local.ps1'
