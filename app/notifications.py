from __future__ import annotations

import smtplib
from email.mime.text import MIMEText
from typing import List

import httpx

from app.config import settings
from app.outlook_graph import acquire_access_token_silent


class NotificationService:
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
        lines = ["SUPER PRIORITY JOBS - APPLY WITHIN 6 HOURS"]
        for job in jobs[:5]:
            lines.append(f"- {job['title']} | {job['company']} | {job['location']}")
            lines.append(f"  Score: {job['interview_probability']} | URL: {job['url']}")
            if job.get("is_ultra_low_competition"):
                lines.append("  Flag: ULTRA LOW COMPETITION")
        body = "\n".join(lines)
        await self.send_telegram(body)
        self.send_email("SUPER PRIORITY JOB ALERT", body)
