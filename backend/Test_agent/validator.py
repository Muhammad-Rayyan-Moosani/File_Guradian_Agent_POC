"""
Validation engine — streams a CSV and checks it against a profile's rules.

Two design choices make this safe for very large files:

  * It reads the file in chunks (a fixed number of rows at a time), so memory
    stays roughly flat whether the file is 1 MB or 100 GB.
  * Every check is vectorised with pandas — it works on a whole column at once
    instead of looping in Python over each cell — so a file with millions of
    rows is checked in seconds, not minutes.

It returns the *true* number of errors and warnings (so the dashboard shows the
real size of the problem) but keeps only a small sample of example rows per
check (so one badly broken file can never write millions of rows to the
database).
"""

import csv
import json
import warnings
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd

# Simple patterns used to recognise value types.
EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
INTEGER_PATTERN = r"^-?\d+$"
BOOLEAN_WORDS = ["true", "false", "0", "1", "yes", "no"]

# Comparison symbols for cross-column rules (used in the messages).
SYMBOLS = {"gt": ">", "gte": ">=", "lt": "<", "lte": "<=", "eq": "=", "neq": "!="}

# Keep at most this many example rows per check in the saved issue list.
MAX_ISSUES_PER_CHECK = 50

# Stop remembering distinct values for a "unique" column after this many, so a
# gigantic file can never run the process out of memory on the unique check.
UNIQUE_TRACK_LIMIT = 5_000_000

# Default number of rows to read at once. Can be overridden by the caller.
DEFAULT_CHUNK_ROWS = 100_000

# Stop remembering new distinct values for the statistics once a column has this
# many, so a huge, high-cardinality column can't run the process out of memory.
STATS_DISTINCT_CAP = 50_000


class Findings:
    """Collects a capped sample of issues plus the true error/warning totals."""

    def __init__(self):
        """Start with no issues and zero totals."""
        self.issues = []
        self.sample_counts = {}      # key -> how many example rows we kept
        self.error_total = 0
        self.warning_total = 0
        self.notes = []              # one-off notices (e.g. unique check truncated)

    def add_total(self, severity, n):
        """Add n to the running error or warning total."""
        if severity == "error":
            self.error_total += n
        elif severity == "warning":
            self.warning_total += n

    def room_for(self, key):
        """How many more example rows we may still keep for this check."""
        return MAX_ISSUES_PER_CHECK - self.sample_counts.get(key, 0)

    def add_sample(self, key, issue):
        """Keep one more example row for this check."""
        self.sample_counts[key] = self.sample_counts.get(key, 0) + 1
        self.issues.append(issue)


def top_count(pair):
    """
    Return the count from a (value, count) pair — used to sort most-common values.
    Parameters: pair (tuple).
    Returns: int.
    """
    return pair[1]


