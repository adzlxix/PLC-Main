"""
finished_goods.py

Append-only Finished Goods ledger (FG-01.csv)

Purpose:
- Track finished pallets on the floor as a **ledger** (not an editable inventory table).
- Production adds +pallets
- Shipping removes -pallets
- Corrections are done via reversal/correction entries (no destructive edits)

ISO-friendly principles:
- Append-only records
- Who/when fields
- Reversal entries instead of edits
"""

from __future__ import annotations

from datetime import datetime
import uuid
import pandas as pd

from file_utils import load_csv_strip, save_csv
from audit import log_audit
from helpers import Color, menu_title, parse_date_input, numeric_input, confirm
from kits import load_kits

FG_FILE = "FG-01.csv"

FG_COLUMNS = [
    "RecordID",
    "EntryType",          # PRODUCE / SHIP / ADJUST / REVERSAL
    "RefRecordID",        # RecordID being reversed (if EntryType=REVERSAL)
    "Timestamp",          # YYYY-MM-DD HH:MM:SS
    "Date",               # MM-DD-YYYY (business date)
    "Product",
    "ProductCode",
    "Line",
    "QtyPallets",         # + adds to floor, - removes from floor
    "EnteredBy",
    "Notes",
]


def load_fg() -> pd.DataFrame:
    df = load_csv_strip(FG_FILE, headers_default=FG_COLUMNS)
    for c in FG_COLUMNS:
        if c not in df.columns:
            df[c] = ""
    df["QtyPallets"] = pd.to_numeric(df["QtyPallets"], errors="coerce").fillna(0.0)
    return df


def save_fg(df: pd.DataFrame) -> None:
    df = df.copy()
    for c in FG_COLUMNS:
        if c not in df.columns:
            df[c] = ""
    df = df[FG_COLUMNS]
    save_csv(df, FG_FILE)


def current_on_hand(product_code: str | None = None) -> pd.DataFrame:
    """
    Return a DataFrame with on-hand pallets by ProductCode/Product.
    If product_code is provided, returns only that product.
    """
    df = load_fg()
    if df.empty:
        return pd.DataFrame(columns=["ProductCode", "Product", "OnHandPallets"])

    grp = (
        df.groupby(["ProductCode", "Product"], dropna=False)["QtyPallets"]
        .sum()
        .reset_index()
        .rename(columns={"QtyPallets": "OnHandPallets"})
    )
    grp["OnHandPallets"] = pd.to_numeric(grp["OnHandPallets"], errors="coerce").fillna(0.0)

    if product_code:
        pc = str(product_code).strip().upper()
        grp = grp[grp["ProductCode"].astype(str).str.upper() == pc]

    return grp.sort_values(["ProductCode", "Product"]).reset_index(drop=True)


def add_entry(
    *,
    entry_type: str,
    date_str: str,
    product: str,
    product_code: str,
    line: str,
    qty_pallets: float,
    entered_by: str,
    notes: str = "",
    ref_record_id: str = "",
) -> str:
    df = load_fg()
    rid = str(uuid.uuid4())
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    row = {
        "RecordID": rid,
        "EntryType": str(entry_type).strip().upper(),
        "RefRecordID": str(ref_record_id).strip(),
        "Timestamp": ts,
        "Date": str(date_str).strip(),
        "Product": str(product).strip(),
        "ProductCode": str(product_code).strip().upper(),
        "Line": str(line).strip(),
        "QtyPallets": float(qty_pallets),
        "EnteredBy": str(entered_by).strip() or "UNKNOWN",
        "Notes": str(notes).strip(),
    }

    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    save_fg(df)

    # Global audit log (append-only)
    try:
        log_audit(
            module="finished_goods",
            action=f"FG_{str(entry_type).upper()}",
            entity_type="FGEntry",
            entity_id=str(rid),
            user=str(entered_by),
            details={
                "Date": date_str,
                "Line": str(line),
                "ProductCode": str(product_code),
                "QtyPallets": float(qty_pallets),
                "Reference": str(ref_record_id),
                "Notes": str(notes),
            },
        )
    except Exception:
        pass

    return rid


def view_on_hand() -> None:
    menu_title("Finished Goods On-Hand (FG-01)")
    oh = current_on_hand()
    if oh.empty:
        print(Color.YELLOW + "No finished goods records yet.\n" + Color.RESET)
        return
    print(oh.to_string(index=False))
    print()




