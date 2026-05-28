"""
Runs API — read-only endpoints the dashboard reads from.

GET /api/runs        → recent validation runs (list)
GET /api/runs/<id>   → one run with its issues + agent events
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from flask import Blueprint, jsonify
from supabase import Client, create_client

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from logging_setup import get_logger  # noqa: E402

log = get_logger("Runs API")

load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")
supabase: Client = create_client(
    os.getenv("SUPABASE_URL"), os.getenv("SERVICE_ROLE_KEY")
)

runs_bp = Blueprint("runs", __name__)


def to_run(row: dict, issues=None, events=None) -> dict:
    """Shape a validation_runs row into the frontend's ValidationRun type."""
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
        "notificationStatus": row.get("notification_status") or "not_required",
        "notifiedRecipients": row.get("notified_recipients") or [],
        "destinationPath": row.get("destination_path"),
        "aiSummary": row.get("ai_summary") or "",
        "issues": issues if issues is not None else [],
        "events": events if events is not None else [],
    }


def to_issue(row: dict) -> dict:
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


def to_event(row: dict) -> dict:
    return {
        "agent": row["agent"],
        "action": row["action"],
        "detail": row.get("detail"),
        "timestamp": row.get("occurred_at"),
    }


@runs_bp.get("/api/runs")
def list_runs():
    log.info("GET /api/runs")
    rows = (
        supabase.table("validation_runs")
        .select("*").order("received_at", desc=True).limit(50).execute().data or []
    )
    return jsonify([to_run(r) for r in rows])


@runs_bp.get("/api/runs/<run_id>")
def get_run(run_id):
    log.info("GET /api/runs/%s", run_id)
    rows = (
        supabase.table("validation_runs")
        .select("*").eq("id", run_id).limit(1).execute().data
    )
    if not rows:
        return jsonify({"error": "Run not found"}), 404

    issues = (
        supabase.table("run_issues").select("*").eq("run_id", run_id).execute().data or []
    )
    events = (
        supabase.table("agent_events")
        .select("*").eq("run_id", run_id).order("occurred_at").execute().data or []
    )
    return jsonify(to_run(rows[0], [to_issue(i) for i in issues], [to_event(e) for e in events]))
