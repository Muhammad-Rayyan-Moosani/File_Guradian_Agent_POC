"""
Pipeline orchestrator — runs one file through all the steps.

When the Monitor sees a new file it calls run_pipeline(). That function:
    1. Intake   — match a profile and open the run.
    2. Test     — load the rules and validate the CSV.
    3. Route    — move the file to the good or quarantine folder.
    4. Finalize — write the issues, the AI summary, and the final result.
"""

import os
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from logging_setup import get_logger
import db
from Intake_agent.initial_check import intake_file, create_run, move_file, with_retries
from Test_agent.validator import validate_file
from Explanation_agent.explain import explain
from Notification_agent.notify import notify_failure

log = get_logger("Pipeline")


def read_int_env(name, default):
    """
    Read a whole-number setting from the environment, or use a default.
    Parameters: name (str), default (int).
    Returns: int.
    """
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


# How many rows to read at once, and the largest file we will open (0 = no cap).
CHUNK_ROWS = read_int_env("FG_CHUNK_ROWS", 100_000)
MAX_FILE_MB = read_int_env("FG_MAX_FILE_MB", 0)


def load_rules(profile_id):
    """
    Load the column rules and cross-column rules for a profile.
    Parameters: profile_id (str).
    Returns: tuple (columns list, cross_rules list).
    """
    columns = db.query_all(
        "SELECT * FROM profile_columns WHERE profile_id = ? ORDER BY column_order",
        (profile_id,))
    cross_rules = db.query_all(
        "SELECT * FROM profile_cross_column_rules WHERE profile_id = ?",
        (profile_id,))
    return columns, cross_rules


def write_issues(run_id, issues):
    """
    Save all the issues found for a run into the run_issues table.
    Parameters: run_id (str), issues (list of issue dicts).
    Returns: None.
    """
    if not issues:
        return

    rows = []
    for issue in issues:
        # Build a friendly "where" string when we know the spot.
        location = None
        if issue.get("column_name") and issue.get("row_number"):
            location = f"row {issue['row_number']}, column {issue['column_name']}"

        rows.append({
            "run_id": run_id,
            "rule_name": issue["rule_name"],
            "severity": issue["severity"],
            "message": issue["message"],
            "location": location,
            "column_name": issue.get("column_name"),
            "row_number": issue.get("row_number"),
            "constraint_kind": issue.get("constraint_kind"),
        })

    def do_insert():
        return db.insert_many("run_issues", rows)

    with_retries(do_insert)


def write_column_stats(run_id, column_stats):
    """
    Save the per-column statistics for a run into the run_column_stats table.
    Parameters: run_id (str), column_stats (list of stat dicts, or None).
    Returns: None.
    """
    if not column_stats:
        return

    rows = []
    for stat in column_stats:
        row = dict(stat)
        row["run_id"] = run_id
        rows.append(row)

    def do_insert():
        return db.insert_many("run_column_stats", rows)

    with_retries(do_insert)


def finalize_run(run_id, status, errors, warnings, destination, summary,
                 notification, total_rows=None, column_count=None):
    """
    Fill in the final result on the validation_runs row.
    Parameters: run_id (str), status (str), errors (int), warnings (int),
        destination (str), summary (dict), notification (dict),
        total_rows (int or None), column_count (int or None).
    Returns: None.
    """
    def do_update():
        return db.update("validation_runs", run_id, {
            "status": status,
            "issue_count": errors + warnings,
            "error_count": errors,
            "warning_count": warnings,
            "total_rows": total_rows,
            "column_count": column_count,
            "destination_path": destination,
            "ai_summary": json.dumps(summary),
            "notification_status": notification["status"],
            "notified_recipients": notification["recipients"],
            "completed_at": datetime.now(timezone.utc).isoformat(),
        })

    with_retries(do_update)
    log.info("Run %s -> %s (%d errors, %d warnings)", run_id, status, errors, warnings)


def log_event(run_id, agent, action, detail=None):
    """
    Record one step of the workflow in the agent_events table (audit trail).
    Parameters: run_id (str), agent (str), action (str), detail (str or None).
    Returns: None.
    """
    try:
        db.insert("agent_events", {
            "run_id": run_id,
            "agent": agent,
            "action": action,
            "detail": detail,
        })
    except Exception:
        # The audit log must never break the run.
        log.exception("Could not write agent event (%s / %s)", agent, action)


