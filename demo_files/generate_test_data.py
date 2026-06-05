"""
Generate large good/bad CSV test files for three profile types.

Run:  python demo_files/generate_test_data.py [row_count]
      (row_count is optional; default is 10000 rows per file)

It writes 9 files into demo_files/test_data/ — for each of three types it makes
two fully-valid "good" files and one "bad" file with scattered rule violations:

  * payroll_*    (salary data)
  * timesheet_*  (hours data)
  * orders_*     (sales orders)

Drop a good file into a matching profile's inbound folder and it should pass;
drop the bad one and it should be quarantined. The intended profile rules for
each type are described in the comments next to each generator below.
"""

import os
import csv
import sys
import random

# A fixed seed so re-running gives the same data (handy when comparing runs).
random.seed(42)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "demo_files", "test_data")

FIRST_NAMES = ["Alice", "Bob", "Carol", "Dan", "Eve", "Frank", "Grace",
               "Heidi", "Ivan", "Judy", "Karl", "Liam", "Mona", "Nina"]
LAST_NAMES = ["Smith", "Jones", "Brown", "White", "Black", "Green", "Khan",
              "Patel", "Lee", "Garcia", "Singh", "Rossi", "Cohen", "Diaz"]
DEPARTMENTS = ["Engineering", "Sales", "HR", "Finance", "Marketing"]
PROJECTS = ["Apollo", "Borealis", "Cobalt", "Delta", "Everest"]
ORDER_STATUSES = ["PENDING", "PAID", "SHIPPED", "CANCELLED"]

# Roughly one row in this many gets a deliberate error in the "bad" files.
ERROR_EVERY = 6


def full_name():
    """
    Build a random person's full name.
    Parameters: none.
    Returns: str like "Alice Smith".
    """
    return random.choice(FIRST_NAMES) + " " + random.choice(LAST_NAMES)


def good_email(name):
    """
    Build a valid-looking email address from a name.
    Parameters: name (str).
    Returns: str.
    """
    handle = name.lower().replace(" ", ".")
    return handle + "@example.com"


def bad_email():
    """
    Build an invalid email address (for the bad files).
    Parameters: none.
    Returns: str.
    """
    return random.choice(["bad@@example.com", "no-at-sign.com",
                          "missing@domain", "@nohandle.com", "spaces in@x.com"])


def good_date():
    """
    Build a valid date string in YYYY-MM-DD form.
    Parameters: none.
    Returns: str.
    """
    year = random.choice([2024, 2025, 2026])
    month = random.randint(1, 12)
    day = random.randint(1, 28)
    return f"{year:04d}-{month:02d}-{day:02d}"


def bad_date():
    """
    Build an invalid date string (for the bad files).
    Parameters: none.
    Returns: str.
    """
    return random.choice(["2025-13-40", "not-a-date", "2025/02/30", "31-12-2025"])


def should_break(index):
    """
    Decide whether the row at this index should carry a deliberate error.
    Parameters: index (int row number).
    Returns: bool.
    """
    return index % ERROR_EVERY == 0


# ---------------------------------------------------------------------------
# Type 1 — PAYROLL  (pattern: payroll_*.csv)
# Suggested profile rules:
#   EmployeeId  integer, required, unique
#   FullName    string,  required
#   Email       email,   required
#   Department  string,  allowed: Engineering/Sales/HR/Finance/Marketing
#   Salary      decimal, required, min 30000, max 500000
#   PayDate     date,    required
# ---------------------------------------------------------------------------
def payroll_rows(count, bad):
    """
    Make payroll rows (header first), valid unless bad is True.
    Parameters: count (int), bad (bool — scatter rule violations).
    Returns: list of rows (each a list), header included.
    """
    rows = [["EmployeeId", "FullName", "Email", "Department", "Salary", "PayDate"]]
    for index in range(count):
        employee_id = 1000 + index
        name = full_name()
        email = good_email(name)
        department = random.choice(DEPARTMENTS)
        salary = random.randint(30000, 500000)
        pay_date = good_date()

        if bad and should_break(index):
            choice = random.randint(1, 6)
            if choice == 1:
                email = bad_email()                      # invalid email
            elif choice == 2:
                salary = random.randint(1000, 29000)     # below the minimum
            elif choice == 3:
                salary = random.randint(500001, 900000)  # above the maximum
            elif choice == 4:
                department = "Operations"                # not in allowed list
            elif choice == 5:
                employee_id = "12A"                       # not an integer
            else:
                name = ""                                 # missing required name

        rows.append([employee_id, name, email, department, salary, pay_date])
    return rows


