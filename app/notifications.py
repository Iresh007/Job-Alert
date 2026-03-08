from __future__ import annotations

import asyncio
import smtplib
from email.mime.text import MIMEText
from typing import List

import httpx

from app.config import settings
from app.outlook_graph import acquire_access_token_silent


class NotificationService:
    @staticmethod
    def _format_job_lines(jobs: List[dict]) -> List[str]:
        lines: List[str] = []
        for idx, job in enumerate(jobs, start=1):
            score = float(job.get("interview_probability") or 0)
            flags = []
            if job.get("is_super_priority"):
                flags.append("SUPER")
            if job.get("is_ultra_low_competition"):
                flags.append("ULTRA-LOW-COMP")
            flag_text = f" [{' | '.join(flags)}]" if flags else ""
            lines.append(
                f"{idx}. {job.get('title', 'Unknown Role')} | {job.get('company', 'Unknown Company')} | "
                f"{job.get('location', 'Unknown Location')} | Score {score:.1f}{flag_text}"
            )
            lines.append(f"   {job.get('url', '')}")
        return lines

    async def notify_all_jobs(self, jobs: List[dict], run_summary: dict) -> None:
        if not jobs:
            return

        run_id = run_summary.get("run_id", "N/A")
        fetched = run_summary.get("fetched", 0)
        inserted = run_summary.get("inserted", 0)
        qualified = run_summary.get("qualified", 0)
        super_priority = run_summary.get("super_priority", 0)

        if settings.telegram_notify_all_jobs:
            max_tg = max(int(settings.telegram_alert_max_per_run or 20), 1)
            tg_jobs = jobs[:max_tg]
            tg_lines = [
                f"ALL JOB ALERTS | Scan #{run_id}",
                f"Fetched: {fetched} | Inserted: {inserted} | Qualified: {qualified} | Super: {super_priority}",
                f"Showing: {len(tg_jobs)}/{len(jobs)}",
                "",
            ]
            tg_lines.extend(self._format_job_lines(tg_jobs))
            for chunk in self._split_discord_messages(tg_lines, max_chars=3800):
                await self.send_telegram(chunk)

        if settings.email_notify_all_jobs:
            max_email = max(int(settings.email_alert_max_per_run or 50), 1)
            email_jobs = jobs[:max_email]
            email_lines = [
                f"ALL JOB ALERTS | Scan #{run_id}",
                f"Fetched: {fetched} | Inserted: {inserted} | Qualified: {qualified} | Super: {super_priority}",
                f"Showing: {len(email_jobs)}/{len(jobs)}",
                "",
            ]
            email_lines.extend(self._format_job_lines(email_jobs))
            self.send_email(f"ALL JOB ALERTS | Scan #{run_id}", "\n".join(email_lines))

    @staticmethod
    def _split_discord_messages(lines: List[str], max_chars: int = 1900) -> List[str]:
        chunks: List[str] = []
        current: List[str] = []
        current_size = 0
        for raw_line in lines:
            line = raw_line or ""
            line_size = len(line) + 1
            if line_size > max_chars:
                if current:
                    chunks.append("\n".join(current))
                    current = []
                    current_size = 0
                chunks.append(line[:max_chars])
                continue
            if current_size + line_size > max_chars and current:
                chunks.append("\n".join(current))
                current = [line]
                current_size = line_size
            else:
                current.append(line)
                current_size += line_size
        if current:
            chunks.append("\n".join(current))
        return chunks

    async def send_discord_message(self, message: str) -> bool:
        token = (settings.discord_bot_token or "").strip()
        channel_id = settings.discord_alert_channel_id_int
        if not token or not channel_id:
            return False

        url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
        headers = {"Authorization": f"Bot {token}", "Content-Type": "application/json"}
        payload = {"content": message[:2000]}

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(url, headers=headers, json=payload)
                if response.status_code == 429:
                    retry_after = float(response.json().get("retry_after", 1))
                    await asyncio.sleep(max(retry_after, 0))
                    response = await client.post(url, headers=headers, json=payload)
                return response.status_code in (200, 201)
        except Exception:
            return False

    async def notify_discord_run(self, jobs: List[dict], run_summary: dict) -> None:
        if not settings.discord_bot_token or not settings.discord_alert_channel_id_int:
            return

        run_id = run_summary.get("run_id", "N/A")
        fetched = run_summary.get("fetched", 0)
        inserted = run_summary.get("inserted", 0)
        qualified = run_summary.get("qualified", 0)
        super_priority = run_summary.get("super_priority", 0)
        error = run_summary.get("error")

        if error:
            await self.send_discord_message(
                f"Scan #{run_id} failed.\nFetched: {fetched} | Inserted: {inserted} | Qualified: {qualified}\nError: {error}"
            )
            return

        header = (
            f"Scan #{run_id} completed.\n"
            f"Fetched: {fetched} | Inserted: {inserted} | Qualified: {qualified} | Super Priority: {super_priority}"
        )
        await self.send_discord_message(header)

        if not jobs:
            await self.send_discord_message("No new qualified jobs this run.")
            return

        max_jobs = max(int(settings.discord_alert_max_per_run or 50), 1)
        selected_jobs = jobs[:max_jobs]
        lines: List[str] = [f"New Job Alerts ({len(selected_jobs)}/{len(jobs)})"]
        if len(jobs) > len(selected_jobs):
            lines.append(f"Showing first {len(selected_jobs)} jobs due to DISCORD_ALERT_MAX_PER_RUN limit.")
        lines.append("")
        lines.extend(self._format_job_lines(selected_jobs))

        for chunk in self._split_discord_messages(lines):
            await self.send_discord_message(chunk)

    async def send_telegram(self, message: str) -> bool:
        if not settings.telegram_bot_token or not settings.telegram_chat_id:
            return False
        url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
        payload = {"chat_id": settings.telegram_chat_id, "text": message, "disable_web_page_preview": True}
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(url, json=payload)
                return response.status_code == 200
        except Exception:
            return False

    def send_email(self, subject: str, message: str) -> bool:
        provider = (settings.email_provider or "smtp").lower()
        if provider == "outlook_graph" and self.send_email_via_outlook_graph(subject, message):
            return True
        if provider == "outlook_graph":
            print("Outlook Graph send failed; falling back to SMTP if configured.")
        return self.send_email_via_smtp(subject, message)

    def send_email_via_smtp(self, subject: str, message: str) -> bool:
        if not settings.email_host or not settings.email_to:
            return False
        msg = MIMEText(message, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = settings.email_from or settings.email_username
        msg["To"] = settings.email_to
        try:
            with smtplib.SMTP(settings.email_host, settings.email_port, timeout=20) as smtp:
                smtp.starttls()
                if settings.email_username:
                    smtp.login(settings.email_username, settings.email_password)
                smtp.send_message(msg)
            return True
        except Exception:
            return False

    def send_email_via_outlook_graph(self, subject: str, message: str) -> bool:
        if not settings.email_to:
            return False
        token, error = acquire_access_token_silent()
        if not token:
            print(f"Outlook Graph email disabled: {error}")
            return False

        payload = {
            "message": {
                "subject": subject,
                "body": {"contentType": "Text", "content": message},
                "toRecipients": [{"emailAddress": {"address": settings.email_to}}],
            },
            "saveToSentItems": "true",
        }
        try:
            with httpx.Client(timeout=20) as client:
                response = client.post(
                    "https://graph.microsoft.com/v1.0/me/sendMail",
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                    json=payload,
                )
            return response.status_code in (200, 202)
        except Exception:
            return False

    async def notify_super_priority(self, jobs: List[dict]) -> None:
        if not jobs:
            return
        should_telegram = not settings.telegram_notify_all_jobs
        should_email = not settings.email_notify_all_jobs
        if not should_telegram and not should_email:
            return
        lines = ["SUPER PRIORITY JOBS - APPLY WITHIN 6 HOURS"]
        for job in jobs[:5]:
            lines.append(f"- {job['title']} | {job['company']} | {job['location']}")
            lines.append(f"  Score: {job['interview_probability']} | URL: {job['url']}")
            if job.get("is_ultra_low_competition"):
                lines.append("  Flag: ULTRA LOW COMPETITION")
        body = "\n".join(lines)
        if should_telegram:
            await self.send_telegram(body)
        if should_email:
            self.send_email("SUPER PRIORITY JOB ALERT", body)