def _known_products_for_adjustment() -> pd.DataFrame:
    rows = []

    fg_df = load_fg()
    if not fg_df.empty:
        base = fg_df[["ProductCode", "Product", "Line"]].copy()
        rows.append(base)

    try:
        kits_df = load_kits()
        if not kits_df.empty:
            needed = kits_df[["ProductCode", "Finished Product", "Line"]].drop_duplicates().copy()
            needed = needed.rename(columns={"Finished Product": "Product"})
            rows.append(needed)
    except Exception:
        pass

    if not rows:
        return pd.DataFrame(columns=["ProductCode", "Product", "Line", "OnHandPallets"])

    combined = pd.concat(rows, ignore_index=True).fillna("")
    combined["ProductCode"] = combined["ProductCode"].astype(str).str.strip().str.upper()
    combined["Product"] = combined["Product"].astype(str).str.strip()
    combined["Line"] = combined["Line"].astype(str).str.strip()
    combined = combined[(combined["ProductCode"] != "") | (combined["Product"] != "")].drop_duplicates()

    on_hand = current_on_hand()
    if on_hand.empty:
        combined["OnHandPallets"] = 0.0
        return combined.sort_values(["ProductCode", "Product"]).reset_index(drop=True)

    on_hand = on_hand.copy()
    on_hand["ProductCode"] = on_hand["ProductCode"].astype(str).str.strip().str.upper()
    on_hand["Product"] = on_hand["Product"].astype(str).str.strip()
    on_hand["OnHandPallets"] = pd.to_numeric(on_hand["OnHandPallets"], errors="coerce").fillna(0.0)

    merged = combined.merge(on_hand, on=["ProductCode", "Product"], how="left")
    merged["OnHandPallets"] = pd.to_numeric(merged["OnHandPallets"], errors="coerce").fillna(0.0)
    return merged.sort_values(["ProductCode", "Product"]).reset_index(drop=True)


def select_product_for_adjustment() -> tuple[str, str, str, float] | None:
    """Search known products and return (product_code, product_name, line, on_hand)."""
    df = _known_products_for_adjustment()
    if df.empty:
        print(Color.YELLOW + "No products available to select." + Color.RESET)
        return None

    while True:
        q = input("Search product (name or code) (blank=cancel): ").strip()
        if not q:
            return None

        qn = q.lower()
        matches = df[
            df["ProductCode"].str.lower().str.contains(qn, na=False)
            | df["Product"].str.lower().str.contains(qn, na=False)
        ].copy()

        if matches.empty:
            print(Color.RED + "No matches. Try again." + Color.RESET)
            continue

        matches = matches.sort_values(["ProductCode", "Product"]).head(25).reset_index(drop=True)
        print("\nMatches (showing up to 25):")
        for i, row in matches.iterrows():
            code = row["ProductCode"]
            name = row["Product"]
            line = row.get("Line", "")
            on_hand = float(row.get("OnHandPallets", 0.0) or 0.0)
            line_part = f" | Line {line}" if str(line).strip() else ""
            print(f"  {i+1:>2}) {code} | {name}{line_part} | On-hand pallets: {on_hand:g}")
        print("   0) Search again")

        choice = input("Choose number: ").strip()
        if choice == "0":
            continue
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(matches):
                r = matches.iloc[idx]
                return (
                    str(r["ProductCode"]).strip().upper(),
                    str(r["Product"]).strip(),
                    str(r.get("Line", "")).strip(),
                    float(pd.to_numeric(r.get("OnHandPallets", 0.0), errors="coerce") or 0.0),
                )
        except ValueError:
            pass

        print(Color.RED + "Invalid choice." + Color.RESET)

def record_adjustment() -> None:
    """
    Rare use: adjustment entry. Still append-only.
    Use this only for cycle counts / reconciliations.
    """
    menu_title("Finished Goods Adjustment (Ledger Entry)")
    date_str = parse_date_input("Date (MM-DD-YYYY): ")
    if not date_str:
        print(Color.RED + "Date cannot be empty.\n" + Color.RESET)
        return

    picked = select_product_for_adjustment()
    if not picked:
        print(Color.YELLOW + "Cancelled. No changes made.\n" + Color.RESET)
        return

    product_code, product, default_line, on_hand = picked
    print(f"Selected: {product} ({product_code}) | On-hand pallets: {on_hand:g}")
    line = input(f"Line (optional) [ENTER to keep {default_line or 'blank'}]: ").strip() or default_line
    qty = numeric_input("Adjustment pallets (+/-): ")
    entered_by = input("Entered by (initials/name): ").strip() or "UNKNOWN"
    notes = input("Reason / notes (required): ").strip()

    if not notes:
        print(Color.RED + "Notes are required for adjustments.\n" + Color.RESET)
        return

    print("\nSummary:")
    print(f"  Product: {product} ({product_code})")
    print(f"  Qty: {qty} pallets")
    print(f"  Reason: {notes}")

    if not confirm("\nConfirm adjustment entry?"):
        print(Color.YELLOW + "Cancelled. No changes made.\n" + Color.RESET)
        return

    add_entry(
        entry_type="ADJUST",
        date_str=date_str,
        product=product,
        product_code=product_code,
        line=line,
        qty_pallets=qty,
        entered_by=entered_by,
        notes=notes,
    )
    print(Color.GREEN + "\n✔ Adjustment recorded in FG-01.\n" + Color.RESET)


