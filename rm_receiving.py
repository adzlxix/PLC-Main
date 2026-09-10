"""
rm_receiving.py

RM-01 — Raw Material Receiving
- Records incoming raw materials (append-only)
- Accepted receipts rebuild RM-BAL-01.csv
- RM-01 remains the receipt log; RM-BAL-01 is the live on-hand file
- ISO-safe (append-only)
"""

import csv
import os
from datetime import datetime

from helpers import Color, menu_title
from file_utils import append_csv_row_safe
from raw_materials import (
    record_raw_material_receipt,
    rebuild_rm_balance_from_logs,
    view_rm_balance,
    view_rm_usage_log,
    load_rm_balance,
)

RM_FILE = "RM-01.csv"
CATEGORY_FILE = "RM_MaterialCategories.csv"
STATE_FILE = "RM_MaterialStates.csv"
CONTAINER_FILE = "RM_ContainerTypes.csv"


def load_list(filename, column):
    if not os.path.exists(filename):
        return []
    with open(filename, newline="", encoding="utf-8") as f:
        return [row[column].strip() for row in csv.DictReader(f) if row.get(column, "").strip()]


def generate_rm_id():
    if not os.path.exists(RM_FILE):
        return "RM-00001"
    with open(RM_FILE, newline="", encoding="utf-8") as f:
        ids = [row["RM_ID"] for row in csv.DictReader(f) if row.get("RM_ID")]
    if not ids:
        return "RM-00001"
    last = max(int(i.split("-")[1]) for i in ids)
    return f"RM-{last + 1:05d}"


