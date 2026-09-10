"""
shipping.py

Simple, append-only Shipping ledger (SHP-01.csv)
- Each row is a shipping transaction line item (one product code per row).
- For future robustness, rows can share ShipmentID to represent a multi-line shipment.

Guardrails:
- Cannot ship more pallets than available in Finished Goods (FG-01).
- No destructive edits; corrections are reversal entries.

ISO-friendly principles:
- Append-only records
- Who/when fields
- Reversal/correction entries instead of edits
"""

from __future__ import annotations

from datetime import datetime
import uuid
import pandas as pd

from file_utils import load_csv_strip, save_csv
from audit import log_audit
from helpers import Color, menu_title, parse_date_input, numeric_input, confirm
import finished_goods as fg

SHP_FILE = "SHP-01.csv"

SHP_COLUMNS = [
    "RecordID",
    "EntryType",      # SHIP / REVERSAL
    "RefRecordID",
    "ShipmentID",
    "Timestamp",
    "DateShipped",    # MM-DD-YYYY
    "Customer",
    "Carrier",
    "Product",
    "ProductCode",
    "PalletsShipped", # positive number (EntryType=SHIP), reversal uses negative
    "EnteredBy",
    "Notes",
]


def load_shipments() -> pd.DataFrame:
    df = load_csv_strip(SHP_FILE, headers_default=SHP_COLUMNS)
    for c in SHP_COLUMNS:
        if c not in df.columns:
            df[c] = ""
    df["PalletsShipped"] = pd.to_numeric(df["PalletsShipped"], errors="coerce").fillna(0.0)
    return df


def save_shipments(df: pd.DataFrame) -> None:
    df = df.copy()
    for c in SHP_COLUMNS:
        if c not in df.columns:
            df[c] = ""
    df = df[SHP_COLUMNS]
    save_csv(df, SHP_FILE)


def _new_shipment_id() -> str:
    return "SHP-" + datetime.now().strftime("%y%m%d") + "-" + str(uuid.uuid4())[:8].upper()

def select_product_from_finished_goods() -> tuple[str, str, float] | None:
    """Search finished goods on-hand and let user choose a product.

    Returns (product_code, product_name, on_hand_pallets) or None if user cancels.
    """
    df = fg.current_on_hand()
    if df.empty:
        print(Color.YELLOW + "No finished goods on-hand to ship." + Color.RESET)
        return None

    # Ensure consistent types
    df = df.copy()
    df["ProductCode"] = df["ProductCode"].astype(str).str.strip().str.upper()
    df["Product"] = df["Product"].astype(str).str.strip()
    df["OnHandPallets"] = pd.to_numeric(df["OnHandPallets"], errors="coerce").fillna(0.0)

    while True:
        q = input("Search product (name or code) (blank=cancel): ").strip()
        if not q:
            return None

        qn = q.strip().lower()
        matches = df[
            df["ProductCode"].str.lower().str.contains(qn, na=False)
            | df["Product"].str.lower().str.contains(qn, na=False)
        ].copy()

        if matches.empty:
            print(Color.RED + "No matches. Try again." + Color.RESET)
            continue

        matches = matches.sort_values(["ProductCode"]).head(25).reset_index(drop=True)

        print("\nMatches (showing up to 25):")
        for i, row in matches.iterrows():
            code = row["ProductCode"]
            name = row["Product"]
            on_hand = float(row["OnHandPallets"])
            print(f"  {i+1:>2}) {code} | {name} | On-hand pallets: {on_hand:g}")
        print("   0) Search again")

        choice = input("Choose number: ").strip()
        if choice == "0":
            continue
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(matches):
                r = matches.iloc[idx]
                return (str(r["ProductCode"]).strip().upper(), str(r["Product"]).strip(), float(r["OnHandPallets"]))
        except ValueError:
            pass

        print(Color.RED + "Invalid choice." + Color.RESET)



def _available_after_pending(product_code: str, on_hand: float, pending_by_code: dict[str, float]) -> float:
    return float(on_hand) - float(pending_by_code.get(str(product_code).strip().upper(), 0.0))


def _save_shipment_rows(shipment_id: str, date_str: str, entered_by: str, rows_to_write: list[dict], fg_posts: list[dict]) -> None:
    if not rows_to_write:
        return

    print("\nSummary:")
    print(f"  ShipmentID: {shipment_id}")
    print(f"  Date: {date_str}")
    print(f"  Lines: {len(rows_to_write)}")
    if not confirm("Save shipment entries?"):
        print(Color.YELLOW + "Cancelled. Nothing saved." + Color.RESET)
        return

    ship_df = load_shipments()
    new_df = pd.DataFrame(rows_to_write)
    ship_df = pd.concat([ship_df, new_df], ignore_index=True)
    save_shipments(ship_df)

    for post in fg_posts:
        fg.add_entry(
            entry_type="SHIP",
            ref_record_id=post["ref_record_id"],
            date_str=post["date_str"],
            product=post["product"],
            product_code=post["product_code"],
            line="",
            qty_pallets=post["qty_pallets"],
            entered_by=post["entered_by"],
            notes=post["notes"],
        )

    print(Color.GREEN + "✔ Shipment recorded and finished goods reduced." + Color.RESET)


