"""
rename_codes.py

Utility tool to safely rename codes across *all* CSVs in this PLC system folder.

Key safety rules (to protect you from the many TBD codes):
- We ONLY update rows where BOTH the *name* and the *old code* match.
  (So we do NOT blindly replace "TBD" everywhere.)
- Before writing anything, we show a per-file "impact preview" and ask for confirmation.
- Every file that will be modified gets a .bak backup first.

What this tool updates:
1) Component Code renames:
   - Any CSV that contains:
       Name column: "Component"
       Code column: "ComponentCode" OR "Component Code"

2) Product Code renames:
   - Any CSV that contains:
       Name column: "Product" OR "Finished Product"
       Code column: "ProductCode"
   - Additionally, for rows being changed, it will update ID-like fields where the code
     is a dash-separated segment (e.g. PROD106-ATWWFX-25364):
       Columns: "ProductionID", "RefRecordID"
     It replaces ONLY a full segment that exactly equals the old code.

Designed for one-off cleanups, e.g. replacing 'TBD' with real QuickBooks codes.
"""

import os
import shutil
from typing import Dict, List, Optional, Tuple

import pandas as pd

from helpers import Color, menu_title, confirm


# ----------------------------
# System file names (known)
# ----------------------------
INVENTORY_FILE = "INV-01.csv"
INV_HISTORY_FILE = "INV-01-History.csv"
KITS_FILE = "Kits.csv"
RECEIVING_FILE = "RCV-01.csv"
PROD_FILE = "PROD-01.csv"

# Newer CSVs you mentioned / that often contain ProductCode:
FG_FILE = "FG-01.csv"
SHP_FILE = "SHP-01.csv"


# ----------------------------
# Generic helpers
# ----------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _full_path(filename: str) -> str:
    return os.path.join(BASE_DIR, filename)


def list_csv_files() -> List[str]:
    """Return all .csv files in the same folder as this script (non-recursive)."""
    files: List[str] = []
    for name in os.listdir(BASE_DIR):
        if name.lower().endswith(".csv"):
            files.append(_full_path(name))
    return sorted(files)


def backup_file(path: str) -> None:
    """Create a .bak backup of the file before modifying it."""
    if not os.path.exists(path):
        return
    backup_path = path + ".bak"
    try:
        shutil.copy2(path, backup_path)
    except Exception as e:
        print(Color.YELLOW + f"Warning: Could not create backup for {os.path.basename(path)}: {e}" + Color.RESET)


def load_csv_safe(path: str) -> pd.DataFrame:
    """Load CSV into DataFrame, or empty if missing. Read as strings to avoid dtype issues."""
    if not os.path.exists(path):
        return pd.DataFrame()
    try:
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
        df.columns = df.columns.str.strip()
        return df
    except Exception as e:
        print(Color.RED + f"Error reading {os.path.basename(path)}: {e}" + Color.RESET)
        return pd.DataFrame()


def save_csv_safe(df: pd.DataFrame, path: str) -> None:
    """Save DataFrame to CSV safely."""
    try:
        df.to_csv(path, index=False)
    except Exception as e:
        print(Color.RED + f"Error writing {os.path.basename(path)}: {e}" + Color.RESET)


def _segment_replace(value: str, old_code: str, new_code: str) -> str:
    """
    Replace dash-separated segments exactly matching old_code.
    Example: 'PROD106-ATWWFX-25364' => replace only the ATWWFX segment.
    If value doesn't look like dash-separated segments, returns unchanged.
    """
    parts = str(value).split("-")
    if len(parts) < 2:
        return str(value)
    changed = False
    for i, p in enumerate(parts):
        if p == old_code:
            parts[i] = new_code
            changed = True
    return "-".join(parts) if changed else str(value)


def _norm_line(value) -> str:
    """Normalize line values so 3, 3.0, '3.0' all compare equal ('3')."""
    s = str(value).strip()
    if s == "" or s.lower() == "nan":
        return ""
    try:
        f = float(s)
        if f.is_integer():
            return str(int(f))
        # Keep as trimmed float string (rare), without trailing zeros
        return str(f).rstrip("0").rstrip(".")
    except Exception:
        # Non-numeric (leave as-is)
        return s


