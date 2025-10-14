#!/usr/bin/env python3
"""
Build raffle entry list from an Excel file.

Steps:
1) Filter rows where column "ID1" == 6610
2) Build "Full Name - Email1 - Phone Number" for each remaining row
3) Repeat each row by the integer value of "Tickets Purchased"
4) Save as a one-column Excel file ("Entry" by default)

Usage:
  python build_raffle_list.py input.xlsx -o output.xlsx --sheet "Sheet1"

Requirements:
  pip install pandas openpyxl
"""

import argparse
import sys
import pandas as pd


REQUIRED_COLUMNS = {
    "ID1": "U",
    "Full Name": "I",
    "Email1": "L",
    "Phone Number": "O",
    "Tickets Purchased": "R",
}


def clean_cell(x):
    """Return a stripped string, or '' for NaN/None."""
    if pd.isna(x):
        return ""
    return str(x).strip()


def build_raffle_entries(input_path: str, output_path: str, sheet_name: str | None, no_header: bool) -> int:
    # Read as strings to preserve things like leading zeros in phone numbers/emails
    df = pd.read_excel(input_path, sheet_name=sheet_name, dtype=str, engine="openpyxl")
    # Normalize column headers (trim spaces)
    df.columns = [str(c).strip() for c in df.columns]

    # Check columns
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        msg = (
            "ERROR: Missing required column(s): "
            + ", ".join([f'{c} (expected in column {REQUIRED_COLUMNS[c]})' for c in missing])
            + "\nMake sure your Excel has these exact headers."
        )
        print(msg, file=sys.stderr)
        return 2

    # Filter by ID1 == 6610 (string comparison after strip)
    id_series = df["ID1"].astype(str).str.strip()
    df = df[id_series == "6610"].copy()

    # If nothing left after filtering, write empty output and exit gracefully
    if df.empty:
        out_df = pd.DataFrame(columns=["Entry"])
        out_df.to_excel(output_path, index=False, header=not no_header, engine="openpyxl")
        print("No rows with ID1 == 6610 were found. Wrote empty file.")
        return 0

    # Compose "Full Name - Email1 - Phone Number"
    combined = (
        df.apply(
            lambda r: f"{clean_cell(r['Full Name'])} - {clean_cell(r['Email1'])} - {clean_cell(r['Phone Number'])}",
            axis=1,
        )
        .astype(str)
    )

    # Tickets Purchased -> integer >= 0
    tickets = pd.to_numeric(df["Tickets Purchased"], errors="coerce").fillna(0).astype(int)
    tickets = tickets.clip(lower=0)

    # Repeat rows according to tickets
    repeated = combined.repeat(tickets)
    out_df = pd.DataFrame({"Entry": repeated.values})
    out_df.to_excel(output_path, index=False, header=not no_header, engine="openpyxl")

    print(f"Done. Entries written: {len(out_df)}")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Create raffle entries from an Excel file.")
    parser.add_argument("input", help="Path to input Excel (.xlsx)")
    parser.add_argument("-o", "--output", default="raffle_entries.xlsx", help="Path to output Excel (.xlsx)")
    parser.add_argument("--sheet", default=None, help="Worksheet name (default: first sheet)")
    parser.add_argument("--no-header", action="store_true", help="Write the output without a header row")
    args = parser.parse_args()

    try:
        code = build_raffle_entries(args.input, args.output, args.sheet, args.no_header)
    except FileNotFoundError:
        print(f"ERROR: File not found: {args.input}", file=sys.stderr)
        code = 2
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        code = 2
    sys.exit(code)


if __name__ == "__main__":
    main()
