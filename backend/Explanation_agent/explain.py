"""
Explanation agent — turns the validator's issues into a plain-English summary.

It never decides pass or fail; the validator already did that. This only
describes the problems that were already found, for a business reader.

By default it builds the summary from a simple template. If ANTHROPIC_API_KEY
is set, it asks Claude to write a nicer one and falls back to the template if
that call fails for any reason.
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from logging_setup import get_logger  # noqa: E402
import paths  # noqa: E402

log = get_logger("Explanation")

# override=True so the real key in .env wins even if the shell exports an
# empty ANTHROPIC_API_KEY. paths.ENV_FILE points next to the .exe when frozen.
load_dotenv(paths.ENV_FILE, override=True)


def explain(meta, issues):
    """
    Build the {summary, impact, action} object for a finished run.
    Parameters: meta (dict: file_name, status, profile_name, total_rows,
        error_count, warning_count), issues (list of issue dicts).
    Returns: dict with keys summary, impact, action.
    """
    # Only spend an AI call when the file actually failed. Passing files get
    # the instant template summary (no latency, no cost).
    if meta.get("status") == "failed" and os.getenv("ANTHROPIC_API_KEY"):
        try:
            return summarize_with_llm(meta, issues)
        except Exception as error:
            log.warning("LLM summary failed, using template: %s", error)
    return build_template_summary(meta, issues)


def counts_from(meta, issues):
    """
    Get the true error/warning counts, preferring the totals passed in meta.
    Parameters: meta (dict), issues (list of issue dicts).
    Returns: tuple (error_count int, warning_count int).
    """
    if meta.get("error_count") is not None or meta.get("warning_count") is not None:
        return meta.get("error_count", 0), meta.get("warning_count", 0)
    errors, warnings = split_by_severity(issues)
    return len(errors), len(warnings)


# --- the simple template summary (always available) ------------------------

def build_template_summary(meta, issues):
    """
    Write a summary without any AI, straight from the issue list.
    Parameters: meta (dict), issues (list of issue dicts).
    Returns: dict with keys summary, impact, action.
    """
    file_name = meta.get("file_name", "The file")
    rows = meta.get("total_rows")

    error_count, warning_count = counts_from(meta, issues)

    # Nothing wrong at all.
    if error_count == 0 and warning_count == 0:
        text = f"{file_name} passed all checks"
        if rows:
            text += f" across {rows} rows."
        else:
            text += "."
        text += " It was routed to the good folder."
        return {"summary": text, "impact": "", "action": ""}

    # Describe each group of problems in plain words.
    groups = group_issues(issues)
    phrases = []
    for kind, column, count in groups:
        phrases.append(phrase_for(kind, column, count))

    head = f"{file_name} failed validation with {error_count} error"
    if error_count != 1:
        head += "s"
    if warning_count:
        head += f" and {warning_count} warning"
        if warning_count != 1:
            head += "s"
    if rows:
        head += f" across {rows} rows."
    else:
        head += "."

    summary = head + " Main issues: " + join_words(phrases) + "."
    return {
        "summary": summary,
        "impact": describe_impact(issues),
        "action": recommend_action(issues),
    }


def describe_impact(issues):
    """
    Explain the likely business impact of the errors.
    Parameters: issues (list of issue dicts).
    Returns: str.
    """
    kinds = error_kinds(issues)
    parts = []

    if "missing_column" in kinds or "required" in kinds:
        parts.append("affected records can't be processed downstream until the "
                     "missing or blank fields are supplied")
    if "unique" in kinds:
        parts.append("duplicate keys risk double-processing (for invoices, "
                     "this can mean double-billing)")
    if kinds_overlap(kinds, ["type", "min", "max", "regex", "allowed_values", "cross"]):
        parts.append("invalid values would corrupt downstream calculations or records")

    if not parts:
        return "No blocking impact — the warnings are advisory only."
    return capitalize_first(join_words(parts) + ".")


def recommend_action(issues):
    """
    Suggest what the user should do next.
    Parameters: issues (list of issue dicts).
    Returns: str.
    """
    kinds = error_kinds(issues)
    if "missing_column" in kinds:
        return ("Ask the sender to re-export the file using the agreed template "
                "so all required columns are present, then resend.")
    if kinds:
        return ("Return the flagged rows to the sender to correct the values, "
                "then resend the file.")
    return "No action required — review the warnings if you want cleaner data."


# --- the Claude path (only used when ANTHROPIC_API_KEY is set) --------------

SYSTEM_PROMPT = (
    "You explain data-file validation failures to non-technical business "
    "users. You are given issues that a deterministic validator already "
    "found. Do not invent issues and do not re-judge the file — only explain "
    "what is listed. Be concise and practical. Respond as JSON with keys "
    "summary, impact, action."
)


def summarize_with_llm(meta, issues):
    """
    Ask Claude to write the summary from the grouped issues.
    Parameters: meta (dict), issues (list of issue dicts).
    Returns: dict with keys summary, impact, action.
    """
    import anthropic

    # Group and cap the issues so the prompt stays small.
    groups = group_issues(issues)
    lines = []
    for kind, column, count in groups[:20]:
        lines.append(f"- {phrase_for(kind, column, count)}")

    error_count, warning_count = counts_from(meta, issues)
    user_message = (
        f"File: {meta.get('file_name')}\n"
        f"Profile: {meta.get('profile_name')}\n"
        f"Result: {str(meta.get('status', '')).upper()} — "
        f"{error_count} errors, {warning_count} warnings "
        f"across {meta.get('total_rows', '?')} rows\n\n"
        f"Issues found:\n" + "\n".join(lines) + "\n\n"
        'Return JSON: {"summary": ..., "impact": ..., "action": ...}'
    )

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=500,
        system=[{
            "type": "text",
            "text": SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        }],
        messages=[{"role": "user", "content": user_message}],
    )

    data = extract_json(response.content[0].text)
    return {
        "summary": data.get("summary", ""),
        "impact": data.get("impact", ""),
        "action": data.get("action", ""),
    }


def extract_json(text):
    """
    Pull the JSON object out of the model's reply (it may add fences/prose).
    Parameters: text (str).
    Returns: dict (raises ValueError if no object is found).
    """
    import json
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"No JSON object in response: {text[:80]}")
    return json.loads(text[start:end + 1])


# --- small helper functions ------------------------------------------------

def split_by_severity(issues):
    """
    Separate issues into errors and warnings.
    Parameters: issues (list of issue dicts).
    Returns: tuple (errors list, warnings list).
    """
    errors = []
    warnings = []
    for issue in issues:
        if issue["severity"] == "error":
            errors.append(issue)
        elif issue["severity"] == "warning":
            warnings.append(issue)
    return errors, warnings


def group_issues(issues):
    """
    Count issues grouped by (constraint kind, column name).
    Parameters: issues (list of issue dicts).
    Returns: list of (kind, column, count) tuples, most common first.
    """
    counts = {}
    for issue in issues:
        kind = issue.get("constraint_kind")
        column = issue.get("column_name") or ""
        key = (kind, column)
        counts[key] = counts.get(key, 0) + 1

    groups = []
    for (kind, column), count in counts.items():
        groups.append((kind, column, count))
    groups.sort(key=count_of_group, reverse=True)
    return groups


def count_of_group(group):
    """
    Return the count from a (kind, column, count) tuple, used for sorting.
    Parameters: group (tuple).
    Returns: int.
    """
    return group[2]


def error_kinds(issues):
    """
    Collect the set of constraint kinds that produced an error.
    Parameters: issues (list of issue dicts).
    Returns: set of strings.
    """
    kinds = set()
    for issue in issues:
        if issue["severity"] == "error":
            kinds.add(issue["constraint_kind"])
    return kinds


def kinds_overlap(kinds, wanted):
    """
    Check if any wanted kind is present in the kinds set.
    Parameters: kinds (set), wanted (list of strings).
    Returns: bool.
    """
    for kind in wanted:
        if kind in kinds:
            return True
    return False


def phrase_for(kind, column, count):
    """
    Describe one group of failures in plain words.
    Parameters: kind (str), column (str), count (int).
    Returns: str.
    """
    plural = "" if count == 1 else "s"
    if kind == "missing_column":
        return f"the required column '{column}' is missing"
    if kind == "required":
        return f"{column} is blank on {count} row{plural}"
    if kind == "unique":
        return f"duplicate {column} value{plural}"
    if kind == "type":
        return f"{column} has an invalid value on {count} row{plural}"
    if kind == "min":
        return f"{column} is below the allowed minimum on {count} row{plural}"
    if kind == "max":
        return f"{column} is above the allowed maximum on {count} row{plural}"
    if kind == "regex":
        return f"{column} does not match the required format on {count} row{plural}"
    if kind == "allowed_values":
        return f"{column} has values outside the allowed list on {count} row{plural}"
    if kind == "cross":
        return f"a column comparison failed on {count} row{plural}"
    return f"{column} failed validation on {count} row{plural}"


def join_words(items):
    """
    Join a list into readable text: "a, b and c".
    Parameters: items (list of strings).
    Returns: str.
    """
    clean = []
    for item in items:
        if item:
            clean.append(item)

    if not clean:
        return ""
    if len(clean) == 1:
        return clean[0]
    return ", ".join(clean[:-1]) + " and " + clean[-1]


def capitalize_first(text):
    """
    Capitalize only the first letter of a string.
    Parameters: text (str).
    Returns: str.
    """
    if not text:
        return text
    return text[0].upper() + text[1:]
