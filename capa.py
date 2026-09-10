"""
capa.py

CAPA – Corrective and Preventive Actions (CAPA-01.csv)

Goals:
- Simple, ISO-friendly CAPA tracking
- Optional linkage to DT-01 (downtime) and PROD-01 (production)
- Controlled status + triggers
- Append-only creation + controlled editing (status/review fields)

CSV: CAPA-01.csv
"""

from __future__ import annotations

from datetime import datetime
import pandas as pd

from helpers import Color, menu_title, parse_date_input, confirm
from file_utils import load_csv_strip, save_csv
from line_utils import choose_line as choose_configured_line

CAPA_FILE = "CAPA-01.csv"

CAPA_COLUMNS = [
    "CAPA ID",
    "Date Opened",
    "Trigger Type",      # Downtime / Production / Quality / Safety / Other
    "Reference Type",    # DT-01 / PROD-01 / INV / N/A
    "Reference ID",      # e.g., date|line|machine or ProductionID etc.
    "Issue Description",
    "Root Cause",
    "Corrective Action",
    "Preventive Action",
    "Owner",
    "Status",            # Open / In Progress / Closed
    "Review Date",
    "Effectiveness Check",
    "Date Closed",
    "Notes",
]

TRIGGER_TYPES = ["Downtime", "Production", "Quality", "Safety", "Other"]
STATUS_VALUES = ["Open", "In Progress", "Closed"]


def load_capa() -> pd.DataFrame:
    df = load_csv_strip(CAPA_FILE, headers_default=CAPA_COLUMNS)

    # Normalize columns (safe if empty)
    for c in CAPA_COLUMNS:
        if c not in df.columns:
            df[c] = ""

    df["CAPA ID"] = df["CAPA ID"].astype(str).str.strip()
    df["Status"] = df["Status"].astype(str).str.strip()
    return df


def save_capa(df: pd.DataFrame) -> None:
    save_csv(df, CAPA_FILE)


def _next_capa_id(df: pd.DataFrame) -> str:
    """
    Generates CAPA-001 style IDs.
    """
    if df.empty or df["CAPA ID"].dropna().empty:
        return "CAPA-001"

    ids = df["CAPA ID"].astype(str).str.extract(r"CAPA-(\d+)")
    nums = pd.to_numeric(ids[0], errors="coerce").dropna()
    n = int(nums.max()) + 1 if not nums.empty else 1
    return f"CAPA-{n:03d}"


