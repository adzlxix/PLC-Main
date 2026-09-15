"""
production.py

Handles:
- Recording production (PROD-01.csv)
- Viewing production history
- Weekly production report (with grouped downtime per line)
- Historic line performance (cases only)

ISO notes:
- Confirmation checkpoint before saving + inventory consumption (A)
- PROD-01 schema enforcement (D)
- Downtime included in weekly report (B) (read-only)
"""

import math

import pandas as pd
from datetime import datetime

from helpers import Color, menu_title, parse_date_input, numeric_input
from file_utils import load_csv_strip, save_csv, normalize_id, normalize_id_series
from audit import log_audit
from inventory import adjust_inventory_quantity, component_exists, load_inventory
from kits import load_kits
from raw_materials import adjust_raw_material_quantity, is_raw_material_row, get_raw_material_on_hand, raw_material_exists
import finished_goods as fg
import line_runtime as lr
from line_utils import choose_line as choose_configured_line

PRODUCTION_FILE = "PROD-01.csv"
DOWNTIME_FILE = "DT-01.csv"
LINE_SETTINGS_FILE = "LineSettings.csv"

PROD_COLUMNS = [
    "ProductionID",
    "Date",
    "Line",
    "Product",
    "ProductCode",
    "UnitType",
    "UnitsCompleted",
    "UnitsPerPallet",
    "PalletsCompleted",
    "Notes",
]