def _print_preview(title: str, preview: Dict[str, int]) -> None:
    print(Color.CYAN + f"\n{title}\n" + Color.RESET)
    if not preview:
        print(Color.YELLOW + "No files will be changed.\n" + Color.RESET)
        return
    for fname, cnt in sorted(preview.items(), key=lambda x: x[0].lower()):
        print(f" - {fname}: {cnt} row(s)")
    print()


# ----------------------------
# Component Code Rename
# ----------------------------

def choose_component() -> Optional[Tuple[str, str]]:
    """
    Let user choose a (Component, ComponentCode) pair from inventory.
    Returns (component_name, old_code) or None.
    """
    inv = load_csv_safe(_full_path(INVENTORY_FILE))
    if inv.empty:
        print(Color.RED + f"\n{INVENTORY_FILE} is empty or missing.\n" + Color.RESET)
        return None

    if "Component" not in inv.columns or "ComponentCode" not in inv.columns:
        print(Color.RED + "Inventory file missing Component/ComponentCode columns.\n" + Color.RESET)
        return None

    subset = (
        inv[["Component", "ComponentCode"]]
        .drop_duplicates()
        .sort_values(by=["Component", "ComponentCode"])
        .reset_index(drop=True)
    )

    if subset.empty:
        print(Color.RED + "No components found in inventory.\n" + Color.RESET)
        return None

    menu_title("Select Component to Rename Code")
    for i, row in subset.iterrows():
        comp = str(row["Component"])
        code = str(row["ComponentCode"])
        print(f"{i + 1}) {comp}  |  Code={code}")

    print()
    choice = input("Choose number (or ENTER to cancel): ").strip()
    if not choice:
        return None
    if not choice.isdigit():
        print(Color.RED + "Invalid selection.\n" + Color.RESET)
        return None

    idx = int(choice) - 1
    if idx < 0 or idx >= len(subset):
        print(Color.RED + "Selection out of range.\n" + Color.RESET)
        return None

    row = subset.iloc[idx]
    comp_name = str(row["Component"])
    old_code = str(row["ComponentCode"])

    print(
        Color.CYAN
        + f"\nYou selected component:\n"
          f"  Name: {comp_name}\n"
          f"  Code: {old_code}\n"
        + Color.RESET
    )

    if not confirm("Proceed with renaming this component code?"):
        return None

    return comp_name, old_code


def _component_impacts(comp_name: str, old_code: str) -> Dict[str, int]:
    """
    Compute how many rows would be changed per file for a component rename.
    Only counts rows where BOTH Component == comp_name and code == old_code.
    """
    impacts: Dict[str, int] = {}
    for path in list_csv_files():
        df = load_csv_safe(path)
        if df.empty:
            continue

        # Accept both common component code column spellings
        if "Component" not in df.columns:
            continue

        code_col = None
        if "ComponentCode" in df.columns:
            code_col = "ComponentCode"
        elif "Component Code" in df.columns:
            code_col = "Component Code"

        if not code_col:
            continue

        mask = (df["Component"].astype(str) == comp_name) & (df[code_col].astype(str) == old_code)
        cnt = int(mask.sum())
        if cnt > 0:
            impacts[os.path.basename(path)] = cnt

    return impacts


def rename_component_code() -> None:
    selection = choose_component()
    if not selection:
        return

    comp_name, old_code = selection

    new_code_raw = input("Enter NEW ComponentCode (will be UPPERCASE): ").strip()
    if not new_code_raw:
        print(Color.RED + "New code cannot be empty.\n" + Color.RESET)
        return
    new_code = new_code_raw.upper()

    if new_code == old_code:
        print(Color.YELLOW + "New code is the same as old code. No changes made.\n" + Color.RESET)
        return

    impacts = _component_impacts(comp_name, old_code)
    _print_preview(
        title=(
            f"Preview: Component code rename\n"
            f"  Component: {comp_name}\n"
            f"  Old Code:  {old_code}\n"
            f"  New Code:  {new_code}\n"
            f"  Matching rule: Component == '{comp_name}' AND Code == '{old_code}'"
        ),
        preview=impacts,
    )

    if not impacts:
        print(Color.YELLOW + "No matching rows found in any CSV. Nothing to do.\n" + Color.RESET)
        return

    if not confirm("Apply these changes to the files listed above?"):
        print(Color.YELLOW + "Cancelled.\n" + Color.RESET)
        return

    # Apply updates file-by-file
    for path in list_csv_files():
        fname = os.path.basename(path)
        if fname not in impacts:
            continue

        df = load_csv_safe(path)
        if df.empty:
            continue

        code_col = "ComponentCode" if "ComponentCode" in df.columns else "Component Code"

        mask = (df["Component"].astype(str) == comp_name) & (df[code_col].astype(str) == old_code)
        if not mask.any():
            continue

        backup_file(path)
        df.loc[mask, code_col] = new_code
        save_csv_safe(df, path)
        print(Color.GREEN + f"Updated {int(mask.sum())} row(s) in {fname}." + Color.RESET)

    print(Color.GREEN + "\nComponent code rename complete.\n" + Color.RESET)