def _choose_from_list(title: str, options: list[str]) -> str:
    menu_title(title)
    for i, opt in enumerate(options, 1):
        print(f"{i}) {opt}")
    while True:
        choice = input("Choose: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(options):
            return options[int(choice) - 1]
        print(Color.RED + "Invalid choice.\n" + Color.RESET)


def _link_reference() -> tuple[str, str, str]:
    """
    Returns (trigger_type, reference_type, reference_id)
    Keeps linking simple & audit-friendly.
    """
    trigger = _choose_from_list("CAPA Trigger Type", TRIGGER_TYPES)

    if trigger == "Downtime":
        # Link to DT-01 by a human-readable key (date + line + machine)
        ref_type = "DT-01"
        date = parse_date_input("Downtime Date (MM-DD-YYYY): ")
        line = choose_configured_line() or ""
        machine = input("Machine name/code (free text): ").strip()
        ref_id = f"{date} | Line {line} | {machine}".strip()
        return trigger, ref_type, ref_id

    if trigger == "Production":
        ref_type = "PROD-01"
        prod_id = input("ProductionID (e.g., PROD4-ATGP50-25344): ").strip()
        if not prod_id:
            # fallback if they don't know it
            date = parse_date_input("Production Date (MM-DD-YYYY): ")
            line = choose_configured_line() or ""
            product = input("Finished Product (free text): ").strip()
            prod_id = f"{date} | Line {line} | {product}".strip()
        return trigger, ref_type, prod_id

    # Quality/Safety/Other may not map to a system record
    ref_type = "N/A"
    ref_id = ""
    if confirm("Link this CAPA to a specific reference anyway?"):
        ref_type = input("Reference Type (e.g., INV, DT-01, PROD-01): ").strip() or "N/A"
        ref_id = input("Reference ID (free text): ").strip()
    return trigger, ref_type, ref_id


def add_capa() -> None:
    df = load_capa()

    menu_title("Open New CAPA")

    capa_id = _next_capa_id(df)
    date_opened = parse_date_input("Date Opened (MM-DD-YYYY): ")

    trigger_type, ref_type, ref_id = _link_reference()

    issue = input("Issue Description (required): ").strip()
    if not issue:
        print(Color.RED + "Issue Description cannot be empty.\n" + Color.RESET)
        return

    root_cause = input("Root Cause (optional now, required before closing): ").strip()
    corr_action = input("Corrective Action (optional now): ").strip()
    prev_action = input("Preventive Action (optional now): ").strip()
    owner = input("Owner (name/initials): ").strip()

    status = "Open"
    review_date = input("Review Date (MM-DD-YYYY) [optional]: ").strip()
    notes = input("Notes (optional): ").strip()

    new_row = {
        "CAPA ID": capa_id,
        "Date Opened": date_opened,
        "Trigger Type": trigger_type,
        "Reference Type": ref_type,
        "Reference ID": ref_id,
        "Issue Description": issue,
        "Root Cause": root_cause,
        "Corrective Action": corr_action,
        "Preventive Action": prev_action,
        "Owner": owner,
        "Status": status,
        "Review Date": review_date,
        "Effectiveness Check": "",
        "Date Closed": "",
        "Notes": notes,
    }

    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    save_capa(df)

    print(Color.GREEN + f"\n✔ CAPA opened: {capa_id}\n" + Color.RESET)


def _list_capa(df: pd.DataFrame) -> None:
    if df.empty:
        print(Color.YELLOW + "\nNo CAPAs found.\n" + Color.RESET)
        return

    show = df.copy()
    # Friendly columns in terminal
    cols = ["CAPA ID", "Status", "Owner", "Trigger Type", "Reference Type", "Reference ID", "Issue Description", "Date Opened"]
    cols = [c for c in cols if c in show.columns]
    print(show[cols].to_string(index=False))
    print()


def view_all_capa() -> None:
    menu_title("CAPA Log (All)")
    df = load_capa()
    _list_capa(df)


def view_open_capa() -> None:
    menu_title("Open CAPAs")
    df = load_capa()
    df = df[df["Status"].astype(str).str.strip().isin(["Open", "In Progress"])]
    _list_capa(df)


def update_capa_status() -> None:
    """
    Controlled edit: update status, review/effectiveness, close date.
    Keeps ISO integrity: you’re not rewriting history, just progressing actions.
    """
    df = load_capa()
    if df.empty:
        print(Color.YELLOW + "\nNo CAPAs available.\n" + Color.RESET)
        return

    menu_title("Update CAPA Status")
    _list_capa(df)

    capa_id = input("Enter CAPA ID to update (e.g., CAPA-003): ").strip()
    if not capa_id:
        return

    mask = df["CAPA ID"].astype(str).str.strip() == capa_id
    if not mask.any():
        print(Color.RED + "CAPA ID not found.\n" + Color.RESET)
        return

    new_status = _choose_from_list("Set Status", STATUS_VALUES)
    df.loc[mask, "Status"] = new_status

    # Encourage ISO completeness before closing
    if new_status == "Closed":
        if not str(df.loc[mask, "Root Cause"].values[0]).strip():
            print(Color.YELLOW + "Warning: Root Cause is empty. ISO usually expects this before closure." + Color.RESET)

        if not str(df.loc[mask, "Corrective Action"].values[0]).strip():
            print(Color.YELLOW + "Warning: Corrective Action is empty. ISO usually expects this before closure." + Color.RESET)

        close_date = parse_date_input("Date Closed (MM-DD-YYYY): ")
        df.loc[mask, "Date Closed"] = close_date

    # Review & effectiveness (optional but recommended)
    review = input("Review Date (MM-DD-YYYY) [optional]: ").strip()
    if review:
        df.loc[mask, "Review Date"] = review

    eff = input("Effectiveness Check (what proves it worked?) [optional]: ").strip()
    if eff:
        df.loc[mask, "Effectiveness Check"] = eff

    note = input("Add Note (optional): ").strip()
    if note:
        prev = str(df.loc[mask, "Notes"].values[0]).strip()
        df.loc[mask, "Notes"] = f"{prev} | {note}".strip(" |")

    save_capa(df)
    print(Color.GREEN + f"\n✔ Updated {capa_id}\n" + Color.RESET)


def capa_menu() -> None:
    while True:
        menu_title("CAPA / Corrective Actions")
        print("1) Open New CAPA")
        print("2) View CAPA Log (All)")
        print("3) View Open CAPAs Only")
        print("4) Update CAPA Status / Close CAPA")
        print("5) Back")

        choice = input("Choose: ").strip()

        if choice == "1":
            add_capa()
        elif choice == "2":
            view_all_capa()
        elif choice == "3":
            view_open_capa()
        elif choice == "4":
            update_capa_status()
        elif choice == "5":
            break
        else:
            print(Color.RED + "Invalid choice.\n" + Color.RESET)