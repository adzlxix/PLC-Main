"""
downtime.py

Downtime / Equipment Event Log (DT-01.csv)

Features:
- Operator-first input flow (date/start first, notes last)
- Machine-level OR line-level downtime
- 07:00–19:00 working-hours enforcement
- Automatic daily splitting (one row per day)
- ISO-safe, audit-friendly records
"""

from datetime import datetime, timedelta
import pandas as pd

from helpers import Color, menu_title, parse_date_input, confirm, numeric_input
from file_utils import load_csv_strip, save_csv
from line_utils import choose_line as choose_configured_line
import equipment

DT_FILE = "DT-01.csv"

DT_COLUMNS = [
    "Line",
    "MachineType/Name",
    "Machine Code",
    "Date",
    "Downtime Start",
    "Downtime End",
    "Downtime Minutes",
    "Downtime Category",
    "Issue",
    "Work Done",
    "Parts Used",
    "Tech Initials",
    "Notes",
]

OPEN_TIME = "07:00"
CLOSE_TIME = "19:00"

CATEGORIES = [
    "Mechanical",
    "Electrical",
    "Material Shortage",
    "Changeover",
    "Cleaning / Sanitation",
    "Quality Hold",
    "Staffing",
    "Planned Maintenance",
    "Other",
]


# -------------------------------------------------------------------
# Core helpers
# -------------------------------------------------------------------

def load_downtime() -> pd.DataFrame:
    df = load_csv_strip(DT_FILE, headers_default=DT_COLUMNS)
    df["Downtime Minutes"] = (
        pd.to_numeric(df.get("Downtime Minutes", 0), errors="coerce")
        .fillna(0)
        .astype(int)
    )
    return df


def save_downtime(df: pd.DataFrame) -> None:
    save_csv(df, DT_FILE)


def _parse_time(hhmm: str) -> datetime:
    return datetime.strptime(hhmm, "%H:%M")


