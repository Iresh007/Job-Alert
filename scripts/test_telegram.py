from __future__ import annotations

import argparse
import asyncio

from app.notifications import NotificationService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Send a test Telegram notification")
    parser.add_argument(
        "--message",
        type=str,
        default="Test notification from Autonomous Job Search Intelligence Platform",
        help="Message text to send",
    )
    return parser


async def main() -> None:
    args = build_parser().parse_args()
    ok = await NotificationService().send_telegram(args.message)
    if ok:
        print("Telegram test message sent successfully.")
    else:
        print("Telegram test failed. Check TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env.")


if __name__ == "__main__":
    asyncio.run(main())
