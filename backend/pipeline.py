"""
Pipeline orchestrator — ties the agents together for one file.

run_pipeline(file_info):
    Monitor already detected the file. We then:
    1. Intake  — match a profile, open the validation run.
    2. Test    — load the profile's rules, validate the CSV.
    3. Route   — move the file to good / quarantine.
    4. Finalize — write issues and update the run row.
"""

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from logging_setup import get_logger
from Intake_agent.initial_check import supabase, intake_file, move_file
from Test_agent.validator import validate

log = get_logger("Pipeline")


def load_rules(profile_id: str):
    """Fetch the column rules + cross-column rules for a profile."""
    columns = (
        supabase.table("profile_columns")
        .select("*").eq("profile_id", profile_id)
        .order("column_order").execute().data or []
    )
    cross = (
        supabase.table("profile_cross_column_rules")
        .select("*").eq("profile_id", profile_id).execute().data or []
    )
    return columns, cross


def write_issues(run_id: str, issues: list[dict]) -> None:
    if not issues:
        return
    rows = []
    for i in issues:
        loc = None
        if i.get("column_name") and i.get("row_number"):
            loc = f"row {i['row_number']}, column {i['column_name']}"
        rows.append({
            "run_id": run_id,
            "rule_name": i["rule_name"],
            "severity": i["severity"],
            "message": i["message"],
            "location": loc,
            "column_name": i.get("column_name"),
            "row_number": i.get("row_number"),
            "constraint_kind": i.get("constraint_kind"),
        })
    supabase.table("run_issues").insert(rows).execute()


def finalize_run(run_id, status, issues, destination):
    errors = sum(1 for i in issues if i["severity"] == "error")
    warnings = sum(1 for i in issues if i["severity"] == "warning")
    supabase.table("validation_runs").update({
        "status": status,
        "issue_count": len(issues),
        "error_count": errors,
        "warning_count": warnings,
        "destination_path": destination,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", run_id).execute()
    log.info("Run %s -> %s (%d errors, %d warnings)", run_id, status, errors, warnings)


def run_pipeline(file_info: dict) -> dict:
    file_path = file_info["file_path"]

    # 1. Intake — match a profile and open the run.
    intake = intake_file(file_info)
    run_id, profile = intake["run_id"], intake["profile"]
    if profile is None:
        return {"run_id": run_id, "status": "review"}  # already moved to review

    # 2. Test — load rules and read the file.
    columns, cross = load_rules(profile["id"])
    try:
        df = pd.read_csv(file_path, dtype=str, keep_default_na=False)
    except Exception as e:
        log.warning("Could not read %s: %s", file_path, e)
        issues = [{
            "rule_name": "File Read", "severity": "error",
            "message": f"File could not be read as CSV: {e}",
            "column_name": None, "row_number": None, "constraint_kind": "type",
        }]
        dest = move_file(file_path, profile["failure_routing"])
        write_issues(run_id, issues)
        finalize_run(run_id, "failed", issues, dest)
        return {"run_id": run_id, "status": "failed"}

    issues = validate(df, columns, cross, profile.get("allow_extra_columns", True))

    # 3. Route — any error quarantines the whole file.
    has_error = any(i["severity"] == "error" for i in issues)
    status = "failed" if has_error else "passed"
    dest_folder = profile["failure_routing"] if has_error else profile["success_routing"]
    dest = move_file(file_path, dest_folder)

    # 4. Finalize.
    write_issues(run_id, issues)
    finalize_run(run_id, status, issues, dest)
    return {"run_id": run_id, "status": status, "issues": len(issues)}
