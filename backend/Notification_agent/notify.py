"""
Notification agent — tells people when a file fails validation.

When a run fails and its profile has notify_on_failure turned on, this builds
an email (file name, status, the main issues, the recommended action, and a
reference to the run) and sends it.

If real SMTP settings are present in .env it sends a real email. If not, it
runs in "log-only" mode: it writes the whole message to the log and reports
success, so the rest of the pipeline keeps working without any mail setup.
"""

import os
import sys
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from logging_setup import get_logger  # noqa: E402
import db  # noqa: E402

log = get_logger("Notification")

# SMTP settings still come from the .env file (host, user, password, etc.).
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")


def notify_failure(profile, file_name, status, summary, issues, run_id,
                   errors=None, warnings=None):
    """
    Send a failure notification for one run (plain-text + HTML email).
    Parameters: profile (dict), file_name (str), status (str),
        summary (dict from the explanation agent), issues (list), run_id (str),
        errors (int or None), warnings (int or None) — the true totals.
    Returns: dict {status, recipients, channel, subject, sent_at}.
    """
    # Only failures are worth a notification, and only if the profile asks.
    if status != "failed" or not profile.get("notify_on_failure"):
        return blank_result("not_required")

    recipients = recipients_for(profile)
    if not recipients:
        log.warning("No recipients configured — skipping notification for %s", file_name)
        return blank_result("not_required")

    # If the caller didn't pass true totals, count what we have.
    if errors is None or warnings is None:
        errors, warnings = count_severities(issues)

    subject = f"[File Guardian] {file_name} failed validation"
    text_body = build_text(file_name, status, summary, issues, run_id, errors, warnings)
    html_body = build_html(profile, file_name, summary, issues, run_id, errors, warnings)
    channel = "email" if smtp_configured() else "email (log-only)"
    sent_at = datetime.now(timezone.utc).isoformat()

    try:
        send_email(recipients, subject, text_body, html_body)
        result_status = "sent"
    except Exception as error:
        log.exception("Failed to send notification for %s: %s", file_name, error)
        result_status = "failed"

    return {
        "status": result_status,
        "recipients": recipients,
        "channel": channel,
        "subject": subject,
        "sent_at": sent_at,
    }


def count_severities(issues):
    """
    Count errors and warnings in an issue list.
    Parameters: issues (list of issue dicts).
    Returns: tuple (errors int, warnings int).
    """
    errors = 0
    warnings = 0
    for issue in issues:
        if issue["severity"] == "error":
            errors += 1
        elif issue["severity"] == "warning":
            warnings += 1
    return errors, warnings


def blank_result(status):
    """
    Build an empty notification result (used when no email is sent).
    Parameters: status (str).
    Returns: dict {status, recipients, channel, subject, sent_at}.
    """
    return {
        "status": status,
        "recipients": [],
        "channel": None,
        "subject": None,
        "sent_at": None,
    }


def smtp_configured():
    """
    Check whether real SMTP credentials are available in the environment.
    Parameters: none.
    Returns: bool.
    """
    return bool(os.getenv("SMTP_HOST") and os.getenv("SMTP_USER") and os.getenv("SMTP_PASSWORD"))


def recipients_for(profile):
    """
    Work out who to email for this profile.
    Parameters: profile (dict).
    Returns: list of email addresses (str). Empty if none are configured.
    """
    recipients = profile.get("email_recipients") or []
    if recipients:
        return recipients

    # Fall back to the global default recipients in settings.
    settings = get_settings()
    return settings.get("default_recipients") or []


def dashboard_url():
    """
    Work out the dashboard link to put in the email.
    Parameters: none.
    Returns: str (defaults to the local frontend).
    """
    return os.getenv("DASHBOARD_URL") or "http://localhost:6200"


def top_issues(issues, limit=10):
    """
    Pick the first few issues to show as examples in the email.
    Parameters: issues (list), limit (int).
    Returns: list of issue dicts (at most `limit`).
    """
    chosen = []
    for issue in issues:
        chosen.append(issue)
        if len(chosen) >= limit:
            break
    return chosen


def build_text(file_name, status, summary, issues, run_id, errors, warnings):
    """
    Write the plain-text body of the notification email (for plain clients).
    Parameters: file_name (str), status (str), summary (dict), issues (list),
        run_id (str), errors (int), warnings (int).
    Returns: str.
    """
    lines = []
    lines.append(f"File: {file_name}")
    lines.append(f"Status: {status.upper()}")
    lines.append(f"Problems: {errors} error(s), {warnings} warning(s)")
    lines.append("")

    if summary.get("summary"):
        lines.append("Summary:")
        lines.append(summary["summary"])
        lines.append("")
    if summary.get("impact"):
        lines.append("Likely impact:")
        lines.append(summary["impact"])
        lines.append("")
    if summary.get("action"):
        lines.append("Recommended action:")
        lines.append(summary["action"])
        lines.append("")

    examples = top_issues(issues)
    if examples:
        lines.append("Example issues:")
        for issue in examples:
            where = issue.get("location") or issue.get("column_name") or ""
            prefix = f"[{issue['severity'].upper()}]"
            if where:
                lines.append(f"  {prefix} {where}: {issue['message']}")
            else:
                lines.append(f"  {prefix} {issue['message']}")
        lines.append("")

    lines.append(f"Validation run reference: {run_id}")
    lines.append(f"Open the dashboard: {dashboard_url()}")
    return "\n".join(lines)


