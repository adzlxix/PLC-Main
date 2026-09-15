"""
monthly_reports.py

Generate clean monthly inventory CSV reports without touching QuickBooks.

Pricing/costing rule:
- QuickBooks item code is the master matching key.
- Item/product names can be changed in the Python tracker.
- QB Cost/Price are matched by code only, never by name.
"""

from __future__ import annotations
from datetime import datetime
import os
import pandas as pd

from file_utils import load_csv_strip
from helpers import Color, menu_title, parse_date_input
from inventory_status import with_status
import finished_goods
import demand

REPORTS_DIR = "monthly_reports"
QB_EXPORT_DIR = "qb_exports"
QB_ITEM_LIST_FILE = os.path.join(QB_EXPORT_DIR, "item list.CSV")


def _safe_name(value: str) -> str:
    return str(value).replace("/", "-").replace("\\", "-").replace(" ", "_")


def _to_number(series) -> pd.Series:
    return pd.to_numeric(
        series.astype(str)
        .str.replace("$", "", regex=False)
        .str.replace(",", "", regex=False)
        .str.strip(),
        errors="coerce",
    ).fillna(0.0)


def load_qb_pricing() -> pd.DataFrame:
    """Load QuickBooks item costs/prices by item code only."""
    if not os.path.exists(QB_ITEM_LIST_FILE):
        return pd.DataFrame(columns=["QBCode", "QBCost", "QBPrice", "QBDescription", "QBType", "QBPreferredVendor"])

    # QB Desktop CSV exports can contain non-UTF characters, so use latin1.
    try:
        qb = pd.read_csv(QB_ITEM_LIST_FILE, encoding="latin1")
    except Exception:
        try:
            qb = pd.read_csv(QB_ITEM_LIST_FILE, encoding="cp1252")
        except Exception:
            return pd.DataFrame(columns=["QBCode", "QBCost", "QBPrice", "QBDescription", "QBType", "QBPreferredVendor"])

    for col in ["Item", "Description", "Type", "Cost", "Price", "Preferred Vendor"]:
        if col not in qb.columns:
            qb[col] = ""

    out = qb[["Item", "Description", "Type", "Cost", "Price", "Preferred Vendor"]].copy()
    out = out.rename(
        columns={
            "Item": "QBCode",
            "Description": "QBDescription",
            "Type": "QBType",
            "Cost": "QBCost",
            "Price": "QBPrice",
            "Preferred Vendor": "QBPreferredVendor",
        }
    )
    out["QBCode"] = out["QBCode"].astype(str).str.strip().str.upper()
    out["QBCost"] = _to_number(out["QBCost"])
    out["QBPrice"] = _to_number(out["QBPrice"])
    out = out[out["QBCode"] != ""].drop_duplicates(subset=["QBCode"], keep="first")
    return out.reset_index(drop=True)


def add_qb_pricing(df: pd.DataFrame, code_col: str, qty_col: str | None = None, value_col: str = "InventoryValue") -> pd.DataFrame:
    """Add QB Cost/Price fields by matching code_col to QB item code."""
    out = df.copy()
    if code_col not in out.columns:
        out["QBCost"] = 0.0
        out["QBPrice"] = 0.0
        out["QBPriceMatch"] = "NO CODE COLUMN"
        return out

    qb = load_qb_pricing()
    out["_MatchCode"] = out[code_col].astype(str).str.strip().str.upper()
    merged = out.merge(qb, left_on="_MatchCode", right_on="QBCode", how="left")
    merged["QBCost"] = pd.to_numeric(merged.get("QBCost", 0), errors="coerce").fillna(0.0)
    merged["QBPrice"] = pd.to_numeric(merged.get("QBPrice", 0), errors="coerce").fillna(0.0)
    merged["QBPriceMatch"] = merged["QBCode"].apply(lambda x: "MATCHED" if str(x).strip() else "NO QB MATCH")

    if qty_col and qty_col in merged.columns:
        merged[qty_col] = pd.to_numeric(merged[qty_col], errors="coerce").fillna(0.0)
        merged[value_col] = merged[qty_col] * merged["QBCost"]

    return merged.drop(columns=["_MatchCode", "QBCode"], errors="ignore")


