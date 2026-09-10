"""
inventory.py

Manages:
- INV-01.csv (current inventory)
- INV-01-History.csv (audit log of changes)
"""

from datetime import datetime
from typing import Optional


import pandas as pd

from file_utils import load_csv_strip, save_csv
from helpers import Color, menu_title, numeric_input, confirm, parse_date_input
import inventory_status

INVENTORY_FILE = "INV-01.csv"
INVENTORY_HISTORY_FILE = "INV-01-History.csv"

INVENTORY_COLUMNS = [
    "Component",
    "ComponentCode",
    "ComponentType",
    "Quantity",
    "DateReceived",
    "Notes",
    "LeadTimeDays",
    "MaxCapacity",
    "SafetyFactor",
]

INVENTORY_HISTORY_COLUMNS = [
    "Timestamp",
    "Component",
    "ComponentCode",
    "ChangeType",
    "DeltaQty",
    "NewQty",
    "Reference",
    "Notes",
]


# ------------------------------------------------------------------
# Loaders
# ------------------------------------------------------------------
def pretty_print_inventory(inv):
    """
    Read-only formatted inventory view
    """
    inv = inv.sort_values(by=["Component"])
    
    print(f"{'Component':30} {'Code':15} {'Type':15} {'Qty':>10}")
    print("-" * 75)

    for _, r in inv.iterrows():
        print(
            f"{r['Component'][:30]:30} "
            f"{r['ComponentCode'][:15]:15} "
            f"{r['ComponentType'][:15]:15} "
            f"{float(r['Quantity']):>10.2f}"
        )

def _ensure_inventory() -> pd.DataFrame:
    df = load_csv_strip(INVENTORY_FILE, headers_default=INVENTORY_COLUMNS)

    for col, default in [
        ("Quantity", 0.0),
        ("LeadTimeDays", 14.0),
        ("MaxCapacity", 0.0),
        ("SafetyFactor", 1.10),
    ]:
        df[col] = pd.to_numeric(df.get(col, default), errors="coerce").fillna(default)

    return df


def _ensure_history() -> pd.DataFrame:
    return load_csv_strip(
        INVENTORY_HISTORY_FILE, headers_default=INVENTORY_HISTORY_COLUMNS
    )


def load_inventory() -> pd.DataFrame:
    return _ensure_inventory()


def load_inventory_history() -> pd.DataFrame:
    return _ensure_history()


# ------------------------------------------------------------------
# Inventory creation (ONLY via Kits)
# ------------------------------------------------------------------

def add_or_update_inventory_component(
    component: str,
    component_code: str,
    component_type: str,
    lead_time_days: float = 14.0,
    max_capacity: float = 0.0,
    safety_factor: float = 1.10,
) -> None:
    component = str(component).strip()
    component_code = str(component_code).strip().upper()
    component_type = str(component_type).strip().lower()

    if not component:
        raise ValueError("Component name cannot be empty.")
    if not component_code:
        raise ValueError("ComponentCode cannot be empty.")
    if not component_type:
        raise ValueError("ComponentType cannot be empty.")

    inv = _ensure_inventory()
    mask = inv["Component"].astype(str).str.lower() == component.lower()

    if mask.any():
        idx = inv[mask].index[0]
        inv.at[idx, "ComponentCode"] = component_code
        inv.at[idx, "ComponentType"] = component_type
    else:
        new_row = {
            "Component": component,
            "ComponentCode": component_code,
            "ComponentType": component_type,
            "Quantity": 0.0,
            "DateReceived": "",
            "Notes": "",
            "LeadTimeDays": float(lead_time_days),
            "MaxCapacity": float(max_capacity),
            "SafetyFactor": float(safety_factor),
        }
        inv = pd.concat([inv, pd.DataFrame([new_row])], ignore_index=True)

    save_csv(inv, INVENTORY_FILE)


def component_exists(component: str) -> bool:
    component = str(component).strip()
    if not component:
        return False
    inv = _ensure_inventory()
    return component.lower() in inv["Component"].astype(str).str.lower().tolist()


# ------------------------------------------------------------------
# Quantity adjustment (core engine)
# ------------------------------------------------------------------

