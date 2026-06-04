"""
Quick check that your Gmail SMTP settings actually work.

Run:  python backend/test_smtp.py you@example.com

It reads SMTP_* from your .env, connects to Gmail, and sends one short test
email to the address you pass on the command line. If it prints "Sent", your
notification settings are good. If it errors, the message tells you what to fix.
"""

import os
import sys
import smtplib
from email.message import EmailMessage
from pathlib import Path

from dotenv import load_dotenv

# Load the real .env from the project root (one level above backend/).
load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=True)


def main():
    """
    Send one test email using the SMTP_* values from .env.
    Parameters: none (reads the recipient from the command line).
    Returns: None.
    """
    if len(sys.argv) < 2:
        print("Usage: python backend/test_smtp.py recipient@example.com")
        return

    recipient = sys.argv[1]

    host = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASSWORD")
    sender = os.getenv("SMTP_FROM") or user

    # Make missing settings obvious instead of failing with a cryptic error.
    missing = []
    if not host:
        missing.append("SMTP_HOST")
    if not user:
        missing.append("SMTP_USER")
    if not password:
        missing.append("SMTP_PASSWORD")
    if missing:
        print("Missing in .env:", ", ".join(missing))
        return

    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = "File Guardian — SMTP test"
    message.set_content(
        "This is a test email from the File Guardian Agent.\n"
        "If you can read this, your Gmail SMTP settings work."
    )

    print(f"Connecting to {host}:{port} as {user} ...")
    try:
        with smtplib.SMTP(host, port, timeout=30) as server:
            server.starttls()
            server.login(user, password)
            server.send_message(message)
    except smtplib.SMTPAuthenticationError:
        print("Login failed. For Gmail you must use a 16-character App "
              "password (not your normal password), and 2-Step Verification "
              "must be on.")
        return
    except Exception as error:
        print("Could not send:", error)
        return

    print(f"Sent. Check the inbox for {recipient}.")


if __name__ == "__main__":
    main()
