"""
equipment.py

Equipment Master (EQ-01.csv)

- Machines are displayed in CSV row order (operator-defined)
- Filtered by line only (no sorting)
"""

import pandas as pd

from helpers import Color, menu_title
from file_utils import load_csv_strip, save_csv

EQ_FILE = "EQ-01.csv"

EQ_COLUMNS = [
    "Line",
    "MachineType/Name",
    "Machine Code",
    "Notes",
]


def load_equipment() -> pd.DataFrame:
    df = load_csv_strip(EQ_FILE, headers_default=EQ_COLUMNS)

    df["Line"] = df["Line"].astype(str).str.strip()
    df["MachineType/Name"] = df["MachineType/Name"].astype(str).str.strip()
    df["Machine Code"] = df["Machine Code"].astype(str).str.strip().str.upper()
    df["Notes"] = df["Notes"].astype(str).str.strip()

    # Remove empty machine rows only
    df = df[df["MachineType/Name"] != ""].reset_index(drop=True)
    return df


def save_equipment(df: pd.DataFrame) -> None:
    save_csv(df, EQ_FILE)


def list_machines_for_line(line: str) -> list[dict]:
    """
    Returns machines in CSV order for a given line.
    """
    df = load_equipment()
    line = str(line).strip()

    subset = df[df["Line"] == line]
    machines = []

    for _, r in subset.iterrows():
        machines.append(
            {
                "name": r["MachineType/Name"],
                "code": r["Machine Code"],
                "notes": r.get("Notes", ""),
            }
        )
    return machines


def select_machine_for_line(line: str) -> tuple[str, str]:
    machines = list_machines_for_line(line)

    if not machines:
        print(
            Color.RED
            + f"\nNo machines found for Line {line} in {EQ_FILE}.\n"
            + Color.RESET
        )
        return "", ""

    menu_title(f"Select Machine (Line {line})")

    for i, m in enumerate(machines, start=1):
        print(f"{i}) {m['name']} ({m['code']})")

    while True:
        choice = input("Choose machine number: ").strip()
        if not choice.isdigit():
            print(Color.RED + "Invalid selection.\n" + Color.RESET)
            continue

        idx = int(choice)
        if not (1 <= idx <= len(machines)):
            print(Color.RED + "Invalid selection.\n" + Color.RESET)
            continue

        sel = machines[idx - 1]
        return sel["name"], sel["code"]


def view_equipment() -> None:
    df = load_equipment()
    menu_title("Equipment Master (EQ-01)")

    if df.empty:
        print(Color.YELLOW + "\nNo equipment defined.\n" + Color.RESET)
        return

    for _, r in df.iterrows():
        line = r["Line"]
        name = r["MachineType/Name"]
        code = r["Machine Code"]
        notes = r["Notes"]

        if notes:
            print(f"Line {line} | {name} ({code}) — {notes}")
        else:
            print(f"Line {line} | {name} ({code})")

    print()