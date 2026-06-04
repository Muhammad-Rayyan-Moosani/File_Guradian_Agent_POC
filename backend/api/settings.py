"""
Settings API — read and update the single global settings row.

GET /api/settings   → the current global settings
PUT /api/settings   → save changes to them

These are the defaults new profiles start from (destination folders, SMTP
sender, default recipients, etc.). The table only ever has one row (id = 1).
"""

import sys
from pathlib import Path

from flask import Blueprint, jsonify, request

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from logging_setup import get_logger  # noqa: E402
import db  # noqa: E402

log = get_logger("Settings API")

settings_bp = Blueprint("settings", __name__)


def to_frontend(row):
    """
    Convert an app_settings row into the frontend's AppSettings shape.
    Parameters: row (dict).
    Returns: dict (camelCase).
    """
    return {
        "processedFolder": row.get("processed_folder", ""),
        "quarantineFolder": row.get("quarantine_folder", ""),
        "reviewFolder": row.get("review_folder", ""),
        "pollIntervalSeconds": row.get("poll_interval_seconds", 5),
        "notificationChannel": row.get("notification_channel", "email"),
        "smtpHost": row.get("smtp_host", ""),
        "smtpPort": row.get("smtp_port", 587),
        "smtpFrom": row.get("smtp_from", ""),
        "teamsWebhookUrl": row.get("teams_webhook_url", ""),
        "defaultRecipients": row.get("default_recipients") or [],
    }


def to_database(body):
    """
    Convert the frontend AppSettings shape into app_settings columns.
    Parameters: body (dict, camelCase).
    Returns: dict (snake_case) ready to write.
    """
    return {
        "id": 1,
        "processed_folder": body.get("processedFolder", ""),
        "quarantine_folder": body.get("quarantineFolder", ""),
        "review_folder": body.get("reviewFolder", ""),
        "poll_interval_seconds": body.get("pollIntervalSeconds", 5),
        "notification_channel": body.get("notificationChannel", "email"),
        "smtp_host": body.get("smtpHost"),
        "smtp_port": body.get("smtpPort", 587),
        "smtp_from": body.get("smtpFrom"),
        "teams_webhook_url": body.get("teamsWebhookUrl"),
        "default_recipients": body.get("defaultRecipients") or [],
    }


@settings_bp.get("/api/settings")
def get_settings():
    """
    Return the current global settings.
    Parameters: none.
    Returns: JSON AppSettings object.
    """
    log.info("GET /api/settings")
    row = db.query_one("SELECT * FROM app_settings WHERE id = 1")
    if row:
        return jsonify(to_frontend(row))
    # No row yet — hand back sensible empty defaults.
    return jsonify(to_frontend({}))


@settings_bp.put("/api/settings")
def update_settings():
    """
    Save changes to the global settings (creates the row if missing).
    Parameters: none (reads JSON body).
    Returns: JSON of the saved AppSettings, or an error.
    """
    log.info("PUT /api/settings")
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "Request body must be JSON"}), 400

    row = to_database(body)
    saved = db.replace_settings(row)
    return jsonify(to_frontend(saved))
