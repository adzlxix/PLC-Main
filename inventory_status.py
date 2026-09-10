"""
inventory_status.py

Lightweight operational inventory dashboard helpers.
Does NOT touch QuickBooks financial inventory.

Adds clear min/reorder/max status logic for INV-01.csv.
"""

from __future__ import annotations

from datetime import datetime
import os
import pandas as pd

from file_utils import load_csv_strip, save_csv
from helpers import Color, menu_title, numeric_input, confirm

INVENTORY_FILE = "INV-01.csv"
INVENTORY_HISTORY_FILE = "INV-01-History.csv"
EXPORT_DIR = "exports"

STATUS_COLUMNS = ["MinQty", "ReorderPoint", "MaxQty"]


def _load_inv() -> pd.DataFrame:
    df = load_csv_strip(INVENTORY_FILE)
    for col in ["Component", "ComponentCode", "ComponentType", "Quantity"]:
        if col not in df.columns:
            df[col] = "" if col != "Quantity" else 0.0
    df["Quantity"] = pd.to_numeric(df["Quantity"], errors="coerce").fillna(0.0)
    for col in STATUS_COLUMNS:
        if col not in df.columns:
            df[col] = ""
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _save_inv(df: pd.DataFrame) -> None:
    save_csv(df, INVENTORY_FILE)


def status_for(qty: float, min_qty, reorder_point, max_qty=None) -> str:
    q = float(qty or 0)
    try:
        rop = float(reorder_point)
    except Exception:
        rop = None
    try:
        mn = float(min_qty)
    except Exception:
        mn = None

    if q < 0:
        return "NEGATIVE"
    if q == 0:
        return "ZERO"
    if rop is None and mn is None:
        return "NO MIN SET"
    if rop is not None and q <= rop:
        return "REORDER"
    if mn is not None and q <= mn:
        return "LOW"
    return "OK"


