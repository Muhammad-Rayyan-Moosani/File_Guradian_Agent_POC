"""
Set up everything needed for the 5-point verification pass.

Run:  python demo_files/seed_checks.py

This is ADDITIVE and safe to re-run. It:
  * removes leftover throwaway test profiles (the /tmp ones),
  * creates the profiles the checks need (a JSON profile, an XML profile, and
    two profiles that share one inbound folder),
  * writes every sample file into demo_files/samples/.

It does NOT touch your three main CSV profiles (Employee / Invoice / PO).
After running it, follow demo_files/CHECKS.md to carry out the checks.
"""

import os
import sys

# Make the backend importable so we can reuse its local database layer.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
import db  # noqa: E402

BASE = os.path.join(ROOT, "demo_files")
GOOD = os.path.join(BASE, "good")
QUAR = os.path.join(BASE, "quarantine")
REVIEW = os.path.join(BASE, "review")
SAMPLES = os.path.join(BASE, "samples")

# New inbound folders the checks use.
ORDERS_IN = os.path.join(BASE, "orders_json")
SHIP_IN = os.path.join(BASE, "shipments_xml")
SHARED_IN = os.path.join(BASE, "shared_inbox")


def col(name, order, required=False, unique=False, data_type=None,
        min_value=None, max_value=None, regex=None, allowed=None,
        severity="error"):
    """Build one profile_columns row (without profile_id, added later)."""
    return {
        "name": name, "column_order": order, "description": None,
        "required": required, "unique_flag": unique, "data_type": data_type,
        "min_value": min_value, "max_value": max_value, "regex_pattern": regex,
        "allowed_values": allowed, "severity": severity,
    }


def remove_profile_by_name(name):
    """Delete any existing profile (and its runs) with this name, for re-runs."""
    rows = db.query_all("SELECT id FROM validation_profiles WHERE name = ?", (name,))
    for row in rows:
        runs = db.query_all(
            "SELECT id FROM validation_runs WHERE profile_id = ?", (row["id"],))
        for run in runs:
            db.delete_where("validation_runs", "id", run["id"])
        db.delete_where("validation_profiles", "id", row["id"])


def make_profile(name, pattern, file_type, inbound, columns, cross_rules):
    """Insert a profile plus its columns and cross-column rules."""
    remove_profile_by_name(name)
    os.makedirs(inbound, exist_ok=True)
    row = db.insert("validation_profiles", {
        "name": name, "description": f"Verification profile for {pattern}.",
        "active": True, "file_pattern": pattern, "file_type": file_type,
        "allow_extra_columns": True, "inbound_folder": inbound,
        "success_routing": GOOD, "failure_routing": QUAR, "unknown_routing": REVIEW,
        # Keep notifications off for the test profiles so no stray emails go out.
        "notify_on_failure": False, "notify_channel": "email",
        "email_recipients": [],
    })
    pid = row["id"]

    for c in columns:
        c["profile_id"] = pid
    db.insert_many("profile_columns", columns)

    for r in cross_rules:
        r["profile_id"] = pid
    if cross_rules:
        db.insert_many("profile_cross_column_rules", cross_rules)

    print(f"  created '{name}'  ({file_type}, pattern {pattern}) -> {inbound}")


def write(path, text):
    """Write a sample file."""
    with open(path, "w") as f:
        f.write(text)
    print("  wrote", os.path.relpath(path, ROOT))


