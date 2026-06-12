# Verification runbook — 5 checks

Setup (once):
```bash
# 1. create the profiles + sample files (safe to re-run)
python demo_files/seed_checks.py
# 2. start the app (API + monitor) and leave it running
python backend/app.py
# 3. open the dashboard
#    http://localhost:6200   (npm run dev in /frontend if it isn't up)
```

"Drop a file" = **copy** a file from `demo_files/samples/` into the inbound folder
while the app is running (copy, not move, so the samples stay for re-runs). Each
check has a ready `cp` command. After dropping, open the dashboard (it
auto-refreshes), click the new run, and check the expected result.

---

## ✅ Check 1 — AI summary is genuinely AI-written
Drop a bad file, open the run, read the **Summary** — it should be a natural,
specific sentence (not the stiff template). This proves the Claude CLI hookup is
used end-to-end, not just the Test button.

```bash
cp demo_files/samples/employees_aifail.csv demo_files/employees/
```
- **Profile:** Employee CSV → **Expect:** Failed, 7 errors, file in `quarantine/`.
- **Look at:** the AI Summary / Impact / Action on the run detail. It should read
  like a person wrote it (e.g. "Three employee rows have problems — one ID isn't a
  number, two salaries are out of range, …"), not a flat list.

---

## ✅ Check 2 — "Enhance with AI" on Upload sample
In the UI: **Validation Profiles → New profile → Upload sample**, choose the file
below, turn the **Enhance with AI** toggle **ON**, and confirm it suggests things.

File to upload (do NOT drop this in a folder — upload it in the form):
```
demo_files/samples/products_sample.csv
```
- **Expect the AI to suggest:** a **regex** for `Sku` (it's always `SKU-#####`),
  an **allowed-values** list for `Category` (Hardware / Electronics / Office),
  `SupplierEmail` as an **email** type, `UnitPrice` as **decimal**, `InStock` as
  **boolean**. You don't have to save — seeing sensible suggestions is the check.

---

## ✅ Check 3 — JSON and XML validate like CSV
Same engine, different formats.

**JSON:**
```bash
cp demo_files/samples/orders_good.json demo_files/orders_json/   # -> Passed (good folder)
cp demo_files/samples/orders_bad.json  demo_files/orders_json/   # -> Failed, 5 errors + 1 warning
```
- Profile **Orders JSON**. Bad-file errors: OrderId regex, bad email, negative
  Amount, duplicate OrderId, ShipDate-before-OrderDate (cross rule); warning: bad Status.

**XML:**
```bash
cp demo_files/samples/shipments_good.xml demo_files/shipments_xml/  # -> Passed
cp demo_files/samples/shipments_bad.xml  demo_files/shipments_xml/  # -> Failed, 5 errors
```
- Profile **Shipments XML**. Bad-file errors: TrackingId regex, bad Carrier,
  negative Weight, blank Destination, duplicate TrackingId.

---

## ✅ Check 4 — File statistics
Open **any** processed run and confirm the header shows **Rows / Columns** and
there's a **File statistics** table (per-column: count, blanks, distinct,
numeric min/max/mean, top values).

```bash
cp demo_files/samples/employees_stats.csv demo_files/employees/
```
- **Profile:** Employee CSV → **Expect:** Passed, 10 rows, 6 columns. Open the run
  and read the statistics table — Salary should show a real min/max/mean, Department
  should show its top values, etc. (Any earlier run works too; this one just has
  richer numbers.)

---

## ✅ Check 5 — Shared inbound folder, two profiles
Two profiles (**Shared Alpha** `alpha_*.csv`, **Shared Beta** `beta_*.csv`) both
watch the **same** folder. Drop one of each and confirm each is matched to the
**right** profile (the bug we fixed).

```bash
cp demo_files/samples/alpha_batch1.csv demo_files/shared_inbox/
cp demo_files/samples/beta_batch1.csv  demo_files/shared_inbox/
```
- **Expect two separate runs:** `alpha_batch1.csv` → profile **Shared Alpha**
  (Passed); `beta_batch1.csv` → profile **Shared Beta** (Passed). Neither should be
  sent to review or matched to the wrong profile.

---

### Reset between runs (optional)
Delete a run from the dashboard (trash icon) to remove its record **and** the moved
file, or re-run `python demo_files/seed_checks.py` to rewrite all samples. The
three main CSV profiles (Employee / Invoice / PO) are left untouched.