def generate_monthly_inventory_report() -> None:
    menu_title("Generate Monthly Inventory Report")
    as_of = parse_date_input("Report date / month-end (MM-DD-YYYY):")
    folder = os.path.join(REPORTS_DIR, _safe_name(as_of))
    os.makedirs(folder, exist_ok=True)

    qb_pricing = load_qb_pricing()
    pricing_loaded = not qb_pricing.empty

    # Keep monthly inventory status aligned to the same dynamic 4-week ROP used in Reports.
    demand.sync_reorder_points_to_inventory()
    inv = with_status(load_csv_strip("INV-01.csv"))
    fg = finished_goods.current_on_hand()
    rm_bal = load_csv_strip("RM-BAL-01.csv")

    if not inv.empty:
        inv_export = inv.copy()
        inv_export = add_qb_pricing(inv_export, code_col="ComponentCode", qty_col="Quantity", value_col="InventoryValue")
        inv_export.to_csv(os.path.join(folder, "components_inventory.csv"), index=False)

        raw_mask = inv_export["ComponentType"].astype(str).str.lower().str.contains("raw|material|bulk|chemical", na=False)
        inv_export[raw_mask].to_csv(os.path.join(folder, "raw_materials_from_inventory.csv"), index=False)
        inv_export[~raw_mask].to_csv(os.path.join(folder, "components_only.csv"), index=False)
        inv_export[inv_export["Status"].isin(["NEGATIVE", "ZERO", "REORDER", "LOW", "NO MIN SET"])].to_csv(
            os.path.join(folder, "inventory_status_attention.csv"), index=False
        )

    if not fg.empty:
        fg_export = fg.copy()
        # Note: FG ledger is stored in pallets. Value is only exact if QB cost is also per pallet.
        # If QB cost is per case/drum, use QBCost as reference and don't treat FG_EstimatedValue as accounting valuation.
        fg_export = add_qb_pricing(fg_export, code_col="ProductCode", qty_col="OnHandPallets", value_col="FG_EstimatedValue")
        fg_export["ValuationNote"] = "FG value = OnHandPallets x QB cost; verify QB cost unit before using for accounting."
        fg_export.to_csv(os.path.join(folder, "finished_goods_on_hand.csv"), index=False)

    if not rm_bal.empty:
        rm_export = rm_bal.copy()
        rm_export = add_qb_pricing(rm_export, code_col="MaterialCode", qty_col="Quantity", value_col="InventoryValue")
        rm_export.to_csv(os.path.join(folder, "raw_material_balance.csv"), index=False)

    summary_rows = []
    summary_rows.append({"Section": "QuickBooks Pricing", "Metric": "Pricing File Loaded", "Value": "YES" if pricing_loaded else "NO"})
    summary_rows.append({"Section": "QuickBooks Pricing", "Metric": "QB Item Cost Rows", "Value": len(qb_pricing)})

    if not inv.empty:
        inv_priced = add_qb_pricing(inv.copy(), code_col="ComponentCode", qty_col="Quantity", value_col="InventoryValue")
        counts = inv_priced["Status"].value_counts().to_dict()
        for status, count in counts.items():
            summary_rows.append({"Section": "Inventory Status", "Metric": status, "Value": count})
        summary_rows.append({"Section": "Inventory Value", "Metric": "Components/Inventory Value", "Value": round(float(inv_priced["InventoryValue"].sum()), 2)})
        summary_rows.append({"Section": "QuickBooks Pricing", "Metric": "Component Rows Missing QB Price Match", "Value": int((inv_priced["QBPriceMatch"] != "MATCHED").sum())})

    if not fg.empty:
        fg_priced = add_qb_pricing(fg.copy(), code_col="ProductCode", qty_col="OnHandPallets", value_col="FG_EstimatedValue")
        summary_rows.append({"Section": "Finished Goods", "Metric": "Product Rows", "Value": len(fg_priced)})
        summary_rows.append({"Section": "Finished Goods", "Metric": "Total Pallets", "Value": float(fg_priced["OnHandPallets"].sum())})
        summary_rows.append({"Section": "Finished Goods", "Metric": "Estimated Value", "Value": round(float(fg_priced["FG_EstimatedValue"].sum()), 2)})
        summary_rows.append({"Section": "QuickBooks Pricing", "Metric": "FG Rows Missing QB Price Match", "Value": int((fg_priced["QBPriceMatch"] != "MATCHED").sum())})

    if not rm_bal.empty:
        rm_priced = add_qb_pricing(rm_bal.copy(), code_col="MaterialCode", qty_col="Quantity", value_col="InventoryValue")
        summary_rows.append({"Section": "Inventory Value", "Metric": "Raw Material Balance Value", "Value": round(float(rm_priced["InventoryValue"].sum()), 2)})
        summary_rows.append({"Section": "QuickBooks Pricing", "Metric": "Raw Material Rows Missing QB Price Match", "Value": int((rm_priced["QBPriceMatch"] != "MATCHED").sum())})

    pd.DataFrame(summary_rows).to_csv(os.path.join(folder, "summary.csv"), index=False)

    print(Color.GREEN + f"\n✔ Monthly report created in: {folder}\n" + Color.RESET)
    print("Files created:")
    for fn in sorted(os.listdir(folder)):
        print(f"  - {fn}")
    print()
    if pricing_loaded:
        print(Color.GREEN + "✔ QB Cost/Price added by item code match only.\n" + Color.RESET)
    else:
        print(Color.YELLOW + "⚠ QB item list not found at qb_exports/item list.CSV. Report created without pricing.\n" + Color.RESET)
