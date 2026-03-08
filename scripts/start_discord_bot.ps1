Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Set-Location $PSScriptRoot\..
$env:PYTHONPATH='.'

.\.venv\Scripts\python scripts\init_db.py
.\.venv\Scripts\python -m uvicorn app.discord_service:app --host 0.0.0.0 --port 5051
