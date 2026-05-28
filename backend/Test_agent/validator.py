"""
Validation engine — pure logic, no database, no file moves.

validate(df, columns, cross_rules, allow_extra) -> list of issues

Each `column` is a profile_columns row (snake_case from Supabase):
    name, data_type, required, unique_flag, min_value, max_value,
    regex_pattern, allowed_values, severity

Each `cross_rule` is a profile_cross_column_rules row:
    name, left_column, op, right_column, severity

An issue is a dict:
    rule_name, severity, message, column_name, row_number, constraint_kind
"""

import re
import pandas as pd

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
INT_RE = re.compile(r"^-?\d+$")
BOOL_VALUES = {"true", "false", "0", "1", "yes", "no"}

# Don't write more than this many issues for a single constraint.
MAX_PER_CONSTRAINT = 50


def validate(df, columns, cross_rules, allow_extra=True):
    issues = []
    headers = list(df.columns)
    declared = {c["name"] for c in columns}

    # --- header checks -----------------------------------------------------
    for col in columns:
        if col["required"] and col["name"] not in headers:
            issues.append(_issue(
                "Missing Column", col["severity"],
                f"Required column '{col['name']}' is missing.",
                column_name=col["name"], constraint_kind="missing_column",
            ))

    if not allow_extra:
        for h in headers:
            if h not in declared:
                issues.append(_issue(
                    "Unexpected Column", "error",
                    f"Column '{h}' is not part of this profile.",
                    column_name=h, constraint_kind="missing_column",
                ))

    # --- per-column cell checks -------------------------------------------
    for col in columns:
        name = col["name"]
        if name not in headers:
            continue  # already reported as missing
        issues.extend(_check_column(df[name], col))

    # --- cross-column checks ----------------------------------------------
    for rule in cross_rules:
        issues.extend(_check_cross(df, rule))

    return issues


def _check_column(series, col):
    """Run every constraint configured on one column."""
    out = []
    name = col["name"]
    sev = col["severity"]
    dtype = col.get("data_type")

    # Which cells are blank
    blank = series.fillna("").astype(str).str.strip() == ""
    nonblank = ~blank
    filled = series[nonblank]

    # required
    if col["required"]:
        out += _from_mask(blank, series, name, sev, "required",
                          lambda v, r: f"{name} cannot be blank (row {r}).")

    # type (only on non-blank cells)
    if dtype and dtype != "string":
        bad = _bad_type_mask(filled, dtype)
        out += _from_mask(bad, filled, name, sev, "type",
                          lambda v, r: f"{name} must be a valid {dtype}. Found '{v}'.")

    # min / max (numeric or date)
    if col.get("min_value") not in (None, ""):
        out += _range_check(filled, col, "min", name, sev)
    if col.get("max_value") not in (None, ""):
        out += _range_check(filled, col, "max", name, sev)

    # regex
    if col.get("regex_pattern"):
        pat = col["regex_pattern"]
        bad = ~filled.str.match(pat)
        out += _from_mask(bad, filled, name, sev, "regex",
                          lambda v, r: f"{name} doesn't match pattern {pat}. Found '{v}'.")

    # allowed_values (enum)
    allowed = col.get("allowed_values")
    if allowed:
        bad = ~filled.isin(allowed)
        out += _from_mask(bad, filled, name, sev, "allowed_values",
                          lambda v, r: f"{name} must be one of {allowed}. Found '{v}'.")

    # unique (across all rows, including blanks)
    if col["unique_flag"]:
        dupes = series[nonblank].duplicated(keep=False)
        dupes = dupes.reindex(series.index, fill_value=False)
        out += _from_mask(dupes, series, name, sev, "unique",
                          lambda v, r: f"Duplicate {name} '{v}' (row {r}).")

    return out


def _check_cross(df, rule):
    """Compare two columns row-by-row."""
    left, right, op = rule["left_column"], rule["right_column"], rule["op"]
    if left not in df.columns or right not in df.columns:
        return []  # missing columns already reported elsewhere

    l = pd.to_numeric(df[left], errors="coerce")
    r = pd.to_numeric(df[right], errors="coerce")
    if l.isna().all() or r.isna().all():  # not numbers — try dates
        l = pd.to_datetime(df[left], errors="coerce")
        r = pd.to_datetime(df[right], errors="coerce")

    ok = _apply_op(l, r, op)
    bad = ~ok & l.notna() & r.notna()
    sym = {"gt": ">", "gte": "≥", "lt": "<", "lte": "≤", "eq": "=", "neq": "≠"}[op]

    out = []
    for i, is_bad in enumerate(bad):
        if is_bad:
            out.append(_issue(
                rule["name"], rule["severity"],
                f"{left} {sym} {right} failed at row {i + 2} "
                f"({df[left].iloc[i]} vs {df[right].iloc[i]}).",
                column_name=left, row_number=i + 2, constraint_kind="cross",
            ))
            if len(out) >= MAX_PER_CONSTRAINT:
                break
    return out


# --- helpers ---------------------------------------------------------------

def _bad_type_mask(filled, dtype):
    if dtype == "integer":
        return ~filled.str.match(INT_RE)
    if dtype == "decimal":
        return pd.to_numeric(filled, errors="coerce").isna()
    if dtype in ("date", "datetime"):
        return pd.to_datetime(filled, errors="coerce").isna()
    if dtype == "email":
        return ~filled.str.match(EMAIL_RE)
    if dtype == "boolean":
        return ~filled.str.lower().isin(BOOL_VALUES)
    return pd.Series(False, index=filled.index)


def _range_check(filled, col, kind, name, sev):
    bound = col[f"{kind}_value"]
    dtype = col.get("data_type")

    if dtype in ("date", "datetime"):
        vals = pd.to_datetime(filled, errors="coerce")
        limit = pd.to_datetime(bound, errors="coerce")
    else:
        vals = pd.to_numeric(filled, errors="coerce")
        limit = pd.to_numeric(bound, errors="coerce")

    if kind == "min":
        bad = vals < limit
        word = "≥"
    else:
        bad = vals > limit
        word = "≤"
    bad = bad.fillna(False)  # un-parseable values are a type problem, not range
    return _from_mask(bad, filled, name, sev, kind,
                      lambda v, r: f"{name} must be {word} {bound}. Found '{v}' (row {r}).")


def _apply_op(l, r, op):
    return {
        "gt": l > r, "gte": l >= r, "lt": l < r,
        "lte": l <= r, "eq": l == r, "neq": l != r,
    }[op]


def _from_mask(mask, series, name, sev, kind, message_fn):
    """Turn a boolean Series into issues (capped). `series` supplies the
    actual cell value for the message, aligned to the mask's index."""
    out = []
    for idx, is_bad in mask.items():
        if is_bad:
            row_num = idx + 2  # +1 for 0-index, +1 for the header line
            val = series.loc[idx]
            out.append(_issue(
                f"{name} {kind}", sev, message_fn(val, row_num),
                column_name=name, row_number=row_num, constraint_kind=kind,
            ))
            if len(out) >= MAX_PER_CONSTRAINT:
                break
    return out


def _issue(rule_name, severity, message, column_name=None, row_number=None,
           constraint_kind=None):
    return {
        "rule_name": rule_name,
        "severity": severity,
        "message": message,
        "column_name": column_name,
        "row_number": row_number,
        "constraint_kind": constraint_kind,
    }