def escape_html(text):
    """
    Make a value safe to drop inside HTML (so a stray < or & can't break it).
    Parameters: text (anything).
    Returns: str.
    """
    return (str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;"))


def build_html(profile, file_name, summary, issues, run_id, errors, warnings):
    """
    Write a clean HTML body that drops the AI's summary/impact/action into a
    branded layout, with a small table of example issues.
    Parameters: profile (dict), file_name (str), summary (dict), issues (list),
        run_id (str), errors (int), warnings (int).
    Returns: str (an HTML document).
    """
    profile_name = profile.get("name") or "—"

    # The three AI sections (only shown if the AI/template filled them in).
    blocks = []
    if summary.get("summary"):
        blocks.append(ai_block("Summary", summary["summary"]))
    if summary.get("impact"):
        blocks.append(ai_block("Likely impact", summary["impact"]))
    if summary.get("action"):
        blocks.append(ai_block("Recommended action", summary["action"]))
    ai_html = "".join(blocks)

    # A small table of example issues.
    rows = []
    for issue in top_issues(issues):
        colour = "#b91c1c" if issue["severity"] == "error" else "#b45309"
        where = issue.get("location") or issue.get("column_name") or "—"
        rows.append(
            "<tr>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #eee;color:{colour};"
            f"font-weight:600;white-space:nowrap'>{escape_html(issue['severity'].upper())}</td>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #eee;white-space:nowrap'>{escape_html(where)}</td>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #eee'>{escape_html(issue['message'])}</td>"
            "</tr>"
        )
    issues_table = ""
    if rows:
        issues_table = (
            "<h3 style='margin:24px 0 8px;font-size:14px;color:#0f172a'>Example issues</h3>"
            "<table style='border-collapse:collapse;width:100%;font-size:13px'>"
            "<tr style='background:#f8fafc;text-align:left'>"
            "<th style='padding:6px 10px;border-bottom:1px solid #e2e8f0'>Severity</th>"
            "<th style='padding:6px 10px;border-bottom:1px solid #e2e8f0'>Location</th>"
            "<th style='padding:6px 10px;border-bottom:1px solid #e2e8f0'>Message</th>"
            "</tr>" + "".join(rows) + "</table>"
        )

    return f"""\
<!doctype html>
<html>
<body style="margin:0;background:#f1f5f9;padding:24px;
             font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#0f172a">
  <div style="max-width:600px;margin:0 auto;background:#ffffff;border-radius:12px;
              overflow:hidden;border:1px solid #e2e8f0">
    <div style="background:#b91c1c;color:#ffffff;padding:18px 24px">
      <div style="font-size:13px;letter-spacing:.5px;opacity:.85">FILE GUARDIAN</div>
      <div style="font-size:18px;font-weight:700;margin-top:2px">Validation failed</div>
    </div>
    <div style="padding:24px">
      <table style="width:100%;font-size:14px;margin-bottom:8px">
        <tr><td style="color:#64748b;padding:3px 0;width:90px">File</td>
            <td style="font-weight:600">{escape_html(file_name)}</td></tr>
        <tr><td style="color:#64748b;padding:3px 0">Profile</td>
            <td>{escape_html(profile_name)}</td></tr>
        <tr><td style="color:#64748b;padding:3px 0">Problems</td>
            <td><span style="color:#b91c1c;font-weight:600">{errors} error(s)</span>
                &nbsp;·&nbsp;{warnings} warning(s)</td></tr>
      </table>
      {ai_html}
      {issues_table}
      <div style="margin-top:28px">
        <a href="{dashboard_url()}"
           style="display:inline-block;background:#2563eb;color:#fff;text-decoration:none;
                  padding:10px 18px;border-radius:8px;font-size:14px;font-weight:600">
          Open the dashboard
        </a>
      </div>
      <div style="margin-top:18px;color:#94a3b8;font-size:12px">
        Run reference: {escape_html(run_id)}
      </div>
    </div>
  </div>
</body>
</html>"""


def ai_block(title, text):
    """
    Render one AI section (summary / impact / action) as an HTML card.
    Parameters: title (str), text (str).
    Returns: str (HTML).
    """
    return (
        "<div style='margin-top:14px'>"
        f"<div style='font-size:12px;text-transform:uppercase;letter-spacing:.4px;"
        f"color:#64748b;margin-bottom:3px'>{escape_html(title)}</div>"
        f"<div style='font-size:14px;line-height:1.5'>{escape_html(text)}</div>"
        "</div>"
    )


def send_email(recipients, subject, text_body, html_body=None):
    """
    Send the email by SMTP, or log it if SMTP is not configured.
    Parameters: recipients (list of str), subject (str), text_body (str),
        html_body (str or None — added as the rich alternative).
    Returns: None (raises on a real SMTP failure).
    """
    host = os.getenv("SMTP_HOST")
    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASSWORD")
    port = int(os.getenv("SMTP_PORT", "587"))
    sender = os.getenv("SMTP_FROM") or get_settings().get("smtp_from") or user

    # Log-only mode: no real credentials, so just record what we would send.
    if not host or not user or not password:
        log.info("[log-only] Email to %s | subject: %s", ", ".join(recipients), subject)
        log.info("[log-only] Body:\n%s", text_body)
        return

    message = EmailMessage()
    message["From"] = sender
    message["To"] = ", ".join(recipients)
    message["Subject"] = subject
    message.set_content(text_body)
    if html_body:
        message.add_alternative(html_body, subtype="html")

    with smtplib.SMTP(host, port, timeout=30) as server:
        server.starttls()
        server.login(user, password)
        server.send_message(message)

    log.info("Email sent to %s | subject: %s", ", ".join(recipients), subject)


def get_settings():
    """
    Load the single app_settings row (folder defaults, SMTP from, recipients).
    Parameters: none.
    Returns: dict (empty dict if no settings row exists).
    """
    row = db.query_one("SELECT * FROM app_settings WHERE id = 1")
    if row:
        return row
    return {}