def reverse_entry() -> None:
    """
    Create a reversal entry that negates a prior FG record (no edits).
    """
    menu_title("Reverse Finished Goods Entry")
    df = load_fg()
    if df.empty:
        print(Color.YELLOW + "No FG records to reverse.\n" + Color.RESET)
        return

    # Show recent entries
    view = df.tail(25).copy()
    view["QtyPallets"] = view["QtyPallets"].astype(float)
    print(view[["RecordID", "EntryType", "Date", "ProductCode", "QtyPallets", "EnteredBy"]].to_string(index=False))
    print()

    target = input("Enter RecordID to reverse: ").strip()
    hit = df[df["RecordID"].astype(str) == target]
    if hit.empty:
        print(Color.RED + "RecordID not found.\n" + Color.RESET)
        return

    r = hit.iloc[0].to_dict()
    entered_by = input("Reversed by (initials/name): ").strip() or "UNKNOWN"
    notes = input("Reversal reason (required): ").strip()
    if not notes:
        print(Color.RED + "Reason is required.\n" + Color.RESET)
        return

    qty = float(r.get("QtyPallets", 0.0))
    date_str = str(r.get("Date", "")).strip() or parse_date_input("Date (MM-DD-YYYY): ")

    print("\nSummary:")
    print(f"  Reversing: {r.get('EntryType')} {r.get('ProductCode')} Qty {qty}")
    print(f"  New entry will be: {(-qty)} pallets (REVERSAL)")
    if not confirm("\nConfirm reversal entry?"):
        print(Color.YELLOW + "Cancelled. No changes made.\n" + Color.RESET)
        return

    add_entry(
        entry_type="REVERSAL",
        date_str=date_str,
        product=str(r.get("Product", "")),
        product_code=str(r.get("ProductCode", "")),
        line=str(r.get("Line", "")),
        qty_pallets=-qty,
        entered_by=entered_by,
        notes=notes,
        ref_record_id=target,
    )
    print(Color.GREEN + "\n✔ Reversal recorded (append-only).\n" + Color.RESET)


def set_finished_goods_count() -> None:
    """
    Set a finished good to an exact physical pallet count.
    Keeps FG-01 append-only by adding an ADJUST entry for the difference.
    """
    menu_title("Set Finished Goods Count / Stocktake")
    picked = select_product_for_adjustment()
    if not picked:
        print(Color.YELLOW + "Cancelled. No changes made.\n" + Color.RESET)
        return

    product_code, product, default_line, on_hand = picked
    print(f"Selected: {product} ({product_code})")
    print(f"Current system on-hand: {on_hand:g} pallets\n")

    date_str = parse_date_input("Count Date (MM-DD-YYYY):")
    actual = numeric_input("Actual physical pallets on hand:", allow_float=True)
    line = input(f"Line (optional) [ENTER to keep {default_line or 'blank'}]: ").strip() or default_line
    entered_by = input("Entered by (initials/name): ").strip() or "UNKNOWN"
    notes = input("Notes (optional): ").strip() or "Finished goods stocktake set count"

    delta = float(actual) - float(on_hand)
    print("\nSummary:")
    print(f"  Current system count: {on_hand:g} pallets")
    print(f"  Actual count: {actual:g} pallets")
    print(f"  Adjustment entry: {delta:g} pallets")

    if not confirm("Confirm set count?"):
        print(Color.YELLOW + "Cancelled. No changes made.\n" + Color.RESET)
        return

    if abs(delta) < 1e-9:
        print(Color.GREEN + "\n✔ Count already matches. No entry needed.\n" + Color.RESET)
        return

    add_entry(
        entry_type="ADJUST",
        date_str=date_str,
        product=product,
        product_code=product_code,
        line=line,
        qty_pallets=delta,
        entered_by=entered_by,
        notes=notes,
    )
    print(Color.GREEN + "\n✔ Finished goods count set via adjustment entry.\n" + Color.RESET)
