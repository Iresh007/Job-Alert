# Autonomous Job Search Intelligence Platform

Git-ready package of the Job Finder system.

## Fastest Way To Run After Clone

### Option A: Docker (Recommended)

```powershell
Copy-Item .env.example .env
powershell -ExecutionPolicy Bypass -File .\scripts\start_docker.ps1
```

Open: `http://127.0.0.1:5050/`

### Option B: Local Python

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_local.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\start_local.ps1
```

Open: `http://127.0.0.1:5050/`

## What This Includes

- Job discovery (ATS + optional board scraping)
- Normalization and dedupe
- Interview probability scoring and ranking
- Scheduler with fixed-time runs + 6-hour interval run
- Dashboard with settings, next scheduled runs, and Excel export
- Telegram alerts
- Outlook OAuth (Graph API) email alerts

## Key APIs

- `GET /api/health`
- `POST /api/scan/run`
- `GET /api/jobs?min_score=70`
- `GET /api/analytics`
- `GET /api/scheduler/next-runs`
- `GET /api/jobs/export/excel?min_score=70&limit=2000`

## Outlook Email Setup (OAuth)

Set in `.env`:

```env
EMAIL_PROVIDER=outlook_graph
EMAIL_TO=<receiver_email>
OUTLOOK_CLIENT_ID=<azure_app_client_id>
OUTLOOK_TENANT=consumers
OUTLOOK_GRAPH_SCOPES=https://graph.microsoft.com/Mail.Send,https://graph.microsoft.com/User.Read,offline_access
OUTLOOK_TOKEN_CACHE_FILE=.outlook_graph_token_cache.bin
```

One-time auth:

```powershell
$env:PYTHONPATH='.'
.\.venv\Scripts\python scripts\setup_outlook_graph_auth.py
```

Test email:

```powershell
$env:PYTHONPATH='.'
.\.venv\Scripts\python scripts\test_email.py --subject "Email connected" --message "Outlook Graph is working"
```

## Notes

- This repo excludes local-only files (`.env`, `.venv`, logs, results, token cache).
- If you get `Not Found` for a new endpoint, restart server from this repo folder.
- Detailed instructions are in `run.txt`.