def adjust_inventory_quantity(
    component: str,
    delta: float,
    change_type: str,
    reference: str = "",
    notes: str = "",
    date_received: Optional[str] = None,
) -> float:
    component = str(component).strip()
    if not component:
        raise ValueError("Component name cannot be empty.")

    inv = _ensure_inventory()
    mask = inv["Component"].astype(str).str.lower() == component.lower()

    if not mask.any():
        raise ValueError(
            f"Component '{component}' does not exist in inventory. "
            f"Create it via Add Product first."
        )

    if date_received is None:
        date_received = datetime.now().strftime("%m-%d-%Y")

    current_qty = float(inv.loc[mask, "Quantity"].iloc[0])
    new_qty = current_qty + float(delta)

    inv.loc[mask, "Quantity"] = new_qty
    if delta > 0:
        inv.loc[mask, "DateReceived"] = str(date_received)
    if notes:
        inv.loc[mask, "Notes"] = str(notes)

    save_csv(inv, INVENTORY_FILE)

    hist = _ensure_history()
    comp_code = inv.loc[mask, "ComponentCode"].astype(str).iloc[0]
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    entry = {
        "Timestamp": timestamp,
        "Component": component,
        "ComponentCode": comp_code,
        "ChangeType": change_type,
        "DeltaQty": float(delta),
        "NewQty": float(new_qty),
        "Reference": reference,
        "Notes": notes,
    }

    hist = pd.concat([hist, pd.DataFrame([entry])], ignore_index=True)
    save_csv(hist, INVENTORY_HISTORY_FILE)

    return new_qty


# ------------------------------------------------------------------
# Inventory selector (reusable)
# ------------------------------------------------------------------

def select_component_from_inventory() -> Optional[dict]:
    inv = _ensure_inventory()
    if inv.empty:
        print(Color.YELLOW + "\nInventory is empty.\n" + Color.RESET)
        return None

    query = input("Search component (ENTER to list all): ").strip().lower()
    view = inv.copy()
    view["Component"] = view["Component"].astype(str)

    if query:
        view = view[view["Component"].str.lower().str.contains(query, na=False)]

    if view.empty:
        print(Color.YELLOW + "No matching components.\n" + Color.RESET)
        return None

    view = view.reset_index(drop=True)

    menu_title("Select Component")
    for i, row in view.iterrows():
        print(
            f"{i + 1}) {row['Component']} "
            f"(Code={row['ComponentCode']}, Qty={row['Quantity']:.2f})"
        )

    choice = input("Choose number (or ENTER to cancel): ").strip()
    if not choice:
        return None
    if not choice.isdigit():
        print(Color.RED + "Invalid selection." + Color.RESET)
        return None

    idx = int(choice) - 1
    if idx < 0 or idx >= len(view):
        print(Color.RED + "Selection out of range." + Color.RESET)
        return None

    row = view.iloc[idx]
    return {
        "Component": str(row["Component"]),
        "ComponentCode": str(row["ComponentCode"]),
        "Quantity": float(row["Quantity"]),
    }



# ------------------------------------------------------------------
# Set Count / Stocktake
# ------------------------------------------------------------------

def set_inventory_component_count() -> None:
    """
    Set a component/raw material to an exact physical count.
    This creates a delta adjustment behind the scenes and logs history.
    Use this for month-end counts, go-live counts, or corrections.
    """
    sel = select_component_from_inventory()
    if not sel:
        return

    component = sel["Component"]
    comp_code = sel["ComponentCode"]
    current_qty = float(sel["Quantity"])

    menu_title("Set Inventory Count / Stocktake")
    print(f"Component: {component}")
    print(f"Code: {comp_code}")
    print(f"Current system quantity: {current_qty:g}\n")

    count_date = parse_date_input("Count Date (MM-DD-YYYY):")
    actual = numeric_input("Actual physical count:", allow_float=True)
    notes = input("Notes (optional): ").strip() or "Stocktake set count"

    delta = float(actual) - current_qty
    print("\nSummary:")
    print(f"  Current system qty: {current_qty:g}")
    print(f"  Actual count: {actual:g}")
    print(f"  Adjustment needed: {delta:g}")
    if not confirm("Confirm set count?"):
        print(Color.YELLOW + "Cancelled.\n" + Color.RESET)
        return

    new_qty = adjust_inventory_quantity(
        component=component,
        delta=delta,
        change_type="stocktake_set_count",
        reference=f"STOCKTAKE_{count_date}",
        notes=notes,
        date_received=count_date,
    )
    print(Color.GREEN + f"\n✔ Count set. New quantity for '{component}': {new_qty:g}\n" + Color.RESET)