def safe_notify(profile, file_name, status, summary, issues, run_id, errors, warnings):
    """
    Run the notification step without ever letting it break the pipeline.
    Parameters: profile (dict), file_name (str), status (str), summary (dict),
        issues (list), run_id (str), errors (int), warnings (int).
    Returns: dict {status, recipients, channel, subject, sent_at}.
    """
    try:
        return notify_failure(profile, file_name, status, summary, issues, run_id,
                              errors, warnings)
    except Exception:
        log.exception("Notification step failed for %s", file_name)
        return {"status": "failed", "recipients": [],
                "channel": None, "subject": None, "sent_at": None}


def notification_event(notification):
    """
    Turn a notification result into an audit action + detail.
    The detail records channel, recipient, subject and sent time (req 6.7).
    Parameters: notification (dict).
    Returns: tuple (action str, detail str or None).
    """
    status = notification["status"]
    if status == "not_required":
        return "No notification needed", None

    detail = (
        f"channel={notification.get('channel')}; "
        f"to={', '.join(notification['recipients'])}; "
        f"subject={notification.get('subject')}; "
        f"sent_at={notification.get('sent_at')}"
    )
    action = "Notification sent" if status == "sent" else "Notification failed"
    return action, detail


def single_error(rule_name, message, kind):
    """
    Build a one-item issue list for a whole-file failure (too big, unreadable).
    Parameters: rule_name (str), message (str), kind (str constraint_kind).
    Returns: dict in the standard issue shape.
    """
    return {
        "rule_name": rule_name, "severity": "error", "message": message,
        "column_name": None, "row_number": None, "constraint_kind": kind,
    }


def complete_run(run_id, profile, file_path, file_name, status,
                 issues, errors, warnings, total_rows,
                 column_stats=None, column_count=None):
    """
    Move the file, explain, notify, save issues and finalize one run.
    Parameters: run_id (str), profile (dict), file_path/file_name (str),
        status (str), issues (list), errors/warnings (int), total_rows (int or None),
        column_stats (list or None), column_count (int or None).
    Returns: dict summary {"run_id", "status", "issues"}.
    """
    if status == "failed":
        dest_folder = profile["failure_routing"]
    else:
        dest_folder = profile["success_routing"]
    dest = move_file(file_path, dest_folder)

    meta = {"file_name": file_name, "status": status,
            "profile_name": profile["name"], "total_rows": total_rows,
            "error_count": errors, "warning_count": warnings}
    # Only spend an AI call on files that actually failed.
    summary = explain(meta, issues)
    log_event(run_id, "Explanation", "Generated plain-English summary")

    notification = safe_notify(profile, file_name, status, summary, issues, run_id,
                               errors, warnings)
    action, detail = notification_event(notification)
    log_event(run_id, "Notification", action, detail)

    write_issues(run_id, issues)
    write_column_stats(run_id, column_stats)
    finalize_run(run_id, status, errors, warnings, dest, summary, notification,
                 total_rows, column_count)
    log_event(run_id, "Audit", "Run finalized", f"status={status}, moved to {dest}")
    return {"run_id": run_id, "status": status, "issues": len(issues)}


def run_pipeline(file_info):
    """
    Run one detected file through intake, validation, routing and finalize.
    Parameters: file_info (dict) with at least "file_path".
    Returns: dict summary {"run_id", "status", ...}.
    """
    file_path = file_info["file_path"]
    file_name = os.path.basename(file_path)

    # 1. Intake — match a profile and open the run.
    intake = intake_file(file_info)
    run_id = intake["run_id"]
    profile = intake["profile"]

    # Record name, path, type, size and received time in the audit trail (req 6.1).
    file_type = file_info.get("file_type") or os.path.splitext(file_name)[1].lower()
    detected_detail = (
        f"name={file_name}; "
        f"type={file_type}; "
        f"size={file_info.get('file_size')} bytes; "
        f"path={file_path}; "
        f"received={file_info.get('received_at')}"
    )
    log_event(run_id, "Monitor", "File detected", detected_detail)

    if profile is None:
        # No profile matched; the file was already moved to review.
        log_event(run_id, "Intake", "Classified file", "No matching profile")
        log_event(run_id, "Planning", "Routed to review",
                  "No active profile matched the file name")
        log_event(run_id, "Audit", "Run finalized", "status=review")
        return {"run_id": run_id, "status": "review"}

    log_event(run_id, "Intake", "Matched profile", profile["name"])

    return run_checks(run_id, profile, file_info, file_path, file_name)