def _build_shipment_row(*, shipment_id: str, date_str: str, customer: str, carrier: str, product_name: str, product_code: str, pallets: float, entered_by: str, notes: str) -> tuple[dict, dict]:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rid = str(uuid.uuid4())
    ship_row = {
        "RecordID": rid,
        "EntryType": "SHIP",
        "RefRecordID": "",
        "ShipmentID": shipment_id,
        "Timestamp": ts,
        "DateShipped": date_str,
        "Customer": customer,
        "Carrier": carrier,
        "Product": product_name,
        "ProductCode": product_code,
        "PalletsShipped": float(pallets),
        "EnteredBy": entered_by,
        "Notes": notes,
    }
    fg_post = {
        "date_str": date_str,
        "product": product_name,
        "product_code": product_code,
        "qty_pallets": -float(pallets),
        "entered_by": entered_by,
        "notes": f"Shipment {shipment_id}" + (f" | {notes}" if notes else ""),
        "ref_record_id": rid,
    }
    return ship_row, fg_post


def quick_ship_batch() -> None:
    """
    Fast shipping entry:
    - date defaults to today
    - entered_by once
    - repeat product search + pallet qty until blank search cancels
    """
    menu_title("Quick Ship Batch")
    date_str = parse_date_input("Ship date (MM-DD-YYYY) [ENTER=today]: ")
    entered_by = input("Entered by (initials/name): ").strip() or "UNKNOWN"
    notes = input("Batch notes (optional): ").strip()

    shipment_id = _new_shipment_id()
    rows_to_write: list[dict] = []
    fg_posts: list[dict] = []
    pending_by_code: dict[str, float] = {}

    while True:
        print("")
        picked = select_product_from_finished_goods()
        if picked is None:
            if not rows_to_write:
                print(Color.YELLOW + "No products added. Shipment cancelled." + Color.RESET)
            break

        product_code, product_name, on_hand = picked
        available_now = _available_after_pending(product_code, on_hand, pending_by_code)
        if available_now <= 0:
            print(Color.RED + f"No remaining on-hand pallets available for {product_code} in this batch." + Color.RESET)
            continue

        pallets = numeric_input(f"Pallets shipped for {product_code} (available now {available_now:g}): ")
        if pallets <= 0:
            print(Color.RED + "Pallets must be greater than 0." + Color.RESET)
            continue
        if pallets > available_now:
            print(Color.RED + f"Cannot ship {pallets} pallets. Only {available_now:g} pallets remain available for {product_code} in this batch." + Color.RESET)
            continue

        ship_row, fg_post = _build_shipment_row(
            shipment_id=shipment_id,
            date_str=date_str,
            customer="",
            carrier="",
            product_name=product_name,
            product_code=product_code,
            pallets=pallets,
            entered_by=entered_by,
            notes=notes,
        )
        rows_to_write.append(ship_row)
        fg_posts.append(fg_post)
        pending_by_code[product_code] = pending_by_code.get(product_code, 0.0) + float(pallets)

        more = input("Add another product to this shipment? (Y/n): ").strip().lower()
        if more in ("n", "no"):
            break

    _save_shipment_rows(shipment_id, date_str, entered_by, rows_to_write, fg_posts)

def record_shipment() -> None:
    """Choose shipping entry mode."""
    menu_title("Shipping Entry")
    print("1) Quick Ship Batch (recommended)")
    print("2) Full Shipment Entry")
    print("3) Back")
    choice = input("Choose: ").strip()

    if choice == "1":
        quick_ship_batch()
        return
    if choice == "2":
        _record_full_shipment()
        return
    if choice == "3":
        return

    print(Color.RED + "Invalid choice." + Color.RESET)


