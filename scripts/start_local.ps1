Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Set-Location $PSScriptRoot\..
$env:PYTHONPATH='.'

.\.venv\Scripts\python scripts\init_db.py
Start-Process -FilePath '.\.venv\Scripts\python.exe' `
  -ArgumentList @('-m', 'uvicorn', 'app.discord_service:app', '--host', '0.0.0.0', '--port', '5051') `
  -WorkingDirectory (Get-Location).Path
.\.venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 5050