# ----------------------------
# Product Code Rename
# ----------------------------

def choose_product() -> Optional[Tuple[str, str, str]]:
    """
    Let user choose a product (Finished Product, ProductCode, Line) from Kits.
    Returns (finished_product, old_code, line_str) or None.
    """
    kits = load_csv_safe(_full_path(KITS_FILE))
    if kits.empty:
        print(Color.RED + f"\n{KITS_FILE} is empty or missing.\n" + Color.RESET)
        return None

    required_cols = ["Finished Product", "ProductCode", "Line", "UnitType", "UnitsPerPallet"]
    for col in required_cols:
        if col not in kits.columns:
            print(Color.RED + f"Kits file missing column: {col}\n" + Color.RESET)
            return None

    distinct = (
        kits[required_cols]
        .drop_duplicates()
        .sort_values(by=["UnitType", "Line", "Finished Product"])
        .reset_index(drop=True)
    )

    if distinct.empty:
        print(Color.RED + "No products found in Kits.\n" + Color.RESET)
        return None

    menu_title("Select Product to Rename ProductCode")
    for i, row in distinct.iterrows():
        fp = str(row["Finished Product"])
        pc = str(row["ProductCode"])
        ln = str(row["Line"])
        ut = str(row["UnitType"])
        try:
            upp = float(str(row["UnitsPerPallet"]))
        except Exception:
            upp = 0.0
        print(f"{i + 1}) Line {ln} | {fp} | Code={pc} | UnitType={ut} | Units/Pallet={upp:.0f}")

    print()
    choice = input("Choose number (or ENTER to cancel): ").strip()
    if not choice:
        return None
    if not choice.isdigit():
        print(Color.RED + "Invalid selection.\n" + Color.RESET)
        return None

    idx = int(choice) - 1
    if idx < 0 or idx >= len(distinct):
        print(Color.RED + "Selection out of range.\n" + Color.RESET)
        return None

    row = distinct.iloc[idx]
    fp = str(row["Finished Product"])
    old_code = str(row["ProductCode"])
    line_str = str(row["Line"])

    print(
        Color.CYAN
        + f"\nYou selected product:\n"
          f"  Name: {fp}\n"
          f"  Code: {old_code}\n"
          f"  Line: {line_str}\n"
        + Color.RESET
    )

    if not confirm("Proceed with renaming this product code?"):
        return None

    return fp, old_code, line_str


def _product_impacts(finished_product: str, old_code: str, line_str: str) -> Dict[str, int]:
    """
    Compute how many rows would be changed per file for a product rename.
    Only counts rows where:
      - (Product OR Finished Product) matches finished_product
      - ProductCode matches old_code
      - If 'Line' exists in the file, Line matches line_str (string compare)
    """
    impacts: Dict[str, int] = {}
    for path in list_csv_files():
        df = load_csv_safe(path)
        if df.empty:
            continue

        if "ProductCode" not in df.columns:
            continue

        name_col = None
        if "Finished Product" in df.columns:
            name_col = "Finished Product"
        elif "Product" in df.columns:
            name_col = "Product"

        if not name_col:
            continue

        mask = (df[name_col].astype(str) == finished_product) & (df["ProductCode"].astype(str) == old_code)

        # Optional line narrowing if the file has Line
        if "Line" in df.columns:
            target_line = _norm_line(line_str)
            mask = mask & (df["Line"].apply(_norm_line) == target_line)

        cnt = int(mask.sum())
        if cnt > 0:
            impacts[os.path.basename(path)] = cnt

    return impacts