# ------------------------------------------------------------
# Core loaders (used by other modules)
# ------------------------------------------------------------
def load_production() -> pd.DataFrame:
    """
    Load production data safely for use by other modules (e.g. health_check).
    Enforces schema + numeric normalization (D).
    """
    df = load_csv_strip(PRODUCTION_FILE, headers_default=PROD_COLUMNS)

    # Ensure schema (D)
    for col in PROD_COLUMNS:
        if col not in df.columns:
            df[col] = ""

    # Normalize numeric columns safely
    for col in ["UnitsCompleted", "UnitsPerPallet", "PalletsCompleted"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    # Keep consistent types for common fields
    for col in ["ProductionID", "Date", "Line", "Product", "ProductCode", "UnitType", "Notes"]:
        df[col] = df[col].fillna("").astype(str).str.strip()
    df["Line"] = normalize_id_series(df["Line"])

    return df


def save_production(df: pd.DataFrame) -> None:
    """Persist production rows with enforced schema and column order."""
    df = df.copy()
    for col in PROD_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df = df[PROD_COLUMNS]
    save_csv(df, PRODUCTION_FILE)


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------
def load_line_names() -> dict:
    """
    Load human-readable line names from LineSettings.csv
    """
    try:
        df = load_csv_strip(LINE_SETTINGS_FILE)
        if {"Line", "LineName"}.issubset(df.columns):
            return {
                normalize_id(r["Line"]): str(r["LineName"]).strip()
                for _, r in df.iterrows()
                if str(r["LineName"]).strip()
            }
    except Exception:
        pass
    return {}


def load_downtime_for_report(start_date: str, end_date: str) -> pd.DataFrame:
    """
    Load downtime records filtered by date range.
    """
    df = load_csv_strip(DOWNTIME_FILE)
    if df.empty:
        return df

    # Allow report to run even if some columns are missing
    for col in ["Date", "Line", "MachineType/Name", "Issue", "Downtime Minutes"]:
        if col not in df.columns:
            df[col] = ""

    df["_dt"] = pd.to_datetime(df["Date"], format="%m-%d-%Y", errors="coerce")
    s = pd.to_datetime(start_date, format="%m-%d-%Y", errors="coerce")
    e = pd.to_datetime(end_date, format="%m-%d-%Y", errors="coerce")

    df = df[(df["_dt"] >= s) & (df["_dt"] <= e)].copy()
    df.drop(columns=["_dt"], inplace=True, errors="ignore")
    return df


def print_grouped_downtime(df: pd.DataFrame, line: str) -> None:
    """
    Print grouped downtime for a specific line.
    Grouped by Machine + Issue.
    """
    if df is None or df.empty:
        print("\n⏱️ Downtime Summary")
        print("No downtime recorded for this line.\n")
        return

    subset = df[df["Line"].astype(str).str.strip() == str(line).strip()].copy()
    if subset.empty:
        print("\n⏱️ Downtime Summary")
        print("No downtime recorded for this line.\n")
        return

    subset["Downtime Minutes"] = pd.to_numeric(subset["Downtime Minutes"], errors="coerce").fillna(0)
    total_minutes = int(subset["Downtime Minutes"].sum())
    groups = subset.groupby(["MachineType/Name", "Issue"], dropna=False)

    print("\n⏱️ Downtime Summary")
    print(f"Total downtime: {total_minutes // 60} hrs {total_minutes % 60} mins")
    print(f"Downtime events: {len(groups)}\n")

    for (machine, issue), g in groups:
        machine = str(machine) if str(machine).strip() else "Unknown"
        issue = str(issue) if str(issue).strip() else "Unknown"
        event_minutes = int(pd.to_numeric(g["Downtime Minutes"], errors="coerce").fillna(0).sum())

        print(f"🔧 Event: {issue}")
        print(f"Machine / Area: {machine}")
        print(f"Total duration: {event_minutes // 60} hrs {event_minutes % 60} mins\n")

        print(f"{'Date':<12} {'Downtime':>10}")
        print("-" * 24)
        for _, r in g.iterrows():
            mins = int(pd.to_numeric(r.get("Downtime Minutes", 0), errors="coerce") or 0)
            label = f"{mins // 60} hr {mins % 60} mins" if mins >= 60 else f"{mins} mins"
            print(f"{str(r.get('Date','')):<12} {label:>10}")
        print()


def _julian_from_mmddyyyy(date_str: str) -> str:
    dt = datetime.strptime(date_str, "%m-%d-%Y")
    return dt.strftime("%y%j")  # YY + Julian day (001-366)




def _unit_char_from_unit_type(unit_type: str) -> str:
    """
    Single-character unit marker for compact LabelID.
    - Cases are pallet labels -> 'P'
    - Everything else -> 'U' (unit)
    """
    ut = (unit_type or "").strip().lower()
    return "P" if ut == "case" else "U"


def _compact_label_id(line: str, product_code: str, date_str: str, unit_type: str, seq: int) -> str:
    """
    Compact LabelID format (as agreed):
        P{LL}{PRODUCT6}{YYDOY5}{UnitChar}{SEQ3}

    Example:
        P03ATWWPX25360P099
    """
    line2 = f"{int(line):02d}"
    pc = (product_code or "").strip().upper()
    jul = _julian_from_mmddyyyy(date_str)
    unit_char = _unit_char_from_unit_type(unit_type)
    return f"P{line2}{pc}{jul}{unit_char}{int(seq):03d}"
def _generate_production_id(df: pd.DataFrame, product_code: str, date_str: str) -> str:
    julian = _julian_from_mmddyyyy(date_str)
    existing = df[df["ProductionID"].astype(str).str.startswith("PROD")]
    next_num = len(existing) + 1
    return f"PROD{next_num}-{product_code}-{julian}"


def _choose_line() -> str:
    line = choose_configured_line()
    return line or ""


def _choose_product_from_kits(kits_df: pd.DataFrame, line: str) -> dict:
    """
    Returns a dict representing the selected product row, filtered by selected line.
    Expects kits_df contains: Finished Product, ProductCode, Line, UnitType, UnitsPerPallet
    """
    # Filter by selected line (fixes your regression)
    kits_line = kits_df[kits_df["Line"].astype(str).str.strip() == str(line).strip()].copy()
    if kits_line.empty:
        print(Color.YELLOW + f"\nNo products found in Kits.csv for Line {line}.\n" + Color.RESET)
        return {}

    # Unique finished products for that line
    products = (
        kits_line[["Finished Product", "ProductCode", "UnitType", "UnitsPerPallet"]]
        .drop_duplicates()
        .copy()
    )

    products["UnitType"] = products["UnitType"].astype(str).str.strip().str.lower()
    products = products.sort_values(by=["UnitType", "Finished Product"]).reset_index(drop=True)

    menu_title(f"Select Product (Line {line})")
    current_type = None
    for i, row in products.iterrows():
        ut = str(row["UnitType"]).lower()
        if ut != current_type:
            current_type = ut
            print(Color.CYAN + f"\n--- {current_type.upper()} ---" + Color.RESET)
        print(f"{i+1}) {row['Finished Product']} ({row['ProductCode']})")

    while True:
        choice = input("\nChoose product number: ").strip()
        if not choice.isdigit():
            print(Color.RED + "Invalid selection." + Color.RESET)
            continue
        idx = int(choice)
        if not (1 <= idx <= len(products)):
            print(Color.RED + "Invalid selection." + Color.RESET)
            continue
        return products.iloc[idx - 1].to_dict()


# ------------------------------------------------------------
# Production functions (RESTORED)
# ------------------------------------------------------------

# ------------------------------------------------------------
# Pallet Label Issuance (LBL-01.csv)
# ------------------------------------------------------------

LABEL_FILE = "LBL-01.csv"
LABEL_COLUMNS = [
    "LabelID",
    "ProductionID",
    "ProductionDate",
    "IssuedOn",
    "Line",
    "Product",
    "ProductCode",
    "UnitType",
    "UnitsPerPallet",
    "LabelSeq",
    "Status",        # ISSUED / USED / VOID
    "Notes",
]


def load_labels() -> pd.DataFrame:
    """
    Load or initialize LBL-01.csv.
    """
    df = load_csv_strip(LABEL_FILE)
    # Ensure schema
    for col in LABEL_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    return df[LABEL_COLUMNS]


def _deterministic_production_id(product_code: str, line: str, date_str: str) -> str:
    """
    Deterministic ID so labels generated in the morning match production recorded later.
    One ProductionID per (date, line, product_code).
    """
    julian = _julian_from_mmddyyyy(date_str)
    return f"PROD{str(line).strip()}-{str(product_code).strip().upper()}-{julian}"


def issue_pallet_labels() -> None:
    """
    Issue (generate) a batch of pallet labels for a specific run.
    These rows can be used as the Zebra Designer variable data source (CSV).
    """
    kits_df = load_kits()
    if kits_df.empty:
        print(Color.YELLOW + "\nNo products found in Kits.csv.\n" + Color.RESET)
        return

    date_str = parse_date_input("Production date for labels (MM-DD-YYYY): ")
    if not date_str:
        print(Color.RED + "Date cannot be empty.\n" + Color.RESET)
        return

    line = _choose_line()
    prod_row = _choose_product_from_kits(kits_df, line)
    if not prod_row:
        return

    product_name = str(prod_row["Finished Product"]).strip()
    product_code = str(prod_row["ProductCode"]).strip().upper()
    unit_type = str(prod_row["UnitType"]).strip().lower()
    units_per_pallet = float(pd.to_numeric(prod_row.get("UnitsPerPallet", 0), errors="coerce") or 0)

    production_id = _deterministic_production_id(product_code, line, date_str)

    try:
        count = int(input("How many pallet labels to generate? ").strip())
    except ValueError:
        print(Color.RED + "Invalid number.\n" + Color.RESET)
        return

    if count <= 0:
        print(Color.RED + "Must be at least 1.\n" + Color.RESET)
        return

    labels = load_labels()

    # Prevent accidental duplicate issuance for same run
    existing_run = labels[
        (labels["ProductionID"].astype(str).str.strip() == production_id)
        & (labels["ProductionDate"].astype(str).str.strip() == date_str)
    ]
    if not existing_run.empty:
        print(
            Color.YELLOW
            + f"\nLabels already exist for this run ({production_id}).\n"
            + "Use them, or void them first if you need to re-issue.\n"
            + Color.RESET
        )
        return

    issued_on = datetime.now().strftime("%m-%d-%Y %H:%M")

    new_rows = []
    for seq in range(1, count + 1):
        label_id = f"{production_id}-{seq:03d}"
        new_rows.append(
            {
                "LabelID": label_id,
                "ProductionID": production_id,
                "ProductionDate": date_str,
                "IssuedOn": issued_on,
                "Line": str(line),
                "Product": product_name,
                "ProductCode": product_code,
                "UnitType": unit_type,
                "UnitsPerPallet": units_per_pallet,
                "LabelSeq": seq,
                "Status": "ISSUED",
                "Notes": "",
            }
        )

    labels = pd.concat([labels, pd.DataFrame(new_rows)], ignore_index=True)
    save_csv(labels[LABEL_COLUMNS], LABEL_FILE)

    # Global audit log (append-only)
    try:
        log_audit(
            module="labels",
            action="ISSUE_LABELS",
            entity_type="LabelRun",
            entity_id=str(production_id),
            user="UNKNOWN",
            details={
                "ProductionDate": date_str,
                "Line": str(line),
                "ProductCode": str(product_code),
                "UnitType": str(unit_type),
                "Count": int(count),
            },
        )
    except Exception:
        pass

    print(Color.GREEN + f"\n✔ Issued {count} labels for {product_name} (Line {line})." + Color.RESET)
    print(Color.GREEN + f"ProductionID: {production_id}\n" + Color.RESET)
    print("Tip: Use LBL-01.csv as your Zebra Designer variable data source.\n")


def _choose_label_run_for_date(labels: pd.DataFrame, date_str: str) -> dict | None:
    """
    Pick a label run for a given date: grouped by (Line, Product, ProductionID).
    Returns a dict with keys: ProductionID, Line, Product, ProductCode, UnitType, UnitsPerPallet
    """
    day = labels[labels["ProductionDate"].astype(str).str.strip() == date_str].copy()
    if day.empty:
        print(Color.YELLOW + "\nNo labels found for that date.\n" + Color.RESET)
        return None

    # Group runs
    grp = (
        day.groupby(["Line", "Product", "ProductionID", "ProductCode", "UnitType", "UnitsPerPallet"])
        .agg(
            issued=("Status", lambda s: int((s == "ISSUED").sum())),
            used=("Status", lambda s: int((s == "USED").sum())),
            void=("Status", lambda s: int((s == "VOID").sum())),
            total=("Status", "count"),
        )
        .reset_index()
    )

    menu_title(f"Label Runs for {date_str}")
    for i, r in grp.iterrows():
        print(
            f"{i+1}) Line {r['Line']} | {r['Product']} | "
            f"Issued:{r['total']} Used:{r['used']} Void:{r['void']}"
        )

    choice = input("Choose run number: ").strip()
    try:
        idx = int(choice) - 1
    except ValueError:
        print(Color.RED + "Invalid choice.\n" + Color.RESET)
        return None

    if idx < 0 or idx >= len(grp):
        print(Color.RED + "Invalid choice.\n" + Color.RESET)
        return None

    r = grp.iloc[idx]
    return {
        "ProductionID": str(r["ProductionID"]),
        "Line": str(r["Line"]),
        "Product": str(r["Product"]),
        "ProductCode": str(r["ProductCode"]),
        "UnitType": str(r["UnitType"]),
        "UnitsPerPallet": float(pd.to_numeric(r["UnitsPerPallet"], errors="coerce") or 0),
    }


def _mark_labels_used_and_void(
    labels: pd.DataFrame,
    production_id: str,
    used_start: int,
    used_end: int,
    void_rest: bool = True,
) -> tuple[pd.DataFrame, int, int]:
    """
    Marks used range as USED. Optionally voids any remaining ISSUED labels in that run.
    Returns updated labels, used_count, voided_count.
    """
    run = labels[labels["ProductionID"].astype(str).str.strip() == production_id].copy()
    if run.empty:
        return labels, 0, 0

    # Only consider labels currently ISSUED when applying changes
    run_issued = run[run["Status"].astype(str).str.strip().str.upper() == "ISSUED"].copy()
    if run_issued.empty:
        return labels, 0, 0

    # Determine seqs available
    seqs = sorted(pd.to_numeric(run_issued["LabelSeq"], errors="coerce").fillna(0).astype(int).tolist())
    if not seqs:
        return labels, 0, 0

    # Validate range
    if used_start < min(seqs) or used_end > max(seqs) or used_start > used_end:
        return labels, 0, 0

    used_set = set(range(used_start, used_end + 1))

    # Apply updates to the master df
    def _set_status(row, status: str):
        labels.loc[row.name, "Status"] = status

    used_count = 0
    voided_count = 0

    for idx, row in labels.iterrows():
        if str(row.get("ProductionID", "")).strip() != production_id:
            continue
        if str(row.get("Status", "")).strip().upper() != "ISSUED":
            continue
        seq = int(pd.to_numeric(row.get("LabelSeq", 0), errors="coerce") or 0)
        if seq in used_set:
            labels.at[idx, "Status"] = "USED"
            used_count += 1

    if void_rest:
        for idx, row in labels.iterrows():
            if str(row.get("ProductionID", "")).strip() != production_id:
                continue
            if str(row.get("Status", "")).strip().upper() != "ISSUED":
                continue
            seq = int(pd.to_numeric(row.get("LabelSeq", 0), errors="coerce") or 0)
            if seq not in used_set:
                labels.at[idx, "Status"] = "VOID"
                voided_count += 1

    return labels, used_count, voided_count


def record_production_from_issued_labels() -> None:
    """
    New workflow:
    - Ask production date
    - Choose a label run created for that date
    - Select used label range (e.g., 1–22)
    - Auto-calc pallets/units
    - Write one PROD-01 row for the run (ProductionID matches labels)
    - Consume inventory (same as manual mode)
    - Mark unused labels as VOID (optional)
    """
    kits_df = load_kits()
    if kits_df.empty:
        print(Color.YELLOW + "\nNo products found in Kits.csv.\n" + Color.RESET)
        return

    date_str = parse_date_input("Production date (MM-DD-YYYY): ")
    if not date_str:
        print(Color.RED + "Date cannot be empty.\n" + Color.RESET)
        return

    labels = load_labels()
    run = _choose_label_run_for_date(labels, date_str)
    if not run:
        return

    production_id = run["ProductionID"]
    line = run["Line"]
    product_name = run["Product"]
    product_code = run["ProductCode"]
    unit_type = run["UnitType"].strip().lower()
    units_per_pallet = float(run.get("UnitsPerPallet", 0) or 0)

    # Find kits row for this product+line to consume BOM before writing runtime.
    product_kits = kits_df[
        (kits_df["Finished Product"].astype(str).str.strip() == product_name)
        & (kits_df["ProductCode"].astype(str).str.strip().str.upper() == str(product_code).strip().upper())
        & (kits_df["Line"].astype(str).str.strip() == str(line).strip())
    ].copy()

    if product_kits.empty:
        print(Color.RED + "\nNo BOM rows found for that product/line in Kits.csv.\n" + Color.RESET)
        return

    # Ensure runtime exists only after the label run has a valid BOM.
    lr.ensure_runtime_for_line_date(date_str, line, entered_by="UNKNOWN", prompt_if_exists=True)

    # Ask used range
    try:
        used_start = int(input("Used label start # (e.g., 1): ").strip())
        used_end = int(input("Used label end # (e.g., 22): ").strip())
    except ValueError:
        print(Color.RED + "Invalid range.\n" + Color.RESET)
        return

    void_rest = input("Void remaining unused labels for this run? (Y/N): ").strip().upper() != "N"

    # Update labels first (validate range)
    labels2, used_count, voided_count = _mark_labels_used_and_void(labels, production_id, used_start, used_end, void_rest)
    if used_count == 0:
        print(Color.RED + "\nNo labels were marked USED — check your range.\n" + Color.RESET)
        return

    # Calculate quantities
    units_completed = 0.0
    pallets_completed = 0.0

    if unit_type == "case":
        pallets_completed = float(used_count)
        units_completed = pallets_completed * units_per_pallet if units_per_pallet > 0 else 0.0
    else:
        # For drums/totes/buckets etc, treat each label as one unit unless you decide otherwise later
        units_completed = float(used_count)
        pallets_completed = (units_completed / units_per_pallet) if units_per_pallet > 0 else 0.0

    notes = f"Labels used: {used_start}-{used_end}"
    if void_rest and voided_count > 0:
        notes += f" | Voided: {voided_count}"

    # Load production and prevent duplicates
    df = load_production()
    if not df.empty:
        dup = df[df["ProductionID"].astype(str).str.strip() == production_id]
        if not dup.empty:
            print(Color.YELLOW + f"\nProductionID already exists in PROD-01: {production_id}\n" + Color.RESET)
            return

    # Preview consumption
    consumption_preview = _build_consumption_preview(product_kits, units_completed, pallets_completed)

    # ISO confirmation checkpoint
    menu_title("Confirm Production Entry")
    print(f"ProductionID: {production_id}")
    print(f"Date: {date_str}")
    print(f"Line: {line}")
    print(f"Product: {product_name}")
    print(f"ProductCode: {product_code}")
    print(f"UnitType: {unit_type}")
    if unit_type == "case":
        print(f"Pallets: {pallets_completed:.0f}")
        print(f"Cases: {units_completed:.0f}")
    else:
        print(f"Units: {units_completed:.0f}")
        print(f"Pallet-equivalent: {pallets_completed:.2f}")
    print("\nInventory to consume:")
    _print_consumption_preview(consumption_preview)

    shortage_errors = _validate_consumption_availability(consumption_preview)
    if shortage_errors:
        print(Color.YELLOW + "\nWARNING: Production will create negative inventory for:" + Color.RESET)
        for err in shortage_errors:
            print(Color.YELLOW + f" - {err}" + Color.RESET)

    confirm = input("\nProceed? (Y/N): ").strip().upper()
    if confirm != "Y":
        print(Color.YELLOW + "\nCancelled.\n" + Color.RESET)
        return

    # Build row + append
    new_row = {
        "ProductionID": production_id,
        "Date": date_str,
        "Line": line,
        "Product": product_name,
        "ProductCode": product_code,
        "UnitType": unit_type,
        "UnitsCompleted": units_completed,
        "UnitsPerPallet": units_per_pallet,
        "PalletsCompleted": pallets_completed,
        "Notes": notes,
    }
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)

    # Ensure schema
    for col in PROD_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df = df[PROD_COLUMNS]

    save_csv(df, PRODUCTION_FILE)

    # Consume inventory / raw materials
    _apply_consumption(consumption_preview, production_id, date_str, line, product_name)


    # Save updated labels
    save_csv(labels2[LABEL_COLUMNS], LABEL_FILE)

    # Post to Finished Goods ledger (pallets only)
    if str(unit_type).lower() == "case":
        try:
            fg.add_entry(
                entry_type="PRODUCE",
                date_str=date_str,
                product=product_name,
                product_code=product_code,
                line=str(line),
                qty_pallets=float(pallets_completed),
                entered_by="ADZ",
                notes=f"{production_id} | {notes}",
            )
        except Exception as e:
            print(Color.YELLOW + f"WARNING: Could not post to FG-01.csv ({e})" + Color.RESET)

    print(Color.GREEN + "\n✔ Production saved and labels updated.\n" + Color.RESET)



