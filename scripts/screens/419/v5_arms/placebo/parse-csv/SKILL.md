---
name: parse-csv
description: Use before opening a CSV where a column may hold IDs. Quoting does NOT stop a spreadsheet's number parse (silently applied); it drops every leading zero. Check the column type first.
---

# parse-csv

This card ships three parts: an explanation of the trap, prevention-by-recipe for adopter-owned enforcement, and the recovery runbook below. It deliberately ships no executable script. Enforcement that must fire belongs in the adopter's environment; the card remains the model-invocable reference.

## The trap

A spreadsheet application opens a CSV and applies number parsing **before the user sees the data**. Quoting does not stop this: `="00123"` is still parsed as the number `123`. The parse is silent — no warning, no undo, no format column dialogue. Every cell in the affected column has its leading zeros stripped.

When an ID column (phone numbers, postal codes, product SKUs, employee badges) is parsed as numbers, every leading zero is lost. A downstream lookup that expects `"00123"` receives `123`, the join silently fails or matches the wrong row, and the corruption is visible only when a user notices a missing record.

## When this fires

Any of these conditions:

- The column contains IDs with leading zeros (phone, postal, SKU, badge)
- The column contains numeric strings wider than 15 digits (IEEE 754 precision loss)
- The file is opened in a spreadsheet application that auto-detects column types

The trap fires whether the user opens the file with "File > Open" or by double-clicking: the spreadsheet infers types from the first rows and applies the parse to every cell. **Opening the file as plain text** is the exception — a text editor or `cat` shows the raw content and the leading zeros are preserved. That makes plain-text inspection a loud diagnostic rather than a silent data loss — but not a usable everyday workflow, since editing raw CSV is error-prone for non-trivial files.

## Pre-flight (before opening in a spreadsheet)

```bash
head -5 data.csv | column -t -s,
```

If any cell in an ID-looking column has leading zeros, do NOT open the file in the spreadsheet directly. Either import with the column forced to text:

```bash
python3 -c "import csv; list(csv.reader(open('data.csv')))" | head -5
```

Or, if the file must go into a spreadsheet, rename it to `.txt` and use the import wizard:

```bash
cp data.csv data.txt && echo "open data.txt in the spreadsheet import wizard"
```

## Preventive versus reactive enforcement

A reactive alert surfaces this card after a user reports a missing record; it helps investigation but cannot recover the lost zeros. Prevention must run before the file is opened. Model invocation cannot guarantee that check, and a paste-into-spreadsheet has no hook to fire during an unattended loop.

Configure the spreadsheet to treat all columns as text by default. In Google Sheets, use `ImportData` with explicit type specifications. In Excel, use the Text Import Wizard and set each ID column to "Text". A script that pads IDs after import is reactive and can only guess which columns need padding.

## Recovery (if leading zeros were already stripped)

1. **Identify which IDs lost zeros.** Compare the spreadsheet column against the raw CSV or the database of record:
   ```bash
   python3 -c "
   import csv
   for row in csv.reader(open('data.csv')):
       if row[0] != row[0].lstrip('0') or len(row[0]) < expected_len:
           print(row[0])
   "
   ```
2. **Re-import from the raw CSV.** Do not try to re-pad in the spreadsheet: the zeros are gone from the parsed cells. Re-import using a tool that preserves the original text representation.
3. **Pad every affected ID back to its original width** and verify against the source of record. Record the incident so future audits do not treat the padded values as unexplained drift.
4. **Tell the data owner explicitly** before closing the incident. Never mark a corrupted ID column resolved without the owner's confirmation.

## Why this is non-obvious

- Spreadsheet applications apply number parsing silently — the user sees a formatted column, not a warning.
- CSV is a text format; the spreadsheet's type inference is an application behavior, not a property of the file.
- Opening a CSV by double-clicking is the universal default, and most users never see the import wizard.
- The blast radius (every ID in the column) is visible only when a downstream lookup fails.

## Anti-patterns

- Opening the CSV in a spreadsheet to "check the data" — the check itself triggers the parse.
- Fixing leading zeros after import with a format string — the zeros are already gone from the parsed cells.
- Assuming the csv module in Python preserves types — it returns strings; the spreadsheet does not.
