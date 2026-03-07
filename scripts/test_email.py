from __future__ import annotations

import argparse

from app.config import settings
from app.notifications import NotificationService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Send a test email notification")
    parser.add_argument(
        "--subject",
        type=str,
        default="Job Finder Email Test",
        help="Email subject",
    )
    parser.add_argument(
        "--message",
        type=str,
        default="Test email from Autonomous Job Search Intelligence Platform",
        help="Email message body",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    print(f"Email provider: {(settings.email_provider or 'smtp').lower()}")
    ok = NotificationService().send_email(args.subject, args.message)
    if ok:
        print("Email test sent successfully.")
    else:
        print("Email test failed. Check .env and auth setup for selected provider.")


if __name__ == "__main__":
    main()