def _minutes_between(start: str, end: str) -> int:
    return max(int((_parse_time(end) - _parse_time(start)).total_seconds() // 60), 0)


def _clamp_to_work_hours(start: str, end: str):
    notes = []
    s, e = _parse_time(start), _parse_time(end)
    o, c = _parse_time(OPEN_TIME), _parse_time(CLOSE_TIME)

    if s < o:
        notes.append(f"Started before hours at {start}")
        s = o
    if s > c:
        s = c

    if e > c:
        notes.append(f"Ended after hours at {end}")
        e = c
    if e < o:
        e = o

    return s.strftime("%H:%M"), e.strftime("%H:%M"), notes


def _next_day(date_str: str) -> str:
    return (datetime.strptime(date_str, "%m-%d-%Y") + timedelta(days=1)).strftime("%m-%d-%Y")


# -------------------------------------------------------------------
# Record downtime
# -------------------------------------------------------------------

def record_downtime_event() -> None:
    menu_title("Record Downtime Event")

    # Line
    line = choose_configured_line()
    if not line:
        print(Color.YELLOW + "Downtime entry cancelled.\n" + Color.RESET)
        return

    # Date & start FIRST
    date_str = parse_date_input("Date (MM-DD-YYYY): ")
    start_raw = input("Downtime Start (HH:MM): ").strip()

    # Category
    menu_title("Downtime Category")
    for i, c in enumerate(CATEGORIES, 1):
        print(f"{i}) {c}")

    cat = CATEGORIES[int(input("Choose: ")) - 1]
    other_detail = ""
    if cat == "Other":
        other_detail = input("Specify Other: ").strip()

    # Machine or line-level
    if confirm("Is this associated with a machine?"):
        machine_name, machine_code = equipment.select_machine_for_line(line)
        if not machine_name:
            return
    else:
        machine_name, machine_code = "LINE-LEVEL", "N/A"

    # Technical details BEFORE end time
    issue = input("Issue (what happened): ").strip()
    work_done = input("Work Done (optional): ").strip()
    parts_used = input("Parts Used (optional): ").strip()
    tech_initials = input("Tech Initials (optional): ").strip().upper()

    df = load_downtime()

    current_date = date_str
    current_start = start_raw
    continued = False

    while True:
        end_raw = input("Downtime End (HH:MM) [ENTER if unresolved]: ").strip()
        unresolved = end_raw == ""

        if unresolved:
            end_raw = CLOSE_TIME

        start_c, end_c, clamp_notes = _clamp_to_work_hours(current_start, end_raw)
        minutes = _minutes_between(start_c, end_c)

        print(Color.CYAN + f"\nCalculated downtime (working hours only): {minutes} minutes\n" + Color.RESET)
        if not confirm("Use this value?"):
            minutes = int(numeric_input("Enter minutes: ", allow_float=False))

        # Notes LAST (per day)
        notes = input("Notes (optional): ").strip()

        if continued:
            notes = f"Continued from previous day | {notes}".strip(" |")

        for n in clamp_notes:
            notes = f"{notes} | {n}".strip(" |")

        if cat == "Other" and other_detail:
            notes = f"{notes} | OtherCategory: {other_detail}".strip(" |")

        row = {
            "Line": line,
            "MachineType/Name": machine_name,
            "Machine Code": machine_code,
            "Date": current_date,
            "Downtime Start": start_c,
            "Downtime End": end_c,
            "Downtime Minutes": minutes,
            "Downtime Category": cat,
            "Issue": issue,
            "Work Done": work_done,
            "Parts Used": parts_used,
            "Tech Initials": tech_initials,
            "Notes": notes,
        }

        df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
        save_downtime(df)

        print(Color.GREEN + f"✔ Saved downtime for {current_date}\n" + Color.RESET)

        if unresolved and confirm("Continue into next working day?"):
            current_date = _next_day(current_date)
            current_start = OPEN_TIME
            continued = True
            continue

        break


# -------------------------------------------------------------------
# View functions (RESTORED & STABLE)
# -------------------------------------------------------------------

def view_all_downtime() -> None:
    menu_title("Downtime Log (All)")
    df = load_downtime()

    if df.empty:
        print(Color.YELLOW + "\nNo downtime entries.\n" + Color.RESET)
        return

    df["_dt"] = pd.to_datetime(df["Date"], format="%m-%d-%Y", errors="coerce")
    df = df.sort_values(by=["_dt", "Line"]).drop(columns=["_dt"])

    for _, r in df.iterrows():
        print(
            f"{r['Date']} | Line {r['Line']} | "
            f"{int(r['Downtime Minutes'])} min | "
            f"{r['Downtime Category']} | "
            f"{r['MachineType/Name']} ({r['Machine Code']}) | "
            f"{r['Issue']}"
        )
    print()


def view_downtime_by_date_range() -> None:
    menu_title("Downtime by Date Range")

    start_date = parse_date_input("Start Date (MM-DD-YYYY): ")
    end_date = parse_date_input("End Date (MM-DD-YYYY): ")

    df = load_downtime()
    if df.empty:
        print(Color.YELLOW + "\nNo downtime entries.\n" + Color.RESET)
        return

    df["_dt"] = pd.to_datetime(df["Date"], format="%m-%d-%Y", errors="coerce")
    s = pd.to_datetime(start_date, format="%m-%d-%Y", errors="coerce")
    e = pd.to_datetime(end_date, format="%m-%d-%Y", errors="coerce")

    subset = df[(df["_dt"] >= s) & (df["_dt"] <= e)].drop(columns=["_dt"])

    if subset.empty:
        print(Color.YELLOW + "\nNo downtime in this range.\n" + Color.RESET)
        return

    for _, r in subset.iterrows():
        print(
            f"{r['Date']} | Line {r['Line']} | "
            f"{int(r['Downtime Minutes'])} min | "
            f"{r['Downtime Category']} | "
            f"{r['MachineType/Name']} ({r['Machine Code']}) | "
            f"{r['Issue']}"
        )
    print()


# -------------------------------------------------------------------
# Menu (REQUIRED by main.py)
# -------------------------------------------------------------------

def downtime_menu() -> None:
    while True:
        menu_title("Downtime / Equipment Log")
        print("1) Record Downtime Event")
        print("2) View Downtime Log (All)")
        print("3) View Downtime by Date Range")
        print("4) View Equipment Master (EQ-01)")
        print("5) Back")

        choice = input("Choose: ").strip()

        if choice == "1":
            record_downtime_event()
        elif choice == "2":
            view_all_downtime()
        elif choice == "3":
            view_downtime_by_date_range()
        elif choice == "4":
            equipment.view_equipment()
        elif choice == "5":
            break
        else:
            print(Color.RED + "Invalid choice.\n" + Color.RESET)