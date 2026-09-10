"""
receiving.py

Handles:
- RM-01 (Raw Material Receiving)
- RCV-01 (Inventory Receiving / Adjustment)
"""

import pandas as pd

from file_utils import load_csv_strip, save_csv
from helpers import Color, menu_title, parse_date_input, numeric_input, confirm
from inventory import adjust_inventory_quantity, select_component_from_inventory
import rm_receiving

RECEIVING_FILE = "RCV-01.csv"

RECEIVING_COLUMNS = [
    "Date Received",
    "Supplier",
    "Component",
    "Component Code",
    "Units Received",
    "Unit Type",
    "Batch #",
    "Condition on Arrival",
    "Accepted (Y/N)",
    "Rejected Qty",
    "Storage Location",
    "PO / Ref #",
    "Receiver Initials",
    "Notes",
]


def load_receiving():
    df = load_csv_strip(RECEIVING_FILE, headers_default=RECEIVING_COLUMNS)
    for col in ("Units Received", "Rejected Qty"):
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    return df


def record_receipt():
    menu_title("Receive / Adjust Inventory (RCV-01)")

    date_received = parse_date_input("Date Received (MM-DD-YYYY):")
    supplier = input("Supplier: ").strip()

    sel = select_component_from_inventory()
    if not sel:
        return

    component = sel["Component"]
    comp_code = sel.get("ComponentCode", "")

    print(f"\nComponent: {component}")
    print(f"Code: {comp_code}")

    if not confirm("Is this correct?"):
        print(Color.YELLOW + "Cancelled.\n" + Color.RESET)
        return

    units_received = numeric_input("Units Received: ", allow_float=False)
    unit_type = input("Unit Type: ").strip()
    batch_no = input("Batch #: ").strip()
    condition = input("Condition on Arrival: ").strip()
    accepted_flag = input("Accepted (Y/N): ").strip()
    rejected_qty = numeric_input("Rejected Qty: ", allow_float=False)
    storage = input("Storage Location: ").strip()
    po_ref = input("PO / Ref #: ").strip()
    initials = input("Receiver Initials: ").strip()
    notes = input("Notes: ").strip()

    accepted = accepted_flag.lower().startswith("y")
    net_accepted = max(units_received - rejected_qty, 0)

    df = load_receiving()
    df = pd.concat([df, pd.DataFrame([{
        "Date Received": date_received,
        "Supplier": supplier,
        "Component": component,
        "Component Code": comp_code,
        "Units Received": units_received,
        "Unit Type": unit_type,
        "Batch #": batch_no,
        "Condition on Arrival": condition,
        "Accepted (Y/N)": accepted_flag,
        "Rejected Qty": rejected_qty,
        "Storage Location": storage,
        "PO / Ref #": po_ref,
        "Receiver Initials": initials,
        "Notes": notes,
    }])], ignore_index=True)

    save_csv(df, RECEIVING_FILE)

    if accepted and net_accepted > 0:
        new_qty = adjust_inventory_quantity(
            component=component,
            delta=net_accepted,
            change_type="RCV-01",
            reference=f"Supplier={supplier}, Batch={batch_no}",
            notes=notes,
            date_received=date_received,
        )
        print(Color.GREEN + f"\n✔ Inventory updated. New quantity: {new_qty:.2f}\n" + Color.RESET)
    else:
        print(Color.YELLOW + "\nNo inventory update performed.\n" + Color.RESET)


def view_receiving_log():
    df = load_receiving()
    if df.empty:
        print(Color.YELLOW + "\nNo receiving entries yet.\n" + Color.RESET)
        return

    menu_title("Receiving Log (RCV-01)")
    print(df.to_string(index=False))
    print()


def receiving_menu():
    while True:
        menu_title("Receiving")
        print("1) Receive Raw Material (RM-01)")
        print("2) View RM-01 Log")
        print("3) View RM-BAL-01 (Current Raw On-Hand)")
        print("4) View RM-01-Usage Log")
        print("5) Rebuild RM-BAL-01 from Logs")
        print("6) Receive / Adjust Inventory (RCV-01)")
        print("7) View Receiving Log (RCV-01)")
        print("8) Back")

        choice = input("Choose: ").strip()

        if choice == "1":
            rm_receiving.record_rm_receiving()
        elif choice == "2":
            rm_receiving.view_rm_log()
        elif choice == "3":
            rm_receiving.view_rm_balance()
        elif choice == "4":
            rm_receiving.view_rm_usage_log()
        elif choice == "5":
            rm_receiving.rebuild_rm_balance()
            print(Color.GREEN + "\n✔ RM-BAL-01 rebuilt from RM-01 and RM-01-Usage.\n" + Color.RESET)
        elif choice == "6":
            record_receipt()
        elif choice == "7":
            view_receiving_log()
        elif choice == "8":
            break
        else:
            print(Color.RED + "Invalid choice.\n" + Color.RESET)
