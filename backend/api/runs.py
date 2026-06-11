"""
Runs API — the read-only endpoints the dashboard reads from.

GET /api/runs        → the most recent validation runs (list)
GET /api/runs/<id>   → one run together with its issues and agent events
"""

import json
import os
import sys
from pathlib import Path

from flask import Blueprint, jsonify

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from logging_setup import get_logger  # noqa: E402
import db  # noqa: E402

log = get_logger("Runs API")

runs_bp = Blueprint("runs", __name__)


def to_run(row, issues=None, events=None, column_stats=None):
    """
    Convert a validation_runs row into the shape the frontend expects.
    Parameters: row (dict), issues (list or None), events (list or None),
        column_stats (list or None).
    Returns: dict matching the frontend ValidationRun type.
    """
    if issues is None:
        issues = []
    if events is None:
        events = []
    if column_stats is None:
        column_stats = []

    return {
        "id": row["id"],
        "fileName": row["file_name"],
        "fileSizeKb": row.get("file_size_kb") or 0,
        "receivedAt": row.get("received_at"),
        "completedAt": row.get("completed_at"),
        "status": row["status"],
        "profileId": row.get("profile_id") or "—",
        "profileName": row.get("profile_name") or "—",
        "issueCount": row.get("issue_count") or 0,
        "errorCount": row.get("error_count") or 0,
        "warningCount": row.get("warning_count") or 0,
        "totalRows": row.get("total_rows"),
        "columnCount": row.get("column_count"),
        "notificationStatus": row.get("notification_status") or "not_required",
        "notifiedRecipients": row.get("notified_recipients") or [],
        "destinationPath": row.get("destination_path"),
        "aiSummary": parse_summary(row.get("ai_summary")),
        "issues": issues,
        "events": events,
        "columnStats": column_stats,
    }


def to_stat(row):
    """
    Convert a run_column_stats row into the frontend's column-stat shape.
    Parameters: row (dict).
    Returns: dict.
    """
    return {
        "columnName": row["column_name"],
        "totalCount": row.get("total_count") or 0,
        "blankCount": row.get("blank_count") or 0,
        "distinctCount": row.get("distinct_count") or 0,
        "distinctTruncated": bool(row.get("distinct_truncated")),
        "numericMin": row.get("numeric_min"),
        "numericMax": row.get("numeric_max"),
        "numericMean": row.get("numeric_mean"),
        "textMinLength": row.get("text_min_length"),
        "textMaxLength": row.get("text_max_length"),
        "topValues": row.get("top_values") or [],
    }


def parse_summary(raw):
    """
    Turn the stored ai_summary text into a {summary, impact, action} dict.
    Parameters: raw (str or None) — JSON text, plain text, or empty.
    Returns: dict with keys summary, impact, action.
    """
    empty = {"summary": "", "impact": "", "action": ""}
    if not raw:
        return empty

    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        # Older rows may be plain text — show it as the summary.
        return {"summary": str(raw), "impact": "", "action": ""}

    if isinstance(data, dict):
        return {
            "summary": data.get("summary", ""),
            "impact": data.get("impact", ""),
            "action": data.get("action", ""),
        }
    return empty


# Kept under the old name too, in case anything imports it.
_parse_summary = parse_summary


def to_issue(row):
    """
    Convert a run_issues row into the frontend's issue shape.
    Parameters: row (dict).
    Returns: dict.
    """
    return {
        "id": row["id"],
        "rule": row["rule_name"],
        "severity": row["severity"],
        "message": row["message"],
        "location": row.get("location"),
        "columnName": row.get("column_name"),
        "rowNumber": row.get("row_number"),
        "constraintKind": row.get("constraint_kind"),
    }


def to_event(row):
    """
    Convert an agent_events row into the frontend's event shape.
    Parameters: row (dict).
    Returns: dict.
    """
    return {
        "agent": row["agent"],
        "action": row["action"],
        "detail": row.get("detail"),
        "timestamp": row.get("occurred_at"),
    }


@runs_bp.get("/api/runs")
def list_runs():
    """
    Return the 50 most recent runs (without their issues/events).
    Parameters: none.
    Returns: JSON list of run dicts.
    """
    log.info("GET /api/runs")
    rows = db.query_all(
        "SELECT * FROM validation_runs ORDER BY received_at DESC LIMIT 50")

    runs = []
    for row in rows:
        runs.append(to_run(row))
    return jsonify(runs)


@runs_bp.delete("/api/runs/<run_id>")
def delete_run(run_id):
    """
    Delete a run everywhere: the physical file plus the database record.
    Parameters: run_id (str) from the URL.
    Returns: JSON {id, ok, file_deleted}, or a 404 error.
    """
    log.info("DELETE /api/runs/%s", run_id)
    row = db.query_one(
        "SELECT destination_path FROM validation_runs WHERE id = ?", (run_id,))
    if not row:
        return jsonify({"error": "Run not found"}), 404

    # Delete the actual file from wherever it was routed.
    file_deleted = False
    dest = row.get("destination_path")
    if dest and os.path.isfile(dest):
        try:
            os.remove(dest)
            file_deleted = True
            log.info("Deleted file %s", dest)
        except OSError:
            log.exception("Could not delete file %s", dest)

    # Delete the run row; its issues and events are removed by cascade.
    db.delete_where("validation_runs", "id", run_id)
    return jsonify({"id": run_id, "ok": True, "file_deleted": file_deleted})


@runs_bp.get("/api/runs/<run_id>")
def get_run(run_id):
    """
    Return one run together with its issues and agent events.
    Parameters: run_id (str) from the URL.
    Returns: JSON run dict, or a 404 error.
    """
    log.info("GET /api/runs/%s", run_id)
    run = db.query_one("SELECT * FROM validation_runs WHERE id = ?", (run_id,))
    if not run:
        return jsonify({"error": "Run not found"}), 404

    issue_rows = db.query_all(
        "SELECT * FROM run_issues WHERE run_id = ?", (run_id,))
    event_rows = db.query_all(
        "SELECT * FROM agent_events WHERE run_id = ? ORDER BY occurred_at",
        (run_id,))
    stat_rows = db.query_all(
        "SELECT * FROM run_column_stats WHERE run_id = ? ORDER BY rowid", (run_id,))

    issues = []
    for row in issue_rows:
        issues.append(to_issue(row))

    events = []
    for row in event_rows:
        events.append(to_event(row))

    column_stats = []
    for row in stat_rows:
        column_stats.append(to_stat(row))

    return jsonify(to_run(run, issues, events, column_stats))
