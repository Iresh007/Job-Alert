from __future__ import annotations

from app.outlook_graph import run_device_code_login


def main() -> None:
    ok, msg = run_device_code_login()
    if ok:
        print(msg)
        print("You can now run: python scripts/test_email.py")
    else:
        print(f"Outlook OAuth setup failed: {msg}")


if __name__ == "__main__":
    main()