def record_production() -> None:
    """
    Production entry:
    1) Recommended: Record from ISSUED pallet labels (so ProductionID matches)
    2) Manual entry (original behavior)
    """
    menu_title("Record Production")
    print("1) Record from Issued Labels (recommended)")
    print("2) Manual Entry")
    choice = input("Choose: ").strip()

    if choice == "1":
        record_production_from_issued_labels()
    elif choice == "2":
        _record_production_manual()
    else:
        print(Color.RED + "Invalid choice.\n" + Color.RESET)




def _normalize_consumption_basis(value: str) -> str:
    basis = str(value or "").strip().upper()
    if basis in {"PER_UNIT", "PER_CASE", "PER_PALLET"}:
        return basis
    return "PER_UNIT"


def _build_consumption_preview(
    product_kits: pd.DataFrame,
    units_completed: float,
    pallets_completed: float = 0.0,
) -> list[dict]:
    preview: list[dict] = []
    for _, r in product_kits.iterrows():
        comp_name = str(r.get("Component", "")).strip()
        qty_per_unit = float(pd.to_numeric(r.get("Qty Per Production Unit", 0), errors="coerce") or 0)
        waste = float(pd.to_numeric(r.get("Waste %", 0), errors="coerce") or 0)
        basis = _normalize_consumption_basis(r.get("ConsumptionBasis", "PER_UNIT"))

        if not comp_name or qty_per_unit <= 0:
            continue

        if basis == "PER_PALLET":
            pallet_count = math.ceil(float(pallets_completed)) if float(pallets_completed) > 0 else 0
            needed = float(pallet_count) * qty_per_unit
            waste_used = 0.0
        else:
            # PER_UNIT and PER_CASE both scale from the completed unit count.
            # For case products, units_completed is the case count.
            needed = float(units_completed) * qty_per_unit * (1 + (waste / 100.0))
            waste_used = waste

        source = str(r.get("InventorySource", "")).strip().upper() or ("RM" if is_raw_material_row(r) else "INV")
        usage_uom = str(r.get("UsageUOM", "")).strip()
        preview.append(
            {
                "component": comp_name,
                "needed": needed,
                "qty_per_unit": qty_per_unit,
                "waste": waste_used,
                "source": source,
                "usage_uom": usage_uom,
                "consumption_basis": basis,
            }
        )
    return preview