def with_status(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in STATUS_COLUMNS:
        if col not in out.columns:
            out[col] = pd.NA
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out["Quantity"] = pd.to_numeric(out.get("Quantity", 0), errors="coerce").fillna(0.0)
    out["Status"] = out.apply(
        lambda r: status_for(r.get("Quantity", 0), r.get("MinQty"), r.get("ReorderPoint"), r.get("MaxQty")),
        axis=1,
    )
    return out


def _status_color(status: str) -> str:
    status = str(status).upper()
    if status in ("NEGATIVE", "REORDER"):
        return Color.RED
    if status in ("ZERO", "LOW", "NO MIN SET"):
        return Color.YELLOW
    if status == "OK":
        return Color.GREEN
    return ""


def _print_rows(df: pd.DataFrame) -> None:
    if df.empty:
        print(Color.YELLOW + "No items found.\n" + Color.RESET)
        return

    print(f"{'Status':12} {'Code':18} {'Type':14} {'Qty':>10} {'ROP':>10} {'Max':>10}  Name")
    print("-" * 105)
    for _, r in df.iterrows():
        status = str(r.get("Status", ""))
        col = _status_color(status)
        qty = int(float(r.get("Quantity", 0) or 0))
        rop = r.get("ReorderPoint")
        mx = r.get("MaxQty")
        rop_txt = "" if pd.isna(rop) else str(int(float(rop)))
        max_txt = "" if pd.isna(mx) else str(int(float(mx)))
        print(
            f"{col}{status:12}{Color.RESET} "
            f"{str(r.get('ComponentCode',''))[:18]:18} "
            f"{str(r.get('ComponentType',''))[:14]:14} "
            f"{qty:>10} {rop_txt:>10} {max_txt:>10}  "
            f"{str(r.get('Component',''))[:55]}"
        )
    print()


def dashboard() -> None:
    """Simple dashboard for operational stock visibility."""
    inv = with_status(_load_inv())
    if inv.empty:
        print(Color.YELLOW + "No inventory rows found.\n" + Color.RESET)
        return

    while True:
        menu_title("Operational Inventory Dashboard")
        print("1) Raw Materials only")
        print("2) Components / Packaging only")
        print("3) Low / Reorder / Zero / Negative")
        print("4) Search all inventory")
        print("5) Edit reorder levels")
        print("6) Export inventory backup CSV")
        print("7) Back")
        choice = input("Choose: ").strip()

        inv = with_status(_load_inv())
        if choice == "1":
            view = inv[inv["ComponentType"].astype(str).str.lower().str.contains("raw|material|bulk|chemical", na=False)].copy()
            if view.empty:
                # RM-BAL items often have component type blank in INV. Show obvious raw material codes too.
                view = inv[inv["ComponentCode"].astype(str).str.upper().str.contains("BULK|RAW|GAL|MET|GLYCOL|ETH|DEF|OIL|WATER|CAUSTIC", na=False)].copy()
            menu_title("Raw Materials On Hand")
            _print_rows(view.sort_values(["Status", "Component"]))
        elif choice == "2":
            raw_mask = inv["ComponentType"].astype(str).str.lower().str.contains("raw|material|bulk|chemical", na=False)
            view = inv[~raw_mask].copy()
            groups = sorted([g for g in view["ComponentType"].astype(str).str.strip().unique() if g])
            print("\nGroups:")
            print("0) All components")
            for i, g in enumerate(groups, start=1):
                print(f"{i}) {g}")
            gchoice = input("Choose group (ENTER=all): ").strip()
            if gchoice and gchoice != "0" and gchoice.isdigit():
                gi = int(gchoice) - 1
                if 0 <= gi < len(groups):
                    view = view[view["ComponentType"].astype(str).str.strip() == groups[gi]]
            menu_title("Components On Hand")
            _print_rows(view.sort_values(["Status", "ComponentType", "Component"]))
        elif choice == "3":
            bad = inv[inv["Status"].isin(["NEGATIVE", "ZERO", "REORDER", "LOW", "NO MIN SET"])].copy()
            order = {"NEGATIVE": 0, "REORDER": 1, "ZERO": 2, "LOW": 3, "NO MIN SET": 4}
            bad["_order"] = bad["Status"].map(order).fillna(9)
            menu_title("Inventory Attention Needed")
            _print_rows(bad.sort_values(["_order", "Component"]).drop(columns=["_order"], errors="ignore"))
        elif choice == "4":
            q = input("Search code/name/type: ").strip().lower()
            if not q:
                continue
            view = inv[
                inv["Component"].astype(str).str.lower().str.contains(q, na=False)
                | inv["ComponentCode"].astype(str).str.lower().str.contains(q, na=False)
                | inv["ComponentType"].astype(str).str.lower().str.contains(q, na=False)
            ].copy()
            _print_rows(view.sort_values(["Component"]))
        elif choice == "5":
            edit_reorder_levels()
        elif choice == "6":
            export_inventory_backup_csv()
        elif choice == "7":
            break
        else:
            print(Color.RED + "Invalid choice.\n" + Color.RESET)


def edit_reorder_levels() -> None:
    inv = with_status(_load_inv())
    q = input("Search item code/name to edit reorder levels: ").strip().lower()
    if not q:
        return
    matches = inv[
        inv["Component"].astype(str).str.lower().str.contains(q, na=False)
        | inv["ComponentCode"].astype(str).str.lower().str.contains(q, na=False)
    ].copy().reset_index()
    if matches.empty:
        print(Color.YELLOW + "No matches.\n" + Color.RESET)
        return
    for i, r in matches.head(30).iterrows():
        print(f"{i+1}) {r['ComponentCode']} | {r['Component']} | Qty {int(float(r['Quantity']))} | Status {r['Status']}")
    choice = input("Choose item number: ").strip()
    if not choice.isdigit():
        return
    idx = int(choice) - 1
    if idx < 0 or idx >= min(len(matches), 30):
        print(Color.RED + "Invalid selection.\n" + Color.RESET)
        return

    original_index = matches.loc[idx, "index"]
    row = inv.loc[original_index]
    print(f"\nSelected: {row.get('ComponentCode')} | {row.get('Component')}")
    print("Leave blank to keep current value.")
    updates = {}
    for col, label in [("MinQty", "Minimum Qty"), ("ReorderPoint", "Reorder Point"), ("MaxQty", "Maximum Qty")]:
        cur = row.get(col)
        cur_txt = "" if pd.isna(cur) else str(int(float(cur)))
        val = input(f"{label} [{cur_txt}]: ").strip()
        if val:
            try:
                updates[col] = float(val)
            except ValueError:
                print(Color.RED + f"Invalid number for {label}; skipped." + Color.RESET)
    if not updates:
        print(Color.YELLOW + "No changes made.\n" + Color.RESET)
        return
    for col, val in updates.items():
        inv.loc[original_index, col] = val
    _save_inv(inv.drop(columns=["Status"], errors="ignore"))
    print(Color.GREEN + "\n✔ Reorder levels updated.\n" + Color.RESET)


def export_inventory_backup_csv() -> str:
    os.makedirs(EXPORT_DIR, exist_ok=True)
    inv = with_status(_load_inv())
    out = inv.copy()
    # Keep exact figures in export; display can be rounded in terminal only.
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(EXPORT_DIR, f"inventory_backup_{stamp}.csv")
    out.to_csv(path, index=False)
    print(Color.GREEN + f"\n✔ Inventory backup exported: {path}\n" + Color.RESET)
    return path
