"""
Quick AI-usage diagnosis — shows what the app's AI has actually been doing.

Run it from the project root:
    Windows:    backend\\venv\\Scripts\\python backend\\diagnose_ai.py
    Mac/Linux:  backend/venv/bin/python backend/diagnose_ai.py
(If you don't have the venv, plain `python backend\\diagnose_ai.py` also works.)

It prints: the current AI provider, how many files/runs the app processed (and
how many FAILED — each failed file is one AI summary call when AI is on), a loop
check, and the most recent log lines. Copy the whole output back to share it.

Note: the log file is wiped each time the app starts, so run this WHILE the app
is still running, or right after a busy period — before you restart it. The
run history in the database persists across restarts, so those counts are always
accurate.
"""

import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import db  # noqa: E402


def line():
    print("-" * 64)


def show_provider():
    """Print the AI provider chosen in the database (the key thing to check)."""
    line()
    print("AI PROVIDER (from the database — persists across restarts)")
    line()
    row = db.query_one(
        "SELECT ai_provider, ai_model, ai_cli_path FROM app_settings WHERE id = 1") or {}
    provider = (row.get("ai_provider") or "off")
    print("  provider     :", provider)
    print("  model        :", row.get("ai_model"))
    print("  cli_path     :", row.get("ai_cli_path"))
    print("  rate cap     :", os.getenv("FG_AI_MAX_CALLS_PER_MIN") or "20/min (default)")
    if provider.lower() == "claudecli":
        print()
        print("  >>> 'claudecli' spends your SIGNED-IN Claude subscription (the 5-hour")
        print("  >>> limit). For automated per-file work use 'anthropic' (API key) or a")
        print("  >>> local model instead. Change it on the Settings page.")


def show_runs():
    """Print run counts by status — failed count ~= number of AI summary calls."""
    line()
    print("RUN HISTORY (from the database)")
    line()
    rows = db.query_all("SELECT status, COUNT(*) AS n FROM validation_runs GROUP BY status")
    total = 0
    failed = 0
    for r in rows:
        total += r["n"]
        if r["status"] in ("failed", "quarantined"):
            failed += r["n"]
        print(f"  {r['status']:12}: {r['n']}")
    print(f"  {'TOTAL':12}: {total}")
    print()
    print(f"  Failed/quarantined runs = {failed}")
    print("  (When AI is ON, the app makes ~one AI summary call per FAILED run,")
    print("   plus one per 'Enhance with AI' upload and one per Test button click.)")

    span = db.query_one(
        "SELECT MIN(received_at) AS first, MAX(received_at) AS last FROM validation_runs")
    if span and span.get("first"):
        print(f"  First run: {span['first']}")
        print(f"  Last run : {span['last']}")

    print()
    print("  Last 12 runs:")
    recent = db.query_all(
        "SELECT file_name, status, received_at FROM validation_runs "
        "ORDER BY received_at DESC LIMIT 12")
    for r in recent:
        print(f"     {r['received_at']}  {r['status']:11}  {r['file_name']}")


def show_log():
    """Print log activity: loop check + recent lines (this run only)."""
    line()
    print("LOG ACTIVITY (current run only — the log wipes on each restart)")
    line()
    log_path = os.path.join(HERE, "logs", "file_guardian.log")
    if not os.path.exists(log_path):
        print("  no log file at", log_path)
        return

    with open(log_path, "r", encoding="utf-8", errors="replace") as handle:
        lines = handle.readlines()

    def count(text):
        total = 0
        for ln in lines:
            if text in ln:
                total += 1
        return total

    print("  total log lines        :", len(lines))
    print("  files detected         :", count("New file:"))
    print("  AI call failures       :", count("AI call failed"))
    print("  rate-cap fallbacks     :", count("AI rate cap reached"))

    files = []
    for ln in lines:
        if "New file:" in ln:
            files.append(ln.split("New file:", 1)[1].strip())
    if files:
        print()
        print("  files detected (a count > 1 means it was reprocessed = a loop):")
        for path, n in Counter(files).most_common(8):
            flag = "   <-- REPROCESSED!" if n > 1 else ""
            print(f"     {n:4}  {path}{flag}")

    print()
    print("  --- last 25 log lines ---")
    for ln in lines[-25:]:
        print("   ", ln.rstrip())


def main():
    show_provider()
    print()
    show_runs()
    print()
    show_log()


if __name__ == "__main__":
    main()