def _print_consumption_preview(consumption_preview: list[dict]) -> None:
    if not consumption_preview:
        print(" - (No components found in Kits for this product/line)")
        return

    for item in consumption_preview:
        source_label = f" [{item['source']}]" if item.get("source") else ""
        uom_label = f" {item['usage_uom']}" if item.get("usage_uom") else ""
        basis_label = f" ({item.get('consumption_basis', 'PER_UNIT')})"
        print(f" - {item['component']}{source_label}{basis_label}: {item['needed']:.2f}{uom_label}")


def _validate_consumption_availability(consumption_preview: list[dict]) -> list[str]:
    """Return human-readable shortage errors before posting production."""
    inv = load_inventory().copy()
    inv["Component"] = inv.get("Component", pd.Series(dtype=str)).astype(str).str.strip().str.lower() if not inv.empty else pd.Series(dtype=str)
    inv["Quantity"] = pd.to_numeric(inv.get("Quantity", 0.0), errors="coerce").fillna(0.0) if not inv.empty else pd.Series(dtype=float)
    inv_qty_map = inv.groupby("Component")["Quantity"].sum().to_dict() if not inv.empty else {}

    errors: list[str] = []
    for item in consumption_preview:
        comp = str(item.get("component", "")).strip()
        if not comp:
            continue
        needed = float(item.get("needed", 0.0) or 0.0)
        src = str(item.get("source", "INV")).upper()
        if src == "RM":
            available = float(get_raw_material_on_hand(comp))
        else:
            available = float(inv_qty_map.get(comp.lower(), 0.0))
        if needed - available > 1e-9:
            uom = f" {item.get('usage_uom','').strip()}" if str(item.get('usage_uom','')).strip() else ""
            errors.append(f"{comp} [{src}] short by {needed - available:.2f}{uom} (needed {needed:.2f}{uom}, on-hand {available:.2f}{uom})")
    return errors