def _record_full_shipment() -> None:
    """
    Create shipping ledger entries (SHP-01) and post negative FG entries (FG-01).
    """
    menu_title("Record Shipment (Append-only)")
    date_str = parse_date_input("Date shipped (MM-DD-YYYY): ")
    if not date_str:
        print(Color.RED + "Date cannot be empty." + Color.RESET)
        return

    customer = input("Customer (optional for now): ").strip()
    carrier = input("Carrier / Shipper (optional for now): ").strip()
    entered_by = input("Entered by (initials/name): ").strip() or "UNKNOWN"
    notes = input("Notes (optional): ").strip()

    shipment_id = _new_shipment_id()
    rows_to_write: list[dict] = []
    fg_posts: list[dict] = []
    pending_by_code: dict[str, float] = {}

    while True:
        print("")
        picked = select_product_from_finished_goods()
        if picked is None:
            if not rows_to_write:
                print(Color.YELLOW + "No products added. Shipment cancelled." + Color.RESET)
            break

        product_code, product_name, on_hand = picked

        available_now = _available_after_pending(product_code, on_hand, pending_by_code)
        if available_now <= 0:
            print(Color.RED + f"No remaining on-hand pallets available for {product_code} in this shipment." + Color.RESET)
            continue

        pallets = numeric_input(f"Pallets shipped for {product_code} (available now {available_now:g}): ")
        if pallets <= 0:
            print(Color.RED + "Pallets must be greater than 0." + Color.RESET)
            continue

        if pallets > available_now:
            print(
                Color.RED
                + f"Cannot ship {pallets} pallets. Only {available_now:g} pallets remain available for {product_code} in this shipment."
                + Color.RESET
            )
            continue

        ship_row, fg_post = _build_shipment_row(
            shipment_id=shipment_id,
            date_str=date_str,
            customer=customer,
            carrier=carrier,
            product_name=product_name,
            product_code=product_code,
            pallets=pallets,
            entered_by=entered_by,
            notes=notes,
        )
        rows_to_write.append(ship_row)
        fg_posts.append(fg_post)
        pending_by_code[product_code] = pending_by_code.get(product_code, 0.0) + float(pallets)

        more = input("Add another product to this shipment? (Y/n): ").strip().lower()
        if more in ("n", "no"):
            break

    if not rows_to_write:
        return

    _save_shipment_rows(shipment_id, date_str, entered_by, rows_to_write, fg_posts)


def reverse_shipment() -> None:
    """
    Append a reversal entry for a prior shipment line, and add pallets back into FG.
    """
    menu_title("Reverse Shipment Entry")
    df = load_shipments()
    if df.empty:
        print(Color.YELLOW + "No shipments to reverse.\n" + Color.RESET)
        return

    view = df.tail(25).copy()
    view["PalletsShipped"] = view["PalletsShipped"].astype(float)
    print(view[["RecordID", "DateShipped", "ShipmentID", "ProductCode", "PalletsShipped", "EnteredBy"]].to_string(index=False))
    print()

    target = input("Enter RecordID to reverse: ").strip()
    hit = df[df["RecordID"].astype(str) == target]
    if hit.empty:
        print(Color.RED + "RecordID not found.\n" + Color.RESET)
        return

    r = hit.iloc[0].to_dict()
    pallets = float(r.get("PalletsShipped", 0.0))
    product_code = str(r.get("ProductCode", "")).strip().upper()
    product_name = str(r.get("Product", "")).strip()
    date_str = str(r.get("DateShipped", "")).strip()

    entered_by = input("Reversed by (initials/name): ").strip() or "UNKNOWN"
    notes = input("Reversal reason (required): ").strip()
    if not notes:
        print(Color.RED + "Reason is required.\n" + Color.RESET)
        return

    print("\nSummary:")
    print(f"  Reversing shipment line: {r.get('ShipmentID')} {product_code} Qty {pallets}")
    print(f"  This will add back {pallets} pallets into Finished Goods.")

    if not confirm("\nConfirm reversal entry?"):
        print(Color.YELLOW + "Cancelled. No changes made.\n" + Color.RESET)
        return

    rid = str(uuid.uuid4())
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    reversal_row = {
        "RecordID": rid,
        "EntryType": "REVERSAL",
        "RefRecordID": target,
        "ShipmentID": str(r.get("ShipmentID", "")).strip(),
        "Timestamp": ts,
        "DateShipped": date_str,
        "Customer": str(r.get("Customer", "")).strip(),
        "Carrier": str(r.get("Carrier", "")).strip(),
        "Product": product_name,
        "ProductCode": product_code,
        "PalletsShipped": -pallets,
        "EnteredBy": entered_by,
        "Notes": notes,
    }

    df = pd.concat([df, pd.DataFrame([reversal_row])], ignore_index=True)
    save_shipments(df)

    # Global audit log (append-only)
    try:
        log_audit(
            module="shipping",
            action="REVERSE_SHIPMENT",
            entity_type="Shipment",
            entity_id=str(rid),
            user=str(entered_by),
            details={
                "Date": date_str,
                "OriginalRecordID": str(target),
                "ShipmentID": str(r.get("ShipmentID", "")),
                "ProductCode": str(product_code),
                "PalletsRestored": float(pallets),
                "Reason": str(notes),
            },
        )
    except Exception:
        pass

    # Post to FG ledger as +pallets
    fg.add_entry(
        entry_type="REVERSAL",
        date_str=date_str,
        product=product_name,
        product_code=product_code,
        line="",
        qty_pallets=+pallets,
        entered_by=entered_by,
        notes=f"Reversal of shipment line {target} | {notes}",
        ref_record_id=rid,
    )

    print(Color.GREEN + "\n✔ Shipment reversal recorded and finished goods restored.\n" + Color.RESET)