class StatsCollector:
    """
    Builds a statistical profile of every column as the file streams past.

    For each column it keeps running tallies (how many values, how many blank,
    distinct values, number min/max/sum, text lengths, value counts). All of it
    updates chunk by chunk, and the distinct/value-count tracking is capped so a
    huge file can never use unbounded memory. This data is stored per run and is
    the groundwork for future machine-learning-based validation.
    """

    def __init__(self):
        """Start with no columns tracked yet."""
        self.columns = {}

    def column(self, name):
        """
        Get (creating if needed) the running tally dict for one column.
        Parameters: name (str).
        Returns: dict.
        """
        if name not in self.columns:
            self.columns[name] = {
                "total_count": 0, "blank_count": 0,
                "counts": {}, "distinct_truncated": False,
                "num_min": None, "num_max": None, "num_sum": 0.0, "num_count": 0,
                "len_min": None, "len_max": None,
            }
        return self.columns[name]

    def add_chunk(self, frame):
        """
        Fold one chunk's values into the running tallies for every column.
        Parameters: frame (a DataFrame chunk).
        Returns: None.
        """
        for name in frame.columns:
            tally = self.column(str(name))
            stripped = frame[name].astype(str).str.strip()
            blank = stripped == ""
            nonblank = stripped[~blank]

            tally["blank_count"] += int(blank.to_numpy().sum())
            tally["total_count"] += int((~blank).to_numpy().sum())

            self.update_value_counts(tally, nonblank)
            self.update_numeric(tally, nonblank)
            self.update_lengths(tally, nonblank)

    def update_value_counts(self, tally, nonblank):
        """
        Add this chunk's value frequencies to the column's running counts (capped).
        Parameters: tally (dict), nonblank (Series of non-blank strings).
        Returns: None.
        """
        counts = tally["counts"]
        for value, number in nonblank.value_counts().items():
            if value in counts:
                counts[value] += int(number)
            elif len(counts) < STATS_DISTINCT_CAP:
                counts[value] = int(number)
            else:
                tally["distinct_truncated"] = True

    def update_numeric(self, tally, nonblank):
        """
        Update the numeric min/max/sum/count from any values that are numbers.
        Parameters: tally (dict), nonblank (Series).
        Returns: None.
        """
        numbers = pd.to_numeric(nonblank, errors="coerce").dropna()
        if len(numbers) == 0:
            return
        chunk_min = float(numbers.min())
        chunk_max = float(numbers.max())
        if tally["num_min"] is None or chunk_min < tally["num_min"]:
            tally["num_min"] = chunk_min
        if tally["num_max"] is None or chunk_max > tally["num_max"]:
            tally["num_max"] = chunk_max
        tally["num_sum"] += float(numbers.sum())
        tally["num_count"] += int(len(numbers))

    def update_lengths(self, tally, nonblank):
        """
        Update the shortest/longest text length seen in the column.
        Parameters: tally (dict), nonblank (Series).
        Returns: None.
        """
        if len(nonblank) == 0:
            return
        lengths = nonblank.str.len()
        chunk_min = int(lengths.min())
        chunk_max = int(lengths.max())
        if tally["len_min"] is None or chunk_min < tally["len_min"]:
            tally["len_min"] = chunk_min
        if tally["len_max"] is None or chunk_max > tally["len_max"]:
            tally["len_max"] = chunk_max

    def results(self):
        """
        Turn the running tallies into a list of finished per-column stat dicts.
        Parameters: none.
        Returns: list of dicts (one per column).
        """
        output = []
        for name, tally in self.columns.items():
            counts = tally["counts"]

            ordered = sorted(counts.items(), key=top_count, reverse=True)
            top_values = []
            for value, number in ordered[:5]:
                top_values.append({"value": short(value), "count": number})

            mean = None
            if tally["num_count"] > 0:
                mean = tally["num_sum"] / tally["num_count"]

            output.append({
                "column_name": name,
                "total_count": tally["total_count"],
                "blank_count": tally["blank_count"],
                "distinct_count": len(counts),
                "distinct_truncated": tally["distinct_truncated"],
                "numeric_min": tally["num_min"],
                "numeric_max": tally["num_max"],
                "numeric_mean": mean,
                "text_min_length": tally["len_min"],
                "text_max_length": tally["len_max"],
                "top_values": top_values,
            })
        return output


# --- the public entry points -----------------------------------------------

def validate_file(path, columns, cross_rules, allow_extra=True,
                  chunk_rows=DEFAULT_CHUNK_ROWS, file_type=None):
    """
    Validate a file on disk against a profile's rules. Picks the reader by the
    profile's file_type (or the file extension) — CSV, JSON, or XML — then runs
    the exact same column and cross-column checks on the resulting rows.
    Parameters: path (str), columns (list), cross_rules (list), allow_extra (bool),
        chunk_rows (int, CSV only), file_type (str or None: 'CSV'/'JSON'/'XML').
    Returns: dict {issues, error_count, warning_count, total_rows, headers, notes}.
    """
    kind = (file_type or "").strip().upper() or guess_kind(path)

    if kind == "JSON":
        frame = read_json_table(path)
        return validate_frames(list(frame.columns), [frame], columns,
                               cross_rules, allow_extra)
    if kind == "XML":
        frame = read_xml_table(path)
        return validate_frames(list(frame.columns), [frame], columns,
                               cross_rules, allow_extra)

    # Default: CSV, streamed in chunks so memory stays flat on huge files.
    encoding = pick_encoding(path)
    headers = read_headers(path, encoding)
    frames = iter_chunks(path, encoding, chunk_rows)
    return validate_frames(headers, frames, columns, cross_rules, allow_extra)