def _apply_consumption(consumption_preview: list[dict], production_id: str, date_str: str, line: str, product_name: str) -> None:
    for item in consumption_preview:
        comp_name = item["component"]
        needed = float(item["needed"])
        source = str(item.get("source", "INV")).upper()
        usage_uom = str(item.get("usage_uom", "")).strip()

        if source == "RM":
            if not raw_material_exists(comp_name):
                raise ValueError(f"Raw material '{comp_name}' does not exist in RM-BAL-01.")
            adjust_raw_material_quantity(
                component=comp_name,
                delta=-needed,
                reference=production_id,
                notes=f"Line {line} – {product_name}",
                date_received=date_str,
                uom=usage_uom,
            )
        else:
            if not component_exists(comp_name):
                raise ValueError(f"Component '{comp_name}' does not exist in inventory.")
            adjust_inventory_quantity(
                component=comp_name,
                delta=-needed,
                change_type="production_consume",
                reference=production_id,
                notes=f"Line {line} – {product_name}",
                date_received=date_str,
            )



def _record_manual_batch_for_date(df: pd.DataFrame, kits_df: pd.DataFrame, date_str: str, recorded_by: str) -> pd.DataFrame:
    runtime_checked: set[tuple[str, str]] = set()

    while True:
        line = _choose_line()
        if not line:
            return df

        # Select a valid product before writing runtime. This prevents an orphan
        # runtime record when the user cancels or a line has no configured products.
        prod = _choose_product_from_kits(kits_df, line)
        if not prod:
            return df

        runtime_key = (date_str, str(line))
        if runtime_key not in runtime_checked:
            lr.ensure_runtime_for_line_date(date_str, line, entered_by=recorded_by, prompt_if_exists=True)
            runtime_checked.add(runtime_key)

        product_name = str(prod["Finished Product"]).strip()
        product_code = str(prod["ProductCode"]).strip().upper()
        unit_type = str(prod["UnitType"]).strip().lower()
        units_per_pallet = float(pd.to_numeric(prod.get("UnitsPerPallet", 0), errors="coerce") or 0)

        print(Color.GREEN + f"\nSelected Product: {product_name}\n" + Color.RESET)

        units_completed = 0.0
        pallets_completed = 0.0

        if unit_type == "case":
            menu_title("Cases Input")
            print("1) Enter pallets")
            print("2) Enter cases (units)")
            mode = input("Choose (1/2): ").strip()

            if mode == "1":
                pallets_completed = float(numeric_input("Pallets completed: ", allow_float=False))
                units_completed = pallets_completed * units_per_pallet
            else:
                units_completed = float(numeric_input("Cases completed: ", allow_float=False))
                pallets_completed = (units_completed / units_per_pallet) if units_per_pallet > 0 else 0
        else:
            units_completed = float(numeric_input(f"{unit_type.capitalize()}s completed: ", allow_float=False))
            pallets_completed = (units_completed / units_per_pallet) if units_per_pallet > 0 else 0

        notes = input("Notes (optional): ").strip()

        if units_per_pallet > 0:
            remainder = units_completed % units_per_pallet
            if remainder != 0:
                tag = f"PARTIAL PALLET ({int(remainder)} of {int(units_per_pallet)})"
                notes = (notes + " | " + tag).strip(" |") if notes else tag

        production_id = _generate_production_id(df, product_code, date_str)

        product_kits = kits_df[
            (kits_df["Finished Product"].astype(str).str.strip() == product_name)
            & (kits_df["ProductCode"].astype(str).str.strip().str.upper() == product_code)
            & (kits_df["Line"].astype(str).str.strip() == str(line).strip())
        ].copy()

        consumption_preview = _build_consumption_preview(product_kits, units_completed, pallets_completed)

        menu_title("Confirm Production Entry")
        print(f"Production ID : {production_id}")
        print(f"Date          : {date_str}")
        print(f"Line          : {line}")
        print(f"Product       : {product_name} ({product_code})")
        print(f"Unit Type     : {unit_type}")
        print(f"Units         : {units_completed}")
        print(f"Pallets       : {pallets_completed}")

        runtime_rec = lr.get_runtime_record(date_str, str(line))
        if runtime_rec:
            hours_ran = float(pd.to_numeric(runtime_rec.get("HoursRan", 0), errors="coerce") or 0)
            print(f"Run Hours     : {hours_ran:.2f}")
            rt_notes = str(runtime_rec.get("Notes", "")).strip()
            if rt_notes:
                print(f"Runtime Notes : {rt_notes}")

        print("\nInventory to be consumed:")
        _print_consumption_preview(consumption_preview)

        shortage_errors = _validate_consumption_availability(consumption_preview)
        if shortage_errors:
            print(Color.RED + "\nInsufficient stock to post this production:" + Color.RESET)
            for err in shortage_errors:
                print(Color.RED + f" - {err}" + Color.RESET)
            again = input(f"Add another production for {date_str}? (Y/n): ").strip().lower()
            if again in ("n", "no"):
                return df
            continue

        if input("\nConfirm production entry? (y/n): ").strip().lower() != "y":
            print(Color.YELLOW + "\nProduction cancelled. No changes made.\n" + Color.RESET)
        else:
            new_row = {
                "ProductionID": production_id,
                "Date": date_str,
                "Line": str(line),
                "Product": product_name,
                "ProductCode": product_code,
                "UnitType": unit_type,
                "UnitsCompleted": float(units_completed),
                "UnitsPerPallet": float(units_per_pallet),
                "PalletsCompleted": float(pallets_completed),
                "Notes": notes,
            }
            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
            save_production(df)

            try:
                log_audit(
                    module="production",
                    action="RECORD_PRODUCTION_MANUAL",
                    entity_type="Production",
                    entity_id=str(production_id),
                    user=str(recorded_by),
                    details={
                        "Date": date_str,
                        "Line": str(line),
                        "ProductCode": str(product_code),
                        "UnitType": str(unit_type),
                        "PalletsCompleted": float(pallets_completed),
                        "UnitsCompleted": float(units_completed),
                    },
                )
            except Exception:
                pass

            _apply_consumption(consumption_preview, production_id, date_str, line, product_name)

            if float(pallets_completed) > 0:
                try:
                    fg.add_entry(
                        entry_type="PRODUCE",
                        date_str=date_str,
                        product=product_name,
                        product_code=product_code,
                        line=str(line),
                        qty_pallets=float(pallets_completed),
                        entered_by=str(recorded_by),
                        notes=f"{production_id} | Manual production",
                        ref_record_id=str(production_id),
                    )
                except Exception as e:
                    print(Color.YELLOW + f"WARNING: Could not post to FG-01.csv ({e})" + Color.RESET)

            print(Color.GREEN + f"\n✔ Production saved: {production_id}\n" + Color.RESET)

        again = input(f"Add another production for {date_str}? (Y/n): ").strip().lower()
        if again in ("n", "no"):
            return df