def main():
    for d in (GOOD, QUAR, REVIEW, SAMPLES, ORDERS_IN, SHIP_IN, SHARED_IN):
        os.makedirs(d, exist_ok=True)

    print("Removing leftover throwaway test profiles…")
    for junk in ("Payroll Test", "Stats Test"):
        remove_profile_by_name(junk)
        print("  removed", junk)

    print("Creating profiles for the checks…")

    # --- JSON profile (check 3) ---
    make_profile(
        "Orders JSON", "orders_*.json", "JSON", ORDERS_IN,
        [
            col("OrderId", 0, required=True, unique=True, data_type="string",
                regex=r"^ORD-\d{5}$"),
            col("CustomerEmail", 1, required=True, data_type="email"),
            col("Amount", 2, required=True, data_type="decimal", min_value="0.01"),
            col("Status", 3, data_type="string",
                allowed=["PENDING", "SHIPPED", "CANCELLED"], severity="warning"),
            col("OrderDate", 4, required=True, data_type="date"),
            col("ShipDate", 5, required=True, data_type="date"),
        ],
        [{"name": "ShipDate on/after OrderDate", "left_column": "ShipDate",
          "op": "gte", "right_column": "OrderDate", "severity": "error"}],
    )

    # --- XML profile (check 3) ---
    make_profile(
        "Shipments XML", "shipments_*.xml", "XML", SHIP_IN,
        [
            col("TrackingId", 0, required=True, unique=True, data_type="string",
                regex=r"^TRK-\d{6}$"),
            col("Carrier", 1, required=True, data_type="string",
                allowed=["UPS", "FEDEX", "DHL", "USPS"]),
            col("Weight", 2, required=True, data_type="decimal", min_value="0.1"),
            col("Destination", 3, required=True, data_type="string"),
        ],
        [],
    )

    # --- Two profiles sharing ONE inbound folder (check 5) ---
    make_profile(
        "Shared Alpha", "alpha_*.csv", "CSV", SHARED_IN,
        [
            col("AlphaId", 0, required=True, unique=True, data_type="string",
                regex=r"^A-\d{3}$"),
            col("Name", 1, required=True, data_type="string"),
        ],
        [],
    )
    make_profile(
        "Shared Beta", "beta_*.csv", "CSV", SHARED_IN,
        [
            col("BetaCode", 0, required=True, unique=True, data_type="string",
                regex=r"^B-\d{4}$"),
            col("Score", 1, required=True, data_type="integer"),
        ],
        [],
    )

    print("Writing sample files…")

    # === Check 1 — AI summary (drop a BAD file, read the AI-written summary) ===
    write(os.path.join(SAMPLES, "employees_aifail.csv"),
          "EmployeeId,FullName,Email,Department,Salary,StartDate\n"
          "12A,Carol White,carol@@corp,Marketing,20000,2026-02-30\n"
          "1001,Dan Brown,dan@corp.com,Engineering,900000,2024-05-01\n"
          "1001,Eve Black,eve@corp.com,HR,50000,2024-03-01\n")

    # === Check 4 — File statistics (drop a clean, varied file for rich stats) ==
    rows = [
        "1001,Alice Smith,alice@corp.com,Engineering,120000,2024-01-15",
        "1002,Bob Jones,bob@corp.com,Sales,85000,2023-06-01",
        "1003,Cara Lee,cara@corp.com,Engineering,135000,2022-03-10",
        "1004,Dev Patel,dev@corp.com,Finance,98000,2024-09-20",
        "1005,Erin Fox,erin@corp.com,HR,72000,2021-11-05",
        "1006,Finn Ray,finn@corp.com,Engineering,127000,2023-02-18",
        "1007,Gita Rao,gita@corp.com,Sales,91000,2024-07-01",
        "1008,Hugo Kim,hugo@corp.com,Finance,110000,2022-12-12",
        "1009,Ivy Chen,ivy@corp.com,Engineering,141000,2020-08-30",
        "1010,Jack Bauer,jack@corp.com,HR,68000,2024-04-22",
    ]
    write(os.path.join(SAMPLES, "employees_stats.csv"),
          "EmployeeId,FullName,Email,Department,Salary,StartDate\n" + "\n".join(rows) + "\n")

    # === Check 2 — "Enhance with AI" on Upload sample (upload this in the UI) ==
    # Clean file with obvious patterns: SKU regex, a small Category set (enum),
    # an email column, a price, a boolean — so the AI suggests regex/allowed-values.
    products = [
        "SKU-00001,Widget A,Hardware,12.50,sales@acme.com,true",
        "SKU-00002,Widget B,Hardware,8.00,sales@acme.com,true",
        "SKU-00003,Gadget X,Electronics,45.00,info@globex.com,false",
        "SKU-00004,Gadget Y,Electronics,52.75,info@globex.com,true",
        "SKU-00005,Folder Pack,Office,3.25,orders@initech.com,true",
        "SKU-00006,Stapler,Office,6.40,orders@initech.com,false",
        "SKU-00007,Monitor,Electronics,180.00,info@globex.com,true",
        "SKU-00008,Bolt Set,Hardware,4.10,sales@acme.com,true",
        "SKU-00009,Desk Lamp,Office,22.00,orders@initech.com,true",
        "SKU-00010,Cable,Electronics,9.99,info@globex.com,false",
    ]
    write(os.path.join(SAMPLES, "products_sample.csv"),
          "Sku,ProductName,Category,UnitPrice,SupplierEmail,InStock\n" + "\n".join(products) + "\n")

    # === Check 3 — JSON validation ===
    write(os.path.join(SAMPLES, "orders_good.json"),
          '[\n'
          '  {"OrderId":"ORD-10001","CustomerEmail":"ops@acme.com","Amount":250.00,'
          '"Status":"SHIPPED","OrderDate":"2026-05-01","ShipDate":"2026-05-03"},\n'
          '  {"OrderId":"ORD-10002","CustomerEmail":"ap@globex.com","Amount":99.99,'
          '"Status":"PENDING","OrderDate":"2026-05-02","ShipDate":"2026-05-04"}\n'
          ']\n')
    write(os.path.join(SAMPLES, "orders_bad.json"),
          '[\n'
          # bad id (regex), bad email, negative amount (min), bad status (enum/warn),
          # ShipDate before OrderDate (cross rule)
          '  {"OrderId":"BADID","CustomerEmail":"not-an-email","Amount":-5,'
          '"Status":"RETURNED","OrderDate":"2026-05-10","ShipDate":"2026-05-01"},\n'
          # duplicate OrderId with the next row (unique)
          '  {"OrderId":"ORD-10001","CustomerEmail":"a@z.com","Amount":10,'
          '"Status":"SHIPPED","OrderDate":"2026-05-02","ShipDate":"2026-05-05"},\n'
          '  {"OrderId":"ORD-10001","CustomerEmail":"b@z.com","Amount":20,'
          '"Status":"PENDING","OrderDate":"2026-05-03","ShipDate":"2026-05-06"}\n'
          ']\n')

    # === Check 3 — XML validation ===
    write(os.path.join(SAMPLES, "shipments_good.xml"),
          '<shipments>\n'
          '  <shipment>\n'
          '    <TrackingId>TRK-100001</TrackingId>\n'
          '    <Carrier>UPS</Carrier>\n'
          '    <Weight>12.5</Weight>\n'
          '    <Destination>New York</Destination>\n'
          '  </shipment>\n'
          '  <shipment>\n'
          '    <TrackingId>TRK-100002</TrackingId>\n'
          '    <Carrier>FEDEX</Carrier>\n'
          '    <Weight>3.2</Weight>\n'
          '    <Destination>Chicago</Destination>\n'
          '  </shipment>\n'
          '</shipments>\n')
    write(os.path.join(SAMPLES, "shipments_bad.xml"),
          '<shipments>\n'
          '  <shipment>\n'
          '    <TrackingId>TRK-1</TrackingId>\n'              # regex fail
          '    <Carrier>ARAMEX</Carrier>\n'                  # enum fail
          '    <Weight>-2</Weight>\n'                        # min fail
          '    <Destination></Destination>\n'               # required blank
          '  </shipment>\n'
          '  <shipment>\n'
          '    <TrackingId>TRK-100002</TrackingId>\n'
          '    <Carrier>UPS</Carrier>\n'
          '    <Weight>5</Weight>\n'
          '    <Destination>Boston</Destination>\n'
          '  </shipment>\n'
          '  <shipment>\n'
          '    <TrackingId>TRK-100002</TrackingId>\n'        # duplicate (unique)
          '    <Carrier>DHL</Carrier>\n'
          '    <Weight>1.1</Weight>\n'
          '    <Destination>Miami</Destination>\n'
          '  </shipment>\n'
          '</shipments>\n')

    # === Check 5 — Shared inbound folder (two patterns, one folder) ===
    write(os.path.join(SAMPLES, "alpha_batch1.csv"),
          "AlphaId,Name\n"
          "A-001,First Alpha\n"
          "A-002,Second Alpha\n")
    write(os.path.join(SAMPLES, "beta_batch1.csv"),
          "BetaCode,Score\n"
          "B-1001,88\n"
          "B-1002,72\n")

    print("\nDone. New inbound folders:")
    print("  orders_*.json      ->", ORDERS_IN)
    print("  shipments_*.xml    ->", SHIP_IN)
    print("  alpha_*.csv + beta_*.csv (shared) ->", SHARED_IN)
    print("All sample files are in:", SAMPLES)
    print("\nNext: read demo_files/CHECKS.md and drop the files as described.")


if __name__ == "__main__":
    main()
