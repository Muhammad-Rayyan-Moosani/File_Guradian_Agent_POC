"""
Sample-file inference — propose a profile's columns from a CSV the user uploads.

Two levels:
  * Basic (always): read the header row and a sample of data rows, then work out
    each column's data type and whether it looks required and/or unique.
  * AI enrichment (optional): if asked, and an Anthropic key is configured, ask
    Claude to suggest extra constraints (a regex format, a short allowed-values
    list). If AI is unavailable or errors, the basic result is returned as-is.

Nothing here writes to the database; it only proposes columns for the editor.
"""

import os
import re
import sys
import json
import uuid
from datetime import datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from logging_setup import get_logger  # noqa: E402

log = get_logger("Inference")

# How many data rows to look at when guessing types (enough to be confident,
# small enough to stay fast on a big file).
SAMPLE_ROWS = 200

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
INTEGER_PATTERN = re.compile(r"^-?\d+$")
DECIMAL_PATTERN = re.compile(r"^-?\d+(\.\d+)?$")
DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%d/%m/%Y", "%d-%m-%Y")
BOOLEAN_VALUES = {"true", "false", "yes", "no"}

AI_SYSTEM_PROMPT = (
    "You help define data-validation rules for the columns of a CSV file. "
    "Only suggest a regex when the values clearly follow a fixed text format "
    "(for example an invoice code like INV-1234). Only suggest allowedValues "
    "when the column is plainly a small fixed set of options (for example a "
    "status). Be conservative — when unsure, leave the column out. Reply with "
    "JSON only, no prose."
)


def new_column_id():
    """
    Make a short unique id for a proposed column (used by the editor's UI).
    Parameters: none.
    Returns: str.
    """
    return "col_" + uuid.uuid4().hex[:10]


def read_sample(file_obj):
    """
    Read the header row and up to SAMPLE_ROWS data rows from a CSV as text.
    Reading everything as text lets us judge the column types ourselves.
    Parameters: file_obj (a path or a file-like object).
    Returns: a pandas DataFrame of strings.
    """
    return pd.read_csv(file_obj, dtype=str, nrows=SAMPLE_ROWS,
                       keep_default_na=True, skip_blank_lines=True)


def non_blank_values(series):
    """
    Get a column's non-empty values as a list of trimmed strings.
    Parameters: series (a pandas Series).
    Returns: list of str.
    """
    values = []
    for value in series.dropna().tolist():
        text = str(value).strip()
        if text != "":
            values.append(text)
    return values


def all_match(values, pattern):
    """
    Tell whether every value matches a compiled regular expression.
    Parameters: values (list of str), pattern (compiled regex).
    Returns: bool (False for an empty list).
    """
    if not values:
        return False
    for value in values:
        if not pattern.match(value):
            return False
    return True


def all_boolean(values):
    """
    Tell whether every value is a yes/no/true/false style boolean.
    Parameters: values (list of str).
    Returns: bool (False for an empty list).
    """
    if not values:
        return False
    for value in values:
        if value.lower() not in BOOLEAN_VALUES:
            return False
    return True


def all_dates(values):
    """
    Tell whether every value parses as a date in one consistent format.
    Parameters: values (list of str).
    Returns: bool (False for an empty list).
    """
    if not values:
        return False
    for date_format in DATE_FORMATS:
        every_value_fits = True
        for value in values:
            try:
                datetime.strptime(value, date_format)
            except ValueError:
                every_value_fits = False
                break
        if every_value_fits:
            return True
    return False


def detect_type(values):
    """
    Guess a column's data type from its non-blank sample values.
    Parameters: values (list of str).
    Returns: one of string/integer/decimal/date/email/boolean.
    """
    if not values:
        return "string"
    # Order matters: integers also match the decimal pattern, so check first.
    if all_match(values, EMAIL_PATTERN):
        return "email"
    if all_match(values, INTEGER_PATTERN):
        return "integer"
    if all_match(values, DECIMAL_PATTERN):
        return "decimal"
    if all_boolean(values):
        return "boolean"
    if all_dates(values):
        return "date"
    return "string"