def _record_production_manual() -> None:
    """
    Manual production entry with same-date batch loop.
    Uses Kits.csv BOM to consume inventory / raw materials.
    """
    kits_df = load_kits()
    if kits_df.empty:
        print(Color.YELLOW + "\nNo products found in Kits.csv.\n" + Color.RESET)
        return

    required = {
        "Finished Product", "ProductCode", "Line", "UnitType", "UnitsPerPallet",
        "Component", "Qty Per Production Unit", "Waste %"
    }
    missing_cols = [c for c in required if c not in kits_df.columns]
    if missing_cols:
        print(Color.RED + f"\nKits.csv missing required columns: {missing_cols}\n" + Color.RESET)
        return

    df = load_production()
    menu_title("Record Production")

    date_str = parse_date_input("Date (MM-DD-YYYY): ")
    if not date_str:
        print(Color.RED + "Date cannot be empty.\n" + Color.RESET)
        return

    recorded_by = input("Recorded by (initials/name): ").strip() or "UNKNOWN"
    _record_manual_batch_for_date(df, kits_df, date_str, recorded_by)

def view_all_production_history() -> None:
    df = load_production()
    if df.empty:
        print(Color.YELLOW + "\nNo production records.\n" + Color.RESET)
        return

    menu_title("Production History (All)")
    df["_dt"] = pd.to_datetime(df["Date"], format="%m-%d-%Y", errors="coerce")
    df = df.sort_values(by=["_dt", "Line"]).drop(columns=["_dt"], errors="ignore")

    print(df.to_string(index=False))
    print()


