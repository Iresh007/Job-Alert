# Autonomous Job Search Intelligence Platform

Git-ready package of the Job Finder system.

## Fastest Way To Run After Clone

### Option A: Docker (Recommended)

```powershell
Copy-Item .env.example .env
powershell -ExecutionPolicy Bypass -File .\scripts\start_docker.ps1
```

Open: `http://127.0.0.1:5050/`

## Public URL Deployment (GitHub -> Render)

This repo now includes:

- `render.yaml` (Render service + Postgres blueprint)
- `.github/workflows/deploy-render.yml` (auto deploy on `main` push)

### One-time setup

1. In Render, create a **Blueprint** service from this GitHub repo.
2. In Render service settings, copy:
- `Deploy Hook` URL
- Public app URL (example: `https://job-alert-app.onrender.com`)
3. In GitHub repo settings, add secrets:
- `RENDER_DEPLOY_HOOK_URL` = Render deploy hook URL
- `RENDER_PUBLIC_URL` = Render app URL (optional but enables health check step)
4. In Render service -> `Environment`, set values for:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `EMAIL_TO`
- `EMAIL_USERNAME` and `EMAIL_PASSWORD` (for SMTP fallback)
- `EMAIL_FROM` (usually same as `EMAIL_USERNAME`)
- `OUTLOOK_CLIENT_ID` (for Graph OAuth mode)

After this, every push to `main` triggers deploy automatically.

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
- Discord alerts for all newly qualified jobs (not only super-priority)
- Discord slash commands to run scans and manage settings directly from server

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
OUTLOOK_GRAPH_SCOPES=https://graph.microsoft.com/Mail.Send,https://graph.microsoft.com/User.Read
OUTLOOK_TOKEN_CACHE_FILE=.outlook_graph_token_cache.bin
TELEGRAM_NOTIFY_ALL_JOBS=true
TELEGRAM_ALERT_MAX_PER_RUN=20
EMAIL_NOTIFY_ALL_JOBS=true
EMAIL_ALERT_MAX_PER_RUN=50
```

For Render deployments, no `.env` file is committed. Configure these keys in Render `Environment`.
If Outlook Graph token is missing, the app now falls back to SMTP when SMTP settings are present.

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

## Discord Setup (Alerts + Settings Control)

Set in `.env`:

```env
DISCORD_BOT_TOKEN=<discord_bot_token>
DISCORD_ALERT_CHANNEL_ID=<channel_id_for_alerts>
DISCORD_ADMIN_ROLE_ID=<optional_admin_role_id>
DISCORD_COMMAND_GUILD_ID=<optional_guild_id_for_fast_command_sync>
DISCORD_ALERT_MAX_PER_RUN=50
```

Bot requirements:

- Invite the bot with `bot` and `applications.commands` scopes.
- Grant `Send Messages` permission in your alert channel.
- If you set `DISCORD_ADMIN_ROLE_ID`, only members with that role (or server admins) can run settings/scan commands.

After restart, use slash commands in your server:

- `/job_help`
- `/job_run`
- `/job_settings`
- `/job_set`
- `/job_add`
- `/job_remove`

`/job_set` supports all profile fields. For list fields (`roles`, `locations`, `skills`, `scan_times`, `excluded_companies`) use comma-separated values.

## Notes

- This repo excludes local-only files (`.env`, `.venv`, logs, results, token cache).
- If you get `Not Found` for a new endpoint, restart server from this repo folder.
- Detailed instructions are in `run.txt`.