# ---------------------------------------------------------------------------
# Type 2 — TIMESHEET  (pattern: timesheet_*.csv)
# Suggested profile rules:
#   EntryId      integer, required, unique
#   EmployeeId   integer, required
#   WorkDate     date,    required
#   HoursWorked  decimal, required, min 0, max 24
#   Project      string,  required
#   Approved     string,  allowed: true/false
# ---------------------------------------------------------------------------
def timesheet_rows(count, bad):
    """
    Make timesheet rows (header first), valid unless bad is True.
    Parameters: count (int), bad (bool — scatter rule violations).
    Returns: list of rows (each a list), header included.
    """
    rows = [["EntryId", "EmployeeId", "WorkDate", "HoursWorked", "Project", "Approved"]]
    for index in range(count):
        entry_id = 5000 + index
        employee_id = random.randint(1000, 1200)
        work_date = good_date()
        hours = round(random.uniform(0.5, 12.0), 1)
        project = random.choice(PROJECTS)
        approved = random.choice(["true", "false"])

        if bad and should_break(index):
            choice = random.randint(1, 5)
            if choice == 1:
                hours = round(random.uniform(24.5, 60.0), 1)  # more than 24h
            elif choice == 2:
                hours = -round(random.uniform(1.0, 5.0), 1)   # negative hours
            elif choice == 3:
                work_date = bad_date()                        # invalid date
            elif choice == 4:
                project = ""                                  # missing required
            else:
                approved = "maybe"                            # not true/false

        rows.append([entry_id, employee_id, work_date, hours, project, approved])
    return rows


# ---------------------------------------------------------------------------
# Type 3 — SALES ORDERS  (pattern: orders_*.csv)
# Suggested profile rules:
#   OrderId        string,  required, unique, regex ^ORD-\d{6}$
#   CustomerEmail  email,   required
#   Amount         decimal, required, min 0.01
#   OrderDate      date,    required
#   Status         string,  allowed: PENDING/PAID/SHIPPED/CANCELLED
# ---------------------------------------------------------------------------
def orders_rows(count, bad):
    """
    Make sales-order rows (header first), valid unless bad is True.
    Parameters: count (int), bad (bool — scatter rule violations).
    Returns: list of rows (each a list), header included.
    """
    rows = [["OrderId", "CustomerEmail", "Amount", "OrderDate", "Status"]]
    for index in range(count):
        order_id = f"ORD-{index:06d}"
        name = full_name()
        email = good_email(name)
        amount = round(random.uniform(1.0, 5000.0), 2)
        order_date = good_date()
        status = random.choice(ORDER_STATUSES)

        if bad and should_break(index):
            choice = random.randint(1, 5)
            if choice == 1:
                order_id = f"PO{index}"               # wrong id format
            elif choice == 2:
                email = bad_email()                   # invalid email
            elif choice == 3:
                amount = 0.0                          # below the 0.01 minimum
            elif choice == 4:
                status = "RETURNED"                   # not in allowed list
            else:
                order_date = bad_date()               # invalid date

        rows.append([order_id, email, amount, order_date, status])
    return rows


def write_csv(file_name, rows):
    """
    Write rows to a CSV file in the output folder.
    Parameters: file_name (str), rows (list of lists, header first).
    Returns: None.
    """
    path = os.path.join(OUT_DIR, file_name)
    with open(path, "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerows(rows)
    size_kb = round(os.path.getsize(path) / 1024)
    print(f"  wrote {file_name:24} ({len(rows) - 1} rows, {size_kb} KB)")


def main():
    """
    Generate two good files and one bad file for each of the three types.
    Parameters: none (reads an optional row count from the command line).
    Returns: None.
    """
    count = 10000
    if len(sys.argv) > 1:
        count = int(sys.argv[1])

    os.makedirs(OUT_DIR, exist_ok=True)
    print(f"Generating {count} rows per file into {OUT_DIR}\n")

    print("Payroll:")
    write_csv("payroll_good_1.csv", payroll_rows(count, bad=False))
    write_csv("payroll_good_2.csv", payroll_rows(count, bad=False))
    write_csv("payroll_bad.csv", payroll_rows(count, bad=True))

    print("Timesheet:")
    write_csv("timesheet_good_1.csv", timesheet_rows(count, bad=False))
    write_csv("timesheet_good_2.csv", timesheet_rows(count, bad=False))
    write_csv("timesheet_bad.csv", timesheet_rows(count, bad=True))

    print("Sales orders:")
    write_csv("orders_good_1.csv", orders_rows(count, bad=False))
    write_csv("orders_good_2.csv", orders_rows(count, bad=False))
    write_csv("orders_bad.csv", orders_rows(count, bad=True))

    print("\nDone. Files are in:", OUT_DIR)


if __name__ == "__main__":
    main()