def validate_frames(headers, frames, columns, cross_rules, allow_extra):
    """
    Run the header checks and the per-chunk column/cross checks over a sequence
    of DataFrames. CSV passes many chunks; JSON/XML pass a single frame.
    Parameters: headers (list of str), frames (iterable of DataFrames),
        columns (list), cross_rules (list), allow_extra (bool).
    Returns: dict {issues, error_count, warning_count, total_rows, headers, notes}.
    """
    found = Findings()

    # Header-level checks first (missing required, unexpected, duplicate names).
    for issue in check_headers(headers, columns, allow_extra):
        found.add_sample((issue.get("column_name"), "header"), issue)
        found.add_total(issue["severity"], 1)

    stats = StatsCollector()
    unique_state = {}        # column name -> {"seen": set(), "truncated": bool}
    total_rows = 0
    for chunk in frames:
        chunk = chunk.reset_index(drop=True)
        offset = total_rows
        for column in columns:
            if column["name"] in chunk.columns:
                check_column_chunk(found, chunk[column["name"]], column,
                                   offset, unique_state)
        for rule in cross_rules:
            check_cross_chunk(found, chunk, rule, offset)
        # Build the statistics profile in the same pass over the data.
        stats.add_chunk(chunk)
        total_rows += len(chunk)

    return {
        "issues": found.issues,
        "error_count": found.error_total,
        "warning_count": found.warning_total,
        "total_rows": total_rows,
        "headers": headers,
        "column_count": len(headers),
        "column_stats": stats.results(),
        "notes": found.notes,
    }


def validate(df, columns, cross_rules, allow_extra=True):
    """
    Validate an in-memory DataFrame (used by tests). Same checks as a file.
    Parameters: df (DataFrame), columns (list), cross_rules (list), allow_extra (bool).
    Returns: list of issue dicts (a capped sample).
    """
    found = Findings()
    headers = list(df.columns)
    for issue in check_headers(headers, columns, allow_extra):
        found.add_sample((issue.get("column_name"), "header"), issue)
        found.add_total(issue["severity"], 1)

    unique_state = {}
    frame = df.reset_index(drop=True)
    for column in columns:
        if column["name"] in frame.columns:
            check_column_chunk(found, frame[column["name"]], column, 0, unique_state)
    for rule in cross_rules:
        check_cross_chunk(found, frame, rule, 0)
    return found.issues


# --- reading the file safely ------------------------------------------------

def pick_encoding(path):
    """
    Decide how to decode the file by test-reading its first rows.
    Parameters: path (str).
    Returns: encoding name (str). 'latin-1' is the always-works fallback.
    """
    for encoding in ("utf-8-sig", "latin-1"):
        try:
            pd.read_csv(path, dtype=str, nrows=50, encoding=encoding,
                        keep_default_na=False)
            return encoding
        except UnicodeDecodeError:
            continue
    return "latin-1"


def read_headers(path, encoding):
    """
    Read just the header row, keeping duplicate names (pandas would rename them).
    Parameters: path (str), encoding (str).
    Returns: list of header strings (empty list if the file is empty).
    """
    with open(path, "r", encoding=encoding, newline="") as handle:
        reader = csv.reader(handle)
        for row in reader:
            return row
    return []


def iter_chunks(path, encoding, chunk_rows):
    """
    Yield the file as a sequence of DataFrames, chunk_rows at a time.
    Parameters: path (str), encoding (str), chunk_rows (int).
    Returns: a generator of DataFrames.
    """
    reader = pd.read_csv(
        path, dtype=str, keep_default_na=False,
        chunksize=chunk_rows, encoding=encoding, on_bad_lines="error",
    )
    for chunk in reader:
        yield chunk


# --- reading JSON and XML ---------------------------------------------------
# Both are turned into a DataFrame of plain strings (one row per record), the
# same shape a CSV chunk has, so the existing checks work unchanged. Missing
# values become "" (blank), which the checks already understand.