def infer_columns(file_obj):
    """
    Build a list of proposed columns from a sample CSV (basic inference).
    Parameters: file_obj (a path or a file-like object).
    Returns: dict {columns (list), row_count (int), samples (dict name->values)}.
    """
    frame = read_sample(file_obj)
    total_rows = len(frame)

    columns = []
    samples = {}
    order = 0
    for header in frame.columns:
        series = frame[header]
        values = non_blank_values(series)
        data_type = detect_type(values)

        # Required: no blank cells were seen (and there were rows to judge).
        required = total_rows > 0 and len(values) == total_rows
        # Unique: every non-blank value differs (and there is more than one).
        unique = len(values) > 1 and len(set(values)) == len(values)

        column_name = str(header).strip()
        columns.append({
            "id": new_column_id(),
            "name": column_name,
            "order": order,
            "constraints": {
                "required": required,
                "unique": unique,
                "type": data_type,
                "severity": "error",
            },
        })
        samples[column_name] = values[:5]
        order += 1

    return {"columns": columns, "row_count": total_rows, "samples": samples}


def apply_suggestion(column, suggestion):
    """
    Merge one column's AI suggestion (regex, allowed values) into its constraints.
    Parameters: column (dict), suggestion (dict from the model).
    Returns: bool — True if anything was actually added.
    """
    constraints = column["constraints"]
    changed = False

    regex = suggestion.get("regex")
    if isinstance(regex, str) and regex.strip():
        constraints["regex"] = regex.strip()
        changed = True

    allowed = suggestion.get("allowedValues")
    if isinstance(allowed, list) and allowed:
        cleaned = []
        for item in allowed:
            cleaned.append(str(item))
        constraints["allowedValues"] = cleaned
        changed = True

    return changed


def ask_claude(columns, samples, api_key):
    """
    Ask Claude to propose a regex and/or allowed-values for each column.
    Parameters: columns (list), samples (dict name->example values), api_key (str).
    Returns: dict mapping a column name to {regex?, allowedValues?}.
    """
    import anthropic

    lines = []
    for column in columns:
        name = column["name"]
        data_type = column["constraints"].get("type")
        examples = ", ".join(samples.get(name, []))
        lines.append(f"- {name} (type {data_type}); examples: {examples}")

    user_message = (
        "Here are the columns of a CSV file, with a few example values each.\n\n"
        + "\n".join(lines) +
        '\n\nReturn JSON shaped like '
        '{"ColumnName": {"regex": "...", "allowedValues": ["A", "B"]}}. '
        "Include only the columns you are confident about; omit the rest."
    )

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=700,
        system=[{
            "type": "text",
            "text": AI_SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        }],
        messages=[{"role": "user", "content": user_message}],
    )
    return extract_json_object(response.content[0].text)


def extract_json_object(text):
    """
    Pull the JSON object out of the model's reply (it may wrap it in prose).
    Parameters: text (str).
    Returns: dict (raises ValueError if no object is found).
    """
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("No JSON object found in the AI response")
    return json.loads(text[start:end + 1])


def enhance_with_ai(columns, samples):
    """
    Add AI-suggested constraints (regex, allowed values) to the columns.
    Falls back to the columns unchanged if no key is set or the call fails.
    Parameters: columns (list of column dicts), samples (dict name->values).
    Returns: tuple (columns list, enhanced_ids list).
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        log.info("No ANTHROPIC_API_KEY set — skipping AI enrichment")
        return columns, []

    try:
        suggestions = ask_claude(columns, samples, api_key)
    except Exception:
        log.exception("AI enrichment failed — using basic inference")
        return columns, []

    enhanced_ids = []
    for column in columns:
        suggestion = suggestions.get(column["name"])
        if not isinstance(suggestion, dict):
            continue
        if apply_suggestion(column, suggestion):
            enhanced_ids.append(column["id"])

    return columns, enhanced_ids
