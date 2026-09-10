"""
line_runtime.py

Separate runtime log by Date + Line.
Keeps runtime and operational notes out of PROD-01.csv.
"""

from __future__ import annotations

from datetime import datetime
import pandas as pd

from helpers import Color, menu_title, parse_date_input
from file_utils import load_csv_strip, save_csv
from line_utils import choose_line as choose_configured_line, load_line_settings

LINE_RUNTIME_FILE = "LINE-RUN-01.csv"
LINE_SETTINGS_FILE = "LineSettings.csv"

LINE_RUNTIME_COLUMNS = [
    "Date",
    "Line",
    "HoursRan",
    "Notes",
    "EnteredBy",
    "LastUpdated",
]


def load_line_names() -> dict:
    try:
        df = load_csv_strip(LINE_SETTINGS_FILE)
        if {"Line", "LineName"}.issubset(df.columns):
            return {
                str(r["Line"]).strip(): str(r["LineName"]).strip()
                for _, r in df.iterrows()
                if str(r.get("LineName", "")).strip()
            }
    except Exception:
        pass
    return {}


def load_line_runtime() -> pd.DataFrame:
    df = load_csv_strip(LINE_RUNTIME_FILE, headers_default=LINE_RUNTIME_COLUMNS)
    for col in LINE_RUNTIME_COLUMNS:
        if col not in df.columns:
            df[col] = ""

    for col in ["Date", "Line", "Notes", "EnteredBy", "LastUpdated"]:
        df[col] = df[col].astype(str).fillna("").str.strip()
    df["HoursRan"] = pd.to_numeric(df["HoursRan"], errors="coerce").fillna(0.0)
    return df[LINE_RUNTIME_COLUMNS]


def save_line_runtime(df: pd.DataFrame) -> None:
    out = df.copy()
    for col in LINE_RUNTIME_COLUMNS:
        if col not in out.columns:
            out[col] = ""
    out = out[LINE_RUNTIME_COLUMNS]
    save_csv(out, LINE_RUNTIME_FILE)


def load_runtime_by_date_range(start_date: str, end_date: str) -> pd.DataFrame:
    df = load_line_runtime()
    if df.empty:
        return df
    df["_dt"] = pd.to_datetime(df["Date"], format="%m-%d-%Y", errors="coerce")
    s = pd.to_datetime(start_date, format="%m-%d-%Y", errors="coerce")
    e = pd.to_datetime(end_date, format="%m-%d-%Y", errors="coerce")
    df = df[(df["_dt"] >= s) & (df["_dt"] <= e)].copy()
    df.drop(columns=["_dt"], inplace=True, errors="ignore")
    return df


def get_runtime_record(date_str: str, line: str) -> dict | None:
    df = load_line_runtime()
    if df.empty:
        return None
    subset = df[
        (df["Date"].astype(str).str.strip() == str(date_str).strip())
        & (df["Line"].astype(str).str.strip() == str(line).strip())
    ]
    if subset.empty:
        return None
    return subset.iloc[0].to_dict()


def _last_updated_stamp() -> str:
    return datetime.now().strftime("%m-%d-%Y %H:%M")


def upsert_runtime(date_str: str, line: str, hours_ran: float, notes: str = "", entered_by: str = "UNKNOWN") -> None:
    df = load_line_runtime()
    mask = (
        (df["Date"].astype(str).str.strip() == str(date_str).strip())
        & (df["Line"].astype(str).str.strip() == str(line).strip())
    )

    payload = {
        "Date": str(date_str).strip(),
        "Line": str(line).strip(),
        "HoursRan": float(hours_ran),
        "Notes": str(notes or "").strip(),
        "EnteredBy": str(entered_by or "UNKNOWN").strip(),
        "LastUpdated": _last_updated_stamp(),
    }

    if mask.any():
        idx = df[mask].index[0]
        for k, v in payload.items():
            df.at[idx, k] = v
    else:
        df = pd.concat([df, pd.DataFrame([payload])], ignore_index=True)

    save_line_runtime(df)


def _choose_line() -> str:
    line = choose_configured_line()
    return line or ""


