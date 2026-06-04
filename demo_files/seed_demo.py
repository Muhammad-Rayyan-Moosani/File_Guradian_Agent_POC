"""
Seed the demo: 3 validation profiles + good/bad sample files.

Run:  python demo_files/seed_demo.py

Wipes existing profiles and runs (clean slate), creates three profiles each
with its own inbound folder under demo_files/, and writes good + bad sample
CSVs into demo_files/samples/.
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


def col(name, order, required=False, unique=False, data_type=None,
        min_value=None, max_value=None, regex=None, allowed=None,
        severity="error", description=None):
    """Build one profile_columns row (without profile_id, added later)."""
    return {
        "name": name, "column_order": order, "description": description,
        "required": required, "unique_flag": unique, "data_type": data_type,
        "min_value": min_value, "max_value": max_value, "regex_pattern": regex,
        "allowed_values": allowed, "severity": severity,
    }


def make_profile(name, pattern, inbound, columns, cross_rules, recipients):
    """Insert a profile plus its columns and cross-column rules."""
    os.makedirs(inbound, exist_ok=True)
    row = db.insert("validation_profiles", {
        "name": name, "description": f"Demo profile for {pattern} files.",
        "active": True, "file_pattern": pattern, "file_type": "CSV",
        "allow_extra_columns": True, "inbound_folder": inbound,
        "success_routing": GOOD, "failure_routing": QUAR, "unknown_routing": REVIEW,
        "notify_on_failure": True, "notify_channel": "email",
        "email_recipients": recipients,
    })
    pid = row["id"]

    for c in columns:
        c["profile_id"] = pid
    db.insert_many("profile_columns", columns)

    for r in cross_rules:
        r["profile_id"] = pid
    if cross_rules:
        db.insert_many("profile_cross_column_rules", cross_rules)

    print(f"  created '{name}'  (pattern {pattern}, {len(columns)} columns) -> {inbound}")
    return pid


def wipe_existing():
    """Delete all existing profiles and runs for a clean demo."""
    runs = db.query_all("SELECT id FROM validation_runs")
    for r in runs:
        db.delete_where("validation_runs", "id", r["id"])
    profiles = db.query_all("SELECT id FROM validation_profiles")
    for p in profiles:
        db.delete_where("validation_profiles", "id", p["id"])
    print(f"wiped {len(profiles)} profile(s) and {len(runs)} run(s)")


def write(path, text):
    """Write a sample file."""
    with open(path, "w") as f:
        f.write(text)
    print("  wrote", os.path.relpath(path, ROOT))


def main():
    for d in (GOOD, QUAR, REVIEW, SAMPLES):
        os.makedirs(d, exist_ok=True)

    print("Cleaning up…")
    wipe_existing()

    inv_in = os.path.join(BASE, "invoices")
    po_in = os.path.join(BASE, "purchase_orders")
    emp_in = os.path.join(BASE, "employees")

    print("Creating profiles…")

    # 1) Invoice CSV — regex, unique, decimal min, email (warning), enum (warning)
    make_profile(
        "Invoice CSV Validation", "invoices_*.csv", inv_in,
        [
            col("CustomerId", 0, required=True, data_type="string"),
            col("CustomerName", 1, required=True, data_type="string"),
            col("InvoiceNumber", 2, required=True, unique=True, data_type="string",
                regex=r"^INV-\d{4,8}$"),
            col("InvoiceDate", 3, required=True, data_type="date"),
            col("Amount", 4, required=True, data_type="decimal", min_value="0.01"),
            col("Email", 5, data_type="email", severity="warning"),
            col("Status", 6, data_type="string",
                allowed=["PAID", "DUE", "VOID"], severity="warning"),
        ],
        [],
        ["ops-team@xorbix.com", "billing-lead@xorbix.com"],
    )

    # 2) Purchase Order CSV — regex, unique, enum, AND a cross-column rule
    make_profile(
        "Purchase Order CSV", "po_*.csv", po_in,
        [
            col("PoNumber", 0, required=True, unique=True, data_type="string",
                regex=r"^PO-\d{5}$"),
            col("VendorId", 1, required=True, data_type="string"),
            col("OrderDate", 2, required=True, data_type="date"),
            col("DeliveryDate", 3, required=True, data_type="date"),
            col("TotalAmount", 4, required=True, data_type="decimal", min_value="1"),
            col("Currency", 5, data_type="string",
                allowed=["USD", "EUR", "GBP"], severity="warning"),
        ],
        [{"name": "DeliveryDate on/after OrderDate", "left_column": "DeliveryDate",
          "op": "gte", "right_column": "OrderDate", "severity": "error"}],
        ["procurement@xorbix.com"],
    )

    # 3) Employee CSV — integer, email (error), enum (error), min AND max
    make_profile(
        "Employee CSV", "employees_*.csv", emp_in,
        [
            col("EmployeeId", 0, required=True, unique=True, data_type="integer"),
            col("FullName", 1, required=True, data_type="string"),
            col("Email", 2, required=True, data_type="email"),
            col("Department", 3, data_type="string",
                allowed=["Engineering", "Sales", "HR", "Finance"]),
            col("Salary", 4, required=True, data_type="decimal",
                min_value="30000", max_value="500000"),
            col("StartDate", 5, required=True, data_type="date"),
        ],
        [],
        ["hr@xorbix.com"],
    )

    print("Writing sample files…")

    # --- Invoice samples ---
    write(os.path.join(SAMPLES, "invoices_good.csv"),
          "CustomerId,CustomerName,InvoiceNumber,InvoiceDate,Amount,Email,Status\n"
          "C100,Acme Corp,INV-1001,2026-05-01,250.00,billing@acme.com,PAID\n"
          "C101,Globex,INV-1002,2026-05-02,980.50,ap@globex.com,DUE\n"
          "C102,Initech,INV-1003,2026-05-03,49.99,finance@initech.com,PAID\n")
    write(os.path.join(SAMPLES, "invoices_bad.csv"),
          "CustomerId,CustomerName,InvoiceNumber,InvoiceDate,Amount,Email,Status\n"
          "C200,Wayne Ent,INV-2001,2026-05-04,-50.00,bad@@wayne,PAID\n"          # neg amount, bad email
          ",Stark Industries,INV-2001,not-a-date,0.00,info@stark.com,SHIPPED\n"  # blank CustomerId, dup INV, bad date, zero amount, bad status
          "C202,Oscorp,INVALID99,2026-05-06,120.00,procure@oscorp.com,DUE\n")    # regex fail on InvoiceNumber

    # --- Purchase Order samples ---
    write(os.path.join(SAMPLES, "po_good.csv"),
          "PoNumber,VendorId,OrderDate,DeliveryDate,TotalAmount,Currency\n"
          "PO-10001,V100,2026-05-01,2026-05-10,5000.00,USD\n"
          "PO-10002,V101,2026-05-03,2026-05-12,250.00,EUR\n")
    write(os.path.join(SAMPLES, "po_bad.csv"),
          "PoNumber,VendorId,OrderDate,DeliveryDate,TotalAmount,Currency\n"
          "PO-12,V100,2026-05-10,2026-05-01,0,USD\n"        # regex fail, delivery<order (cross), amount<min
          "PO-10005,V101,2026-05-03,2026-05-12,100,YEN\n"   # bad currency enum
          "PO-10005,V102,2026-05-04,2026-05-20,500,USD\n")  # duplicate PoNumber

    # --- Employee samples ---
    write(os.path.join(SAMPLES, "employees_good.csv"),
          "EmployeeId,FullName,Email,Department,Salary,StartDate\n"
          "1001,Alice Smith,alice@corp.com,Engineering,120000,2024-01-15\n"
          "1002,Bob Jones,bob@corp.com,Sales,85000,2023-06-01\n")
    write(os.path.join(SAMPLES, "employees_bad.csv"),
          "EmployeeId,FullName,Email,Department,Salary,StartDate\n"
          "12A,Carol White,carol@@corp,Marketing,20000,2026-02-30\n"   # non-int id, bad email, bad dept, salary<min, bad date
          "1001,Dan Brown,dan@corp.com,Engineering,900000,2024-05-01\n"  # salary>max
          "1001,Eve Black,eve@corp.com,HR,50000,2024-03-01\n")          # duplicate EmployeeId

    print("\nDone. Inbound folders to drop files into:")
    print("  invoices_*.csv     ->", inv_in)
    print("  po_*.csv           ->", po_in)
    print("  employees_*.csv    ->", emp_in)
    print("Sample files are in:", SAMPLES)


if __name__ == "__main__":
    main()