def choose_from_list(prompt, options):
    if not options:
        return ""
    for i, opt in enumerate(options, 1):
        print(f"{i}) {opt}")
    while True:
        choice = input(f"{prompt}: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(options):
            return options[int(choice) - 1]
        print(Color.RED + "Invalid selection." + Color.RESET)




def _load_known_materials():
    known = {}

    bal = load_rm_balance(rebuild_if_missing=True)
    if not bal.empty:
        for _, row in bal.iterrows():
            name = str(row.get("Material", "")).strip()
            code = str(row.get("MaterialCode", "")).strip().upper()
            if name:
                known[name.lower()] = (name, code)

    if os.path.exists(RM_FILE):
        with open(RM_FILE, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                name = str(row.get("Material Name", "")).strip()
                code = str(row.get("Material Code", "")).strip().upper()
                if name and name.lower() not in known:
                    known[name.lower()] = (name, code)

    return sorted(known.values(), key=lambda x: x[0].lower())


def search_select_material():
    """Search materials by name and return (material_name, material_code).

    Uses known materials from RM-BAL-01 and RM-01 history.
    Allows manual creation only when no suitable existing match is found.
    """
    materials = _load_known_materials()

    while True:
        query = input("Search material name (blank=manual entry): ").strip()
        if not query:
            material_name = input("New Material Name: ").strip()
            material_code = input("Material Code (auto-uppercase): ").strip().upper()
            return material_name, material_code

        q = query.lower()
        matches = [m for m in materials if q in m[0].lower() or q in m[1].lower()]

        if not matches:
            print(Color.YELLOW + "No matches found." + Color.RESET)
            if input("Create a new material manually? (Y/N): ").strip().lower() == "y":
                material_name = input("New Material Name: ").strip()
                material_code = input("Material Code (auto-uppercase): ").strip().upper()
                return material_name, material_code
            continue

        print("\nMatches:")
        for i, (name, code) in enumerate(matches[:25], 1):
            code_disp = f" [{code}]" if code else ""
            print(f"  {i}) {name}{code_disp}")
        print("  0) Search again")

        choice = input("Choose material number: ").strip()
        if choice == "0":
            continue
        if choice.isdigit() and 1 <= int(choice) <= min(len(matches), 25):
            name, code = matches[int(choice) - 1]
            return name, code
        print(Color.RED + "Invalid choice." + Color.RESET)

def record_rm_receiving():
    menu_title("Receive Raw Material (RM-01)")

    rm_id = generate_rm_id()
    print(f"RM ID: {rm_id}\n")

    date = input("Date (MM-DD-YYYY) [ENTER for today]: ").strip() or datetime.today().strftime("%m-%d-%Y")
    supplier = input("Supplier: ").strip()
    material_name, material_code = search_select_material()
    print(f"Selected Material: {material_name} [{material_code}]" if material_code else f"Selected Material: {material_name}")

    categories = load_list(CATEGORY_FILE, "Category")
    states = load_list(STATE_FILE, "State")
    containers = load_list(CONTAINER_FILE, "ContainerType")

    material_category = choose_from_list("Select Material Category", categories)
    material_state = choose_from_list("Select Material State", states)
    container_type = choose_from_list("Select Container Type", containers)

    quantity = input("Quantity: ").strip()
    unit = input("Unit (free text): ").strip()
    lot = input("Lot / Batch (optional): ").strip()
    po = input("PO / BOL # (optional): ").strip()
    received_by = input("Received By: ").strip()

    print("\nInspection Status:")
    print("1) Accepted")
    print("2) Quarantined")
    print("3) Rejected")

    while True:
        insp = input("Choose: ").strip()
        if insp == "1":
            inspection = "Accepted"
            break
        if insp == "2":
            inspection = "Quarantined"
            break
        if insp == "3":
            inspection = "Rejected"
            break
        print(Color.RED + "Invalid choice." + Color.RESET)

    notes = input("Notes (optional): ").strip()

    print("\n--- Confirm RM-01 Entry ---")
    print(f"Material: {material_name}")
    print(f"Category: {material_category}")
    print(f"State: {material_state}")
    print(f"Container: {container_type}")
    print(f"Quantity: {quantity} {unit}")
    print(f"Inspection: {inspection}")

    if input("\nProceed? (Y/N): ").strip().lower() != "y":
        print(Color.YELLOW + "\nRM-01 entry cancelled.\n" + Color.RESET)
        return

    rm_headers = [
        "RM_ID", "Date", "Supplier", "Material Name", "Material Code",
        "Material Category", "Material State", "Container Type",
        "Quantity", "Unit", "Lot / Batch", "PO / BOL #",
        "Inspection Status", "Received By", "Notes"
    ]
    append_csv_row_safe(
        RM_FILE,
        {
            "RM_ID": rm_id,
            "Date": date,
            "Supplier": supplier,
            "Material Name": material_name,
            "Material Code": material_code,
            "Material Category": material_category,
            "Material State": material_state,
            "Container Type": container_type,
            "Quantity": quantity,
            "Unit": unit,
            "Lot / Batch": lot,
            "PO / BOL #": po,
            "Inspection Status": inspection,
            "Received By": received_by,
            "Notes": notes,
        },
        rm_headers,
    )

    if inspection == "Accepted":
        record_raw_material_receipt(
            material=material_name,
            material_code=material_code,
            quantity=float(quantity),
            unit=unit,
            business_date=date,
            notes=notes or f"Received via RM-01 ({rm_id})",
        )

    print(Color.GREEN + "\n✔ RM-01 entry recorded successfully.\n" + Color.RESET)


def view_rm_log():
    if not os.path.exists(RM_FILE):
        print(Color.YELLOW + "\nNo RM-01 records found.\n" + Color.RESET)
        return
    with open(RM_FILE, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    if not rows:
        print(Color.YELLOW + "\nNo RM-01 records found.\n" + Color.RESET)
        return

    menu_title("RM-01 — Raw Material Receiving Log")
    headers = reader.fieldnames
    print(" | ".join(headers))
    print("-" * 140)
    for row in rows:
        print(" | ".join(row.get(h, "") for h in headers))
    print()


def rebuild_rm_balance():
    return rebuild_rm_balance_from_logs()