# ------------------------------------------------------------------
# Reset inventory to ZERO (NEW)
# ------------------------------------------------------------------

def reset_inventory_component_to_zero() -> None:
    sel = select_component_from_inventory()
    if not sel:
        return

    component = sel["Component"]
    comp_code = sel["ComponentCode"]
    current_qty = sel["Quantity"]

    menu_title("Reset Inventory Component to ZERO")
    print(f"Component: {component}")
    print(f"Code: {comp_code}")
    print(f"Current Quantity: {current_qty:.2f}\n")

    reset_date = parse_date_input("Reset Date (MM-DD-YYYY): ")

    if not confirm("This will RESET quantity to ZERO and log history. Continue?"):
        print(Color.YELLOW + "Cancelled.\n" + Color.RESET)
        return

    if abs(current_qty) < 1e-9:
        print(Color.GREEN + "Quantity already zero. No action taken.\n" + Color.RESET)
        return

    delta = -current_qty

    new_qty = adjust_inventory_quantity(
        component=component,
        delta=delta,
        change_type="reset",
        reference="INVENTORY_RESET",
        notes="Reset to zero during backlog correction",
        date_received=reset_date,
    )

    print(
        Color.GREEN
        + f"\n✔ Inventory reset complete. New quantity: {new_qty:.2f}\n"
        + Color.RESET
    )


# ------------------------------------------------------------------
# Views & manual adjust (unchanged)
# ------------------------------------------------------------------

def view_inventory() -> None:
    """Main operational inventory view/dashboard."""
    inventory_status.dashboard()


def view_inventory_history() -> None:
    hist = _ensure_history()
    if hist.empty:
        print(Color.YELLOW + "\nNo inventory history entries found.\n" + Color.RESET)
        return

    menu_title("Inventory History (INV-01-History)")
    print(hist.to_string(index=False))
    print()


def adjust_inventory_manual() -> None:
    inv = _ensure_inventory()
    if inv.empty:
        print(Color.YELLOW + "\nInventory is empty. Nothing to adjust.\n" + Color.RESET)
        return

    menu_title("Manual Inventory Adjustment")

    for i, row in inv.sort_values(by="Component").reset_index(drop=True).iterrows():
        print(
            f"{i + 1}) {row['Component']} "
            f"(Code={row['ComponentCode']}, Type={row['ComponentType']}, Qty={row['Quantity']:.2f})"
        )

    choice = input("Select component number (or ENTER to cancel): ").strip()
    if not choice:
        return
    if not choice.isdigit():
        print(Color.RED + "Invalid selection." + Color.RESET)
        return

    idx = int(choice) - 1
    if idx < 0 or idx >= len(inv):
        print(Color.RED + "Selection out of range." + Color.RESET)
        return

    row = inv.sort_values(by="Component").reset_index(drop=True).iloc[idx]
    comp_name = str(row["Component"])

    delta = numeric_input("Enter quantity change (+/-): ", allow_float=True)
    notes = input("Notes (optional): ").strip()

    new_qty = adjust_inventory_quantity(
        component=comp_name,
        delta=delta,
        change_type="manual_adjust",
        reference="MANUAL",
        notes=notes,
    )

    print(
        Color.GREEN
        + f"\nInventory updated. New quantity for '{comp_name}': {new_qty:.2f}\n"
        + Color.RESET
    )

def add_inventory_component(component, component_code="", component_type=""):
    """
    Create a new inventory component with zero quantity.
    Used by RM-01 / Receiving when a component is first seen.
    Auto-populates planning fields to prevent schema drift.
    """
    import pandas as pd
    from datetime import datetime
    from file_utils import load_csv_strip, save_csv

    INVENTORY_FILE = "INV-01.csv"

    df = load_csv_strip(INVENTORY_FILE)

    # Prevent duplicates
    if component in df["Component"].values:
        return

    today = datetime.now().strftime("%m-%d-%Y")

    new_row = {
        "Component": component,
        "ComponentCode": component_code,
        "ComponentType": component_type,
        "Quantity": 0.0,
        "DateReceived": today,        # AUTO: today
        "Notes": "Added manually",    # AUTO
        "LeadTimeDays": 14.0,         # AUTO
        "MaxCapacity": 0.0,           # AUTO
        "SafetyFactor": 1.0,          # AUTO
    }

    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    save_csv(df, INVENTORY_FILE)