def view_production_by_date_range() -> None:
    df = load_production()
    if df.empty:
        print(Color.YELLOW + "\nNo production records.\n" + Color.RESET)
        return

    menu_title("Production History (Date Range)")
    start_date = parse_date_input("Start date (MM-DD-YYYY): ")
    end_date = parse_date_input("End date (MM-DD-YYYY): ")

    df["_dt"] = pd.to_datetime(df["Date"], format="%m-%d-%Y", errors="coerce")
    s = pd.to_datetime(start_date, format="%m-%d-%Y", errors="coerce")
    e = pd.to_datetime(end_date, format="%m-%d-%Y", errors="coerce")

    subset = df[(df["_dt"] >= s) & (df["_dt"] <= e)].copy()
    subset.drop(columns=["_dt"], inplace=True, errors="ignore")

    if subset.empty:
        print(Color.YELLOW + f"\nNo production between {start_date} and {end_date}.\n" + Color.RESET)
        return

    print(subset.to_string(index=False))
    print()


# ------------------------------------------------------------
# Weekly Production Report (keeps your grouped downtime behavior)
# ------------------------------------------------------------
def print_weekly_production_report() -> None:
    menu_title("Weekly Production Report")

    start_date = parse_date_input("Start date (MM-DD-YYYY): ")
    end_date = parse_date_input("End date (MM-DD-YYYY): ")

    prod = load_production()
    if prod.empty:
        print(Color.YELLOW + "\nNo production data.\n" + Color.RESET)
        return

    prod["_dt"] = pd.to_datetime(prod["Date"], format="%m-%d-%Y", errors="coerce")
    s = pd.to_datetime(start_date, format="%m-%d-%Y", errors="coerce")
    e = pd.to_datetime(end_date, format="%m-%d-%Y", errors="coerce")
    prod = prod[(prod["_dt"] >= s) & (prod["_dt"] <= e)].copy()
    prod.drop(columns=["_dt"], inplace=True, errors="ignore")

    if prod.empty:
        print(Color.YELLOW + "\nNo production data in selected range.\n" + Color.RESET)
        return

    runtime_df = lr.load_runtime_by_date_range(start_date, end_date)
    line_names = load_line_names()
    downtime_df = load_downtime_for_report(start_date, end_date)

    for line in sorted(prod["Line"].astype(str).unique()):
        line_df = prod[prod["Line"].astype(str) == line]
        runtime_line = runtime_df[runtime_df["Line"].astype(str).str.strip() == str(line).strip()].copy() if not runtime_df.empty else pd.DataFrame()

        line_label = line_names.get(line, "")
        header = f"Line {line}"
        if line_label:
            header += f" – {line_label}"

        print("\n" + "-" * 60)
        print(f"## 🔹 {header}\n")

        total_pallets = 0
        total_units = 0

        for product, g in line_df.groupby("Product"):
            unit_type = str(g["UnitType"].iloc[0]).strip().lower()

            if unit_type == "case":
                pallets = int(pd.to_numeric(g["PalletsCompleted"], errors="coerce").fillna(0).sum())
                total_pallets += pallets
                print(f"- {product}: {pallets} pallets completed")
            else:
                units = int(pd.to_numeric(g["UnitsCompleted"], errors="coerce").fillna(0).sum())
                total_units += units
                print(f"- {product}: {units} units completed")

        if total_pallets:
            print(f"\nTotal pallets {header}: {total_pallets}")
        else:
            print(f"\nTotal units {header}: {total_units}")

        total_hours = float(pd.to_numeric(runtime_line.get("HoursRan", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()) if not runtime_line.empty else 0.0
        if total_hours > 0:
            print(f"Total run hours {header}: {total_hours:.2f}")
            if total_pallets:
                print(f"Average rate {header}: {total_pallets / total_hours:.2f} pallets/hour")
            else:
                print(f"Average rate {header}: {total_units / total_hours:.2f} units/hour")
        else:
            print(f"Total run hours {header}: N/A (no runtime logged)")

        notes_rows = runtime_line[runtime_line["Notes"].astype(str).str.strip() != ""] if not runtime_line.empty and "Notes" in runtime_line.columns else pd.DataFrame()
        if not notes_rows.empty:
            print("\n📝 Runtime notes")
            for _, rr in notes_rows.iterrows():
                dt = str(rr.get("Date", "")).strip()
                note = str(rr.get("Notes", "")).strip()
                print(f"- {dt}: {note}")

        print_grouped_downtime(downtime_df, line)

    print("\nEnd of report.\n")


# ------------------------------------------------------------
# Optional: Historic line performance (cases only)
# ------------------------------------------------------------
def historic_line_performance_cases() -> None:
    df = load_production()
    if df.empty:
        print(Color.YELLOW + "\nNo production data available.\n" + Color.RESET)
        return

    df["UnitType"] = df["UnitType"].astype(str).str.strip().str.lower()
    df = df[df["UnitType"] == "case"].copy()
    if df.empty:
        print(Color.YELLOW + "\nNo case-based production found.\n" + Color.RESET)
        return

    df["PalletsCompleted"] = pd.to_numeric(df["PalletsCompleted"], errors="coerce").fillna(0).astype(float)
    daily = df.groupby(["Line", "Date"], as_index=False)["PalletsCompleted"].sum()

    menu_title("Historic Line Performance (Cases Only)")

    for line in sorted(daily["Line"].astype(str).unique()):
        line_df = daily[daily["Line"].astype(str) == str(line)]
        days_with_data = len(line_df)
        total_pallets = float(line_df["PalletsCompleted"].sum())
        max_pallets = float(line_df["PalletsCompleted"].max())
        avg_pallets = total_pallets / days_with_data if days_with_data else 0.0

        print(f"Line {line}")
        print(f"  Max pallets in one day: {int(max_pallets)}")
        print(f"  Historic daily average: {avg_pallets:.2f} pallets/day")
        print(f"  Days with production: {days_with_data}\n")