def _prompt_hours(existing: float | None = None) -> float | None:
    while True:
        label = "Hours ran"
        if existing is not None:
            label += f" [{existing:.2f}]"
        raw = input(label + " (blank to keep existing / skip new): ").strip()
        if raw == "":
            return existing
        try:
            val = float(raw)
            if val <= 0:
                print(Color.RED + "Hours must be greater than zero." + Color.RESET)
                continue
            return val
        except ValueError:
            print(Color.RED + "Enter a valid number, e.g. 2 or 5.5" + Color.RESET)


def ensure_runtime_for_line_date(date_str: str, line: str, entered_by: str = "UNKNOWN", prompt_if_exists: bool = True) -> None:
    line_names = load_line_names()
    label = line_names.get(str(line).strip(), "")
    line_header = f"Line {line}" + (f" – {label}" if label else "")

    existing = get_runtime_record(date_str, line)
    if existing and not prompt_if_exists:
        return

    menu_title(f"Line Runtime | {date_str} | {line_header}")

    if existing:
        hours = float(pd.to_numeric(existing.get("HoursRan", 0), errors="coerce") or 0)
        notes = str(existing.get("Notes", "")).strip()
        print(f"Existing runtime: {hours:.2f} hours")
        if notes:
            print(f"Existing notes  : {notes}")
        action = input("Keep existing runtime? (Y=keep / E=edit): ").strip().upper() or "Y"
        if action == "Y":
            return
        if action != "E":
            print(Color.YELLOW + "Keeping existing runtime unchanged.\n" + Color.RESET)
            return

        new_hours = _prompt_hours(existing=hours)
        if new_hours is None:
            new_hours = hours
        new_notes_raw = input("Runtime notes (blank keeps existing): ").strip()
        new_notes = new_notes_raw if new_notes_raw != "" else notes
        upsert_runtime(date_str, line, new_hours, new_notes, entered_by)
        print(Color.GREEN + "\n✔ Line runtime updated.\n" + Color.RESET)
        return

    print("No runtime record exists yet for this date + line.")
    hours = _prompt_hours(existing=None)
    if hours is None:
        print(Color.YELLOW + "Skipped runtime entry for now.\n" + Color.RESET)
        return
    notes = input("Runtime notes (optional): ").strip()
    upsert_runtime(date_str, line, hours, notes, entered_by)
    print(Color.GREEN + "\n✔ Line runtime saved.\n" + Color.RESET)


def view_all_runtime() -> None:
    df = load_line_runtime()
    menu_title("Line Runtime (All)")
    if df.empty:
        print(Color.YELLOW + "\nNo line runtime records.\n" + Color.RESET)
        return
    print(df.to_string(index=False))
    print()


def view_runtime_by_date_range() -> None:
    menu_title("Line Runtime (Date Range)")
    start_date = parse_date_input("Start date (MM-DD-YYYY): ")
    end_date = parse_date_input("End date (MM-DD-YYYY): ")

    df = load_runtime_by_date_range(start_date, end_date)
    if df.empty:
        print(Color.YELLOW + f"\nNo line runtime between {start_date} and {end_date}.\n" + Color.RESET)
        return

    print(df.to_string(index=False))
    print()


def record_or_edit_runtime() -> None:
    menu_title("Add / Edit Line Runtime")
    date_str = parse_date_input("Date (MM-DD-YYYY): ")
    line = _choose_line()
    entered_by = input("Entered by (initials/name): ").strip() or "UNKNOWN"
    ensure_runtime_for_line_date(date_str, line, entered_by=entered_by, prompt_if_exists=True)


def line_runtime_menu() -> None:
    while True:
        menu_title("Line Runtime (LINE-RUN-01)")
        print("1) Add / Edit Line Runtime")
        print("2) View All Runtime")
        print("3) View Runtime by Date Range")
        print("4) Back")

        choice = input("Choose: ").strip()
        if choice == "1":
            record_or_edit_runtime()
        elif choice == "2":
            view_all_runtime()
        elif choice == "3":
            view_runtime_by_date_range()
        elif choice == "4":
            break
        else:
            print(Color.RED + "Invalid choice.\n" + Color.RESET)