def run_checks(run_id, profile, file_info, file_path, file_name):
    """
    Load the rules, validate the file, then route and finalize the run.
    This is the shared core used by both the folder Monitor and the direct
    upload path, so both behave identically once the profile is known.
    Parameters: run_id (str), profile (dict), file_info (dict),
        file_path (str), file_name (str).
    Returns: dict summary {"run_id", "status", "issues"}.
    """
    # 2. Test — load the rules for this profile.
    columns, cross_rules = load_rules(profile["id"])
    log_event(run_id, "Planning", "Loaded validation rules",
              f"{len(columns)} columns, {len(cross_rules)} cross-column rules")

    # Guard: refuse a single file bigger than the configured limit.
    size_bytes = file_info.get("file_size") or 0
    if MAX_FILE_MB > 0 and size_bytes > MAX_FILE_MB * 1024 * 1024:
        log.warning("File over the %d MB limit: %s", MAX_FILE_MB, file_path)
        log_event(run_id, "Test", "File too large", f"{size_bytes} bytes")
        issues = [single_error(
            "File Size",
            f"File is larger than the {MAX_FILE_MB} MB limit and was not opened.",
            "type")]
        return complete_run(run_id, profile, file_path, file_name,
                            "failed", issues, 1, 0, None)

    # 3. Validate the file — streamed in chunks so memory stays flat.
    # When the profile is set to auto-detect, pass no file_type so the validator
    # picks the format from the file's own extension (CSV/JSON/XML).
    if profile.get("auto_detect_type"):
        chosen_type = None
    else:
        chosen_type = profile.get("file_type")

    try:
        result = validate_file(file_path, columns, cross_rules,
                               profile.get("allow_extra_columns", True), CHUNK_ROWS,
                               file_type=chosen_type)
    except Exception as error:
        # The file is there but isn't readable in its expected format — quarantine it.
        log.warning("Could not read %s: %s", file_path, error)
        log_event(run_id, "Test", "Could not read file", str(error))
        issues = [single_error(
            "File Read", f"File could not be read: {error}", "type")]
        return complete_run(run_id, profile, file_path, file_name,
                            "failed", issues, 1, 0, None)

    issues = result["issues"]
    errors = result["error_count"]
    warnings = result["warning_count"]
    total_rows = result["total_rows"]
    column_stats = result.get("column_stats")
    column_count = result.get("column_count")
    log_event(run_id, "Test", "Ran validation checks",
              f"{errors} errors, {warnings} warnings across {total_rows} rows")

    # 4. Route + finalize — any error quarantines the whole file.
    if errors > 0:
        status = "failed"
    else:
        status = "passed"
    return complete_run(run_id, profile, file_path, file_name, status,
                        issues, errors, warnings, total_rows,
                        column_stats, column_count)


def run_pipeline_for_profile(file_info, profile):
    """
    Validate a file against a profile we already know, instead of matching it by
    folder + name. Used when a file is uploaded straight from the UI (e.g. the
    sample used to create a profile) rather than dropped into a watched folder.
    The outcome is identical to the normal flow: a run is recorded and the file
    is moved to the profile's good or quarantine folder.
    Parameters: file_info (dict with file_path), profile (dict, a profile row).
    Returns: dict summary {"run_id", "status", "issues"}.
    """
    file_path = file_info["file_path"]
    file_name = os.path.basename(file_path)

    run_id = create_run(file_info, profile, "processing")

    file_type = file_info.get("file_type") or os.path.splitext(file_name)[1].lower()
    detected_detail = (
        f"name={file_name}; "
        f"type={file_type}; "
        f"size={file_info.get('file_size')} bytes; "
        f"path={file_path}; "
        f"received={file_info.get('received_at')}"
    )
    log_event(run_id, "Monitor", "File uploaded", detected_detail)
    log_event(run_id, "Intake", "Matched profile", profile["name"])

    return run_checks(run_id, profile, file_info, file_path, file_name)
