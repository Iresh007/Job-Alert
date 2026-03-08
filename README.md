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

- `render.yaml` (free Render blueprint: 1 Postgres + 2 web services)
- `.github/workflows/deploy-render.yml` (auto deploy on `main` push)

### One-time setup

1. In Render, create a **Blueprint** from this GitHub repo.
2. Render will create:
- `job-alert-db` free Postgres
- `job-alert-app` free web service for the dashboard/API
- `job-alert-discord-bot` free web service for Discord commands, queued scans, and notifications
3. In Render service settings, copy:
- `Deploy Hook` URL
- Public app URL (example: `https://job-alert-app.onrender.com`)
4. In GitHub repo settings, add secrets:
- `RENDER_DEPLOY_HOOK_URL` = Render deploy hook URL
- `RENDER_PUBLIC_URL` = Render app URL (optional but enables health check step)
5. In Render service -> `Environment`, set values for:
- `job-alert-app`
  - `ADMIN_API_TOKEN`
- `job-alert-discord-bot`
  - `DISCORD_BOT_TOKEN`
  - `DISCORD_ALERT_CHANNEL_ID`
  - `DISCORD_ADMIN_ROLE_ID`
  - `DISCORD_COMMAND_GUILD_ID`
  - `TELEGRAM_BOT_TOKEN`
  - `TELEGRAM_CHAT_ID`
  - `EMAIL_PROVIDER=outlook_graph`
  - `EMAIL_TO`
  - `OUTLOOK_CLIENT_ID`
  - `OUTLOOK_TENANT=consumers`
  - `OUTLOOK_GRAPH_SCOPES=https://graph.microsoft.com/Mail.Send,https://graph.microsoft.com/User.Read`
  - `OUTLOOK_TOKEN_CACHE_FILE=.outlook_graph_token_cache.bin`

After this, every push to `main` triggers deploy automatically.

### Free Render Architecture

- `job-alert-app`: dashboard, REST API, scheduler, admin fallback API
- `job-alert-discord-bot`: Discord gateway, queued `/job_run`, embedded scan worker, notifications
- `job-alert-db`: shared persistent Postgres database

`/job_run` no longer runs the scan inline. It creates a queued scan request, replies immediately, and reports the result when processing finishes.

### Option B: Local Python

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_local.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\start_local.ps1
```

Open: `http://127.0.0.1:5050/`
Discord bot health: `http://127.0.0.1:5051/health`

## What This Includes

- Job discovery (ATS + optional board scraping)
- Normalization and dedupe
- Interview probability scoring and ranking
- Scheduler with fixed-time runs + 6-hour interval run
- Dashboard with settings, next scheduled runs, and Excel export
- Persistent queued scan requests with status tracking
- Telegram alerts
- Outlook OAuth (Graph API) email alerts
- Discord alerts for all newly qualified jobs (not only super-priority)
- Discord slash commands to queue scans and manage settings directly from server
- Admin fallback API to trigger scans even if Discord is unavailable

## Key APIs

- `GET /api/health`
- `POST /api/scan/run`
- `GET /api/scan/requests/{request_id}`
- `POST /api/admin/scan/run`
- `GET /api/admin/scan/requests/{request_id}`
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
If Outlook Graph token is missing, the app falls back to SMTP when SMTP settings are present. On free Render, prefer Outlook Graph because outbound SMTP ports are restricted.

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
- `/job_status`
- `/job_settings`
- `/job_set`
- `/job_add`
- `/job_remove`

`/job_run` now queues a scan request, acknowledges immediately, and posts the result when complete.

`/job_set` supports all profile fields. For list fields (`roles`, `locations`, `skills`, `scan_times`, `excluded_companies`) use comma-separated values.

## Admin Fallback API

If Discord is unavailable, trigger and inspect scans through the API.

Set in `.env` or Render:

```env
ADMIN_API_TOKEN=<strong_random_secret>
```

Trigger a scan:

```powershell
curl -X POST https://<your-app>.onrender.com/api/admin/scan/run `
  -H "X-Admin-Token: <ADMIN_API_TOKEN>"
```

Read request status:

```powershell
curl https://<your-app>.onrender.com/api/admin/scan/requests/<request_id> `
  -H "X-Admin-Token: <ADMIN_API_TOKEN>"
```

## Notes

- This repo excludes local-only files (`.env`, `.venv`, logs, results, token cache).
- The free Render blueprint uses 2 web services and 1 free Postgres database.
- `job-alert-discord-bot/health` reports both Discord bot health and embedded scan worker health.
- If you get `Not Found` for a new endpoint, restart from this repository folder or redeploy the Render service.
- Detailed instructions are in `run.txt`.