def guess_kind(path):
    """
    Decide the file kind from its extension when the profile didn't say.
    Parameters: path (str).
    Returns: 'JSON', 'XML', or 'CSV'.
    """
    lowered = path.lower()
    if lowered.endswith(".json"):
        return "JSON"
    if lowered.endswith(".xml"):
        return "XML"
    return "CSV"


def stringify(value):
    """
    Turn one JSON/XML value into the plain string the checks expect.
    None becomes "", booleans become 'true'/'false', nested data becomes JSON
    text, and numbers/strings are kept as-is (so integers stay integers).
    Parameters: value (anything).
    Returns: str.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    return str(value)


def clean_record(record):
    """
    Convert one record (a dict) into a dict of column -> clean string value.
    Parameters: record (dict).
    Returns: dict.
    """
    row = {}
    for key, value in record.items():
        row[str(key)] = stringify(value)
    return row


def records_to_frame(records):
    """
    Build a string DataFrame from a list of record dicts (missing keys -> "").
    Parameters: records (list of dicts).
    Returns: a pandas DataFrame.
    """
    rows = []
    for record in records:
        rows.append(clean_record(record))
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    return frame.fillna("").astype(str)


def extract_records(data):
    """
    Find the list of record objects inside parsed JSON.
    Handles a top-level array, or an object wrapping the array under a key like
    'data'/'items'/'records'/'rows', or a single object treated as one record.
    Parameters: data (the parsed JSON value).
    Returns: list of dicts.
    """
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]

    if isinstance(data, dict):
        # Prefer well-known wrapper keys, then any value that is a list of dicts.
        for key in ("data", "items", "records", "rows", "results"):
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        for value in data.values():
            if isinstance(value, list) and value and isinstance(value[0], dict):
                return [item for item in value if isinstance(item, dict)]
        # No array inside — treat the object itself as a single record.
        return [data]

    return []


def read_json_table(path):
    """
    Read a JSON file into a string DataFrame (one row per record).
    Parameters: path (str).
    Returns: a pandas DataFrame.
    """
    with open(path, "r", encoding="utf-8-sig") as handle:
        data = json.load(handle)
    return records_to_frame(extract_records(data))


def read_xml_table(path):
    """
    Read an XML file into a string DataFrame. Each direct child of the root is a
    record; that record's attributes and child-element texts become columns.
    Parameters: path (str).
    Returns: a pandas DataFrame.
    """
    root = ET.parse(path).getroot()
    return xml_root_to_frame(root)


def local_tag(tag):
    """
    Strip any XML namespace from a tag or attribute name.
    Real vendor XML often declares a namespace, which makes ElementTree return
    tags like '{http://company.com}OrderId'; we want the bare 'OrderId' so it
    still matches the column the profile declares.
    Parameters: tag (str).
    Returns: str — the name without the namespace.
    """
    if tag and "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def element_to_row(element):
    """
    Turn one record element into a dict of column name -> text value.
    Both attributes and direct child tags become columns (namespaces stripped).
    Parameters: element (an ElementTree element).
    Returns: dict.
    """
    row = {}
    for attr_name, attr_value in element.attrib.items():
        row[local_tag(attr_name)] = (attr_value or "").strip()
    for child in element:
        text = child.text or ""
        row[local_tag(child.tag)] = text.strip()
    return row


def find_records_parent(root):
    """
    Find the element whose children are the records. Usually that is the root
    (e.g. <orders><order>...), but if the root just wraps a single container
    (e.g. <response><orders><order>...), step down into that container.
    Parameters: root (an ElementTree element).
    Returns: an ElementTree element.
    """
    current = root
    for _ in range(6):                       # safety bound; XML this deep is rare
        children = list(current)
        # A lone wrapper child that itself holds elements — go one level deeper.
        if len(children) == 1 and len(list(children[0])) > 0:
            current = children[0]
        else:
            break
    return current


def xml_root_to_frame(root):
    """
    Turn a parsed XML root element into a string DataFrame (one row per record).
    Copes with namespaces, one wrapper level, and single-record files.
    Parameters: root (an ElementTree element).
    Returns: a pandas DataFrame.
    """
    parent = find_records_parent(root)
    candidates = list(parent)

    # If every candidate element is a leaf (has no child elements), they are the
    # fields of ONE record, not a list of records — so treat the parent itself
    # as the single record.
    only_leaves = True
    for element in candidates:
        if len(list(element)) > 0:
            only_leaves = False
            break

    records = []
    if candidates and only_leaves:
        records.append(element_to_row(parent))
    else:
        for element in candidates:
            records.append(element_to_row(element))

    return records_to_frame(records)


# --- header checks ----------------------------------------------------------

def check_headers(headers, columns, allow_extra):
    """
    Check the header row for missing required, unexpected, or duplicate columns.
    Parameters: headers (list of str), columns (list of dicts), allow_extra (bool).
    Returns: list of issue dicts.
    """
    issues = []

    declared = []
    for column in columns:
        declared.append(column["name"])

    # Duplicate header names make the data ambiguous — always an error.
    seen = set()
    flagged = set()
    for header in headers:
        if header in seen and header not in flagged:
            flagged.add(header)
            issues.append(make_issue(
                rule_name="Duplicate Column",
                severity="error",
                message=f"Column '{header}' appears more than once in the header.",
                column_name=header, constraint_kind="missing_column",
            ))
        seen.add(header)

    # Required columns that are not present.
    for column in columns:
        if column["required"] and column["name"] not in headers:
            issues.append(make_issue(
                rule_name="Missing Column",
                severity=column["severity"],
                message=f"Required column '{column['name']}' is missing.",
                column_name=column["name"], constraint_kind="missing_column",
            ))

    # Columns the profile did not declare (only an error if extras are banned).
    if not allow_extra:
        for header in headers:
            if header not in declared:
                issues.append(make_issue(
                    rule_name="Unexpected Column",
                    severity="error",
                    message=f"Column '{header}' is not part of this profile.",
                    column_name=header, constraint_kind="missing_column",
                ))

    return issues


# --- per-column checks (all vectorised) -------------------------------------

def check_column_chunk(found, series, column, offset, unique_state):
    """
    Run every rule for one column across one chunk, all at once.
    Parameters: found (Findings), series (the column's values), column (rule dict),
        offset (rows seen before this chunk), unique_state (dict for the unique check).
    Returns: None (it adds to `found`).
    """
    name = column["name"]
    severity = column["severity"]
    data_type = column.get("data_type")

    stripped = series.astype(str).str.strip()
    blank = stripped == ""
    nonblank = ~blank

    # Required: a blank cell in a required column is a problem.
    if column["required"]:
        record(found, name, (name, "required"), blank, stripped, offset,
               f"{name} required", "required", severity,
               name + " cannot be blank (row {row}).")

    # Type: the value does not look like the expected kind.
    if data_type and data_type != "string":
        valid = type_valid_mask(stripped, blank, data_type)
        invalid = nonblank & ~valid
        record(found, name, (name, "type"), invalid, stripped, offset,
               f"{name} type", "type", severity,
               name + " must be a valid " + data_type + ". Found '{value}' (row {row}).")

    # Minimum.
    minimum = column.get("min_value")
    if minimum not in (None, ""):
        coerced, limit = coerce_for_bound(stripped, minimum, data_type)
        if limit is not None:
            mask = coerced.notna() & (coerced < limit)
            record(found, name, (name, "min"), mask, stripped, offset,
                   f"{name} min", "min", severity,
                   name + " must be >= " + str(minimum) + ". Found '{value}' (row {row}).")

    # Maximum.
    maximum = column.get("max_value")
    if maximum not in (None, ""):
        coerced, limit = coerce_for_bound(stripped, maximum, data_type)
        if limit is not None:
            mask = coerced.notna() & (coerced > limit)
            record(found, name, (name, "max"), mask, stripped, offset,
                   f"{name} max", "max", severity,
                   name + " must be <= " + str(maximum) + ". Found '{value}' (row {row}).")

    # Regex pattern.
    pattern = column.get("regex_pattern")
    if pattern:
        try:
            matches = stripped.str.match(pattern, na=False)
        except Exception:
            matches = None  # a broken pattern shouldn't crash the whole file
        if matches is not None:
            mask = nonblank & ~matches
            record(found, name, (name, "regex"), mask, stripped, offset,
                   f"{name} regex", "regex", severity,
                   name + " does not match the required format. Found '{value}' (row {row}).")

    # Allowed values (enum).
    allowed = column.get("allowed_values")
    if allowed:
        mask = nonblank & ~stripped.isin(allowed)
        record(found, name, (name, "allowed_values"), mask, stripped, offset,
               f"{name} allowed_values", "allowed_values", severity,
               name + " must be one of " + str(allowed) + ". Found '{value}' (row {row}).")

    # Uniqueness (needs to remember values across chunks).
    if column.get("unique_flag"):
        check_unique_chunk(found, stripped, nonblank, name, severity, offset, unique_state)


def type_valid_mask(stripped, blank, data_type):
    """
    Build a boolean mask that is True where a value fits the type (or is blank).
    Parameters: stripped (Series), blank (boolean Series), data_type (str).
    Returns: boolean Series.
    """
    if data_type == "integer":
        return stripped.str.match(INTEGER_PATTERN, na=False) | blank
    if data_type == "decimal":
        return pd.to_numeric(stripped, errors="coerce").notna() | blank
    if data_type in ("date", "datetime"):
        return to_datetime(stripped).notna() | blank
    if data_type == "email":
        return stripped.str.match(EMAIL_PATTERN, na=False) | blank
    if data_type == "boolean":
        return stripped.str.lower().isin(BOOLEAN_WORDS) | blank
    # Unknown / string: everything is acceptable.
    return pd.Series(True, index=stripped.index)


def coerce_for_bound(stripped, bound_text, data_type):
    """
    Turn a column and a min/max bound into comparable numbers or dates.
    Parameters: stripped (Series), bound_text (str), data_type (str).
    Returns: tuple (coerced Series, limit value or None).
    """
    if data_type in ("date", "datetime"):
        coerced = to_datetime(stripped)
        limit = pd.to_datetime(bound_text, errors="coerce")
        if pd.isna(limit):
            return coerced, None
        return coerced, limit

    coerced = pd.to_numeric(stripped, errors="coerce")
    try:
        limit = float(bound_text)
    except (TypeError, ValueError):
        limit = None
    return coerced, limit


def check_unique_chunk(found, stripped, nonblank, name, severity, offset, unique_state):
    """
    Flag duplicate values in a unique column, remembering values across chunks.
    Parameters: found (Findings), stripped (Series), nonblank (boolean Series),
        name (str), severity (str), offset (int), unique_state (dict).
    Returns: None.
    """
    state = unique_state.setdefault(name, {"seen": set(), "truncated": False})

    # Later copies of a value within this chunk.
    dup_in_chunk = stripped.duplicated(keep="first") & nonblank
    # Values we already saw in an earlier chunk.
    if state["seen"]:
        seen_before = nonblank & stripped.isin(state["seen"])
    else:
        seen_before = pd.Series(False, index=stripped.index)

    mask = dup_in_chunk | seen_before
    record(found, name, (name, "unique"), mask, stripped, offset,
           f"{name} unique", "unique", severity,
           "Duplicate " + name + " value '{value}' (row {row}).")

    # Remember this chunk's values for the next one (with a memory safety cap).
    if not state["truncated"]:
        present_values = stripped[nonblank].unique().tolist()
        state["seen"].update(present_values)
        if len(state["seen"]) > UNIQUE_TRACK_LIMIT:
            state["truncated"] = True
            state["seen"] = set()
            found.notes.append(
                f"The unique check on '{name}' was limited because the column "
                f"has more than {UNIQUE_TRACK_LIMIT:,} distinct values."
            )


# --- cross-column checks ----------------------------------------------------

def check_cross_chunk(found, chunk, rule, offset):
    """
    Compare two columns row by row across one chunk (e.g. DeliveryDate >= OrderDate).
    Parameters: found (Findings), chunk (DataFrame), rule (cross-rule dict), offset (int).
    Returns: None.
    """
    left = rule["left_column"]
    right = rule["right_column"]
    if left not in chunk.columns or right not in chunk.columns:
        return

    left_text = chunk[left].astype(str).str.strip()
    right_text = chunk[right].astype(str).str.strip()
    fail = cross_fail_mask(left_text, right_text, rule["op"])

    total = int(fail.to_numpy().sum())
    if total == 0:
        return
    found.add_total(rule["severity"], total)

    key = (rule["name"], "cross")
    room = found.room_for(key)
    if room <= 0:
        return

    symbol = SYMBOLS[rule["op"]]
    positions = np.nonzero(fail.to_numpy())[0][:room]
    left_values = left_text.to_numpy()
    right_values = right_text.to_numpy()
    for pos in positions:
        position = int(pos)
        row_number = offset + position + 2
        message = (f"{left} {symbol} {right} failed at row {row_number} "
                   f"({short(left_values[position])} vs {short(right_values[position])}).")
        found.add_sample(key, make_issue(
            rule_name=rule["name"], severity=rule["severity"], message=message,
            column_name=left, row_number=row_number, constraint_kind="cross",
        ))


def cross_fail_mask(left_text, right_text, op):
    """
    Work out which rows fail a two-column comparison (numbers or dates).
    Parameters: left_text (Series), right_text (Series), op (str).
    Returns: boolean Series — True where the comparison fails.
    """
    left_num = pd.to_numeric(left_text, errors="coerce")
    right_num = pd.to_numeric(right_text, errors="coerce")
    num_ok = left_num.notna() & right_num.notna()

    left_dt = to_datetime(left_text)
    right_dt = to_datetime(right_text)
    dt_ok = left_dt.notna() & right_dt.notna() & ~num_ok

    fail_num = num_ok & ~op_holds(left_num, right_num, op)
    fail_dt = dt_ok & ~op_holds(left_dt, right_dt, op)
    return fail_num | fail_dt


def op_holds(left, right, op):
    """
    Apply a comparison operator to two Series, returning a boolean Series.
    Parameters: left (Series), right (Series), op (str).
    Returns: boolean Series (True where 'left op right' holds).
    """
    if op == "gt":
        return left > right
    if op == "gte":
        return left >= right
    if op == "lt":
        return left < right
    if op == "lte":
        return left <= right
    if op == "eq":
        return left == right
    return left != right


# --- small helpers ----------------------------------------------------------

def to_datetime(series):
    """
    Parse a Series of text into dates, quietly returning NaT for bad values.
    Parameters: series (Series of str).
    Returns: Series of datetimes (NaT where parsing failed).
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return pd.to_datetime(series, errors="coerce")


def record(found, name, key, mask, value_series, offset,
           rule_name, kind, severity, template):
    """
    Count all failures in a mask and keep up to MAX_ISSUES_PER_CHECK examples.
    Parameters: found (Findings), name (str), key (tuple), mask (boolean Series),
        value_series (Series), offset (int), rule_name (str), kind (str),
        severity (str), template (str with literal {value} and {row} markers).
    Returns: None.
    """
    array = mask.to_numpy()
    total = int(array.sum())
    if total == 0:
        return

    found.add_total(severity, total)
    room = found.room_for(key)
    if room <= 0:
        return

    positions = np.nonzero(array)[0][:room]
    values = value_series.to_numpy()
    for pos in positions:
        position = int(pos)
        row_number = offset + position + 2
        message = template.replace("{value}", short(values[position]))
        message = message.replace("{row}", str(row_number))
        found.add_sample(key, make_issue(
            rule_name=rule_name, severity=severity, message=message,
            column_name=name, row_number=row_number, constraint_kind=kind,
        ))


def short(value):
    """
    Turn a cell value into a short printable string (long values are trimmed).
    Parameters: value (anything).
    Returns: str (at most ~60 characters).
    """
    text = str(value)
    if len(text) > 60:
        return text[:57] + "..."
    return text


def make_issue(rule_name, severity, message,
               column_name=None, row_number=None, constraint_kind=None):
    """
    Build one issue dict in the standard shape the rest of the app expects.
    Parameters: rule_name/severity/message (str), column_name (str),
        row_number (int), constraint_kind (str).
    Returns: dict.
    """
    return {
        "rule_name": rule_name,
        "severity": severity,
        "message": message,
        "column_name": column_name,
        "row_number": row_number,
        "constraint_kind": constraint_kind,
    }