def _apply_product_updates_to_df(
    df: pd.DataFrame,
    finished_product: str,
    old_code: str,
    new_code: str,
    line_str: str
) -> Tuple[int, int]:
    """
    Apply product code rename to a DataFrame in-place.
    Returns (rows_updated, ids_updated).

    Updates:
    - ProductCode in matching rows
    - For matching rows, also update ProductionID / RefRecordID dash-segment if present
    """
    if df.empty or "ProductCode" not in df.columns:
        return 0, 0

    name_col = "Finished Product" if "Finished Product" in df.columns else ("Product" if "Product" in df.columns else None)
    if not name_col:
        return 0, 0

    mask = (df[name_col].astype(str) == finished_product) & (df["ProductCode"].astype(str) == old_code)
    if "Line" in df.columns:
            target_line = _norm_line(line_str)
            mask = mask & (df["Line"].apply(_norm_line) == target_line)

    rows = int(mask.sum())
    if rows == 0:
        return 0, 0

    # Update ProductCode
    df.loc[mask, "ProductCode"] = new_code

    # Update ID-like columns for the affected rows only
    ids_updated = 0
    for id_col in ["ProductionID", "RefRecordID"]:
        if id_col in df.columns:
            original = df.loc[mask, id_col].astype(str)
            updated = original.apply(lambda v: _segment_replace(v, old_code, new_code))
            ids_updated += int((original != updated).sum())
            df.loc[mask, id_col] = updated

    return rows, ids_updated


def rename_product_code() -> None:
    selection = choose_product()
    if not selection:
        return

    finished_product, old_code, line_str = selection

    new_code_raw = input("Enter NEW ProductCode (will be UPPERCASE): ").strip()
    if not new_code_raw:
        print(Color.RED + "New ProductCode cannot be empty.\n" + Color.RESET)
        return
    new_code = new_code_raw.upper()

    if new_code == old_code:
        print(Color.YELLOW + "New ProductCode is the same as old code. No changes made.\n" + Color.RESET)
        return

    impacts = _product_impacts(finished_product, old_code, line_str)
    _print_preview(
        title=(
            f"Preview: Product code rename\n"
            f"  Product:   {finished_product}\n"
            f"  Line:      {line_str}\n"
            f"  Old Code:  {old_code}\n"
            f"  New Code:  {new_code}\n"
            f"  Matching rule: Name == '{finished_product}' AND ProductCode == '{old_code}'"
            + (f" AND Line == '{line_str}' (when Line column exists)" if True else "")
        ),
        preview=impacts,
    )

    if not impacts:
        print(Color.YELLOW + "No matching rows found in any CSV. Nothing to do.\n" + Color.RESET)
        return

    if not confirm("Apply these changes to the files listed above?"):
        print(Color.YELLOW + "Cancelled.\n" + Color.RESET)
        return

    # Apply updates file-by-file
    total_rows = 0
    total_ids = 0

    for path in list_csv_files():
        fname = os.path.basename(path)
        if fname not in impacts:
            continue

        df = load_csv_safe(path)
        if df.empty:
            continue

        rows_updated, ids_updated = _apply_product_updates_to_df(df, finished_product, old_code, new_code, line_str)
        if rows_updated == 0:
            continue

        backup_file(path)
        save_csv_safe(df, path)

        total_rows += rows_updated
        total_ids += ids_updated

        msg = f"Updated {rows_updated} row(s) in {fname}."
        if ids_updated > 0:
            msg += f" (Also updated {ids_updated} ID field value(s).)"
        print(Color.GREEN + msg + Color.RESET)

    print(Color.GREEN + f"\nProduct code rename complete. Rows updated: {total_rows}. ID values updated: {total_ids}.\n" + Color.RESET)


# ----------------------------
# Main Menu
# ----------------------------

def main() -> None:
    while True:
        menu_title("Code Rename Tool")
        print("1) Rename Component Code")
        print("2) Rename Product Code")
        print("3) Exit")

        choice = input("Choose: ").strip()

        if choice == "1":
            rename_component_code()
        elif choice == "2":
            rename_product_code()
        elif choice == "3":
            print(Color.GREEN + "\nExiting Code Rename Tool.\n" + Color.RESET)
            break
        else:
            print(Color.RED + "Invalid choice.\n" + Color.RESET)


if __name__ == "__main__":
    main()
