"""
raw_materials.py

Raw-material ledger support.

Design:
- RM-01.csv remains the append-only receiving log.
- RM-01-Usage.csv is the append-only production/adjustment usage log.
- RM-BAL-01.csv is the current on-hand balance file used by production and reporting.

Source of truth:
- Receipts come from RM-01.csv (Accepted only)
- Usage comes from RM-01-Usage.csv
- RM-BAL-01.csv is rebuilt from those logs after each RM receipt / usage event
"""

from __future__ import annotations

from datetime import datetime
import pandas as pd

from file_utils import load_csv_strip, save_csv

RM_RECEIPT_FILE = "RM-01.csv"
RM_USAGE_FILE = "RM-01-Usage.csv"
RM_BAL_FILE = "RM-BAL-01.csv"

RM_USAGE_COLUMNS = [
    "Timestamp",
    "BusinessDate",
    "Material",
    "MaterialCode",
    "DeltaQty",
    "UOM",
    "Reference",
    "Notes",
]

RM_BAL_COLUMNS = [
    "Material",
    "MaterialCode",
    "Quantity",
    "UOM",
    "LastUpdated",
    "Notes",
]

RAW_HINTS = {"raw material", "raw_material", "rm", "bulk", "liquid", "chemical"}


def _norm_text(value) -> str:
    if pd.isna(value):
        return ""
    s = str(value).strip()
    if s.lower() == "nan":
        return ""
    return s


def _norm_key(value) -> str:
    return _norm_text(value).lower()


def _ensure_usage() -> pd.DataFrame:
    df = load_csv_strip(RM_USAGE_FILE, headers_default=RM_USAGE_COLUMNS)
    for c in RM_USAGE_COLUMNS:
        if c not in df.columns:
            df[c] = ""
    df["DeltaQty"] = pd.to_numeric(df["DeltaQty"], errors="coerce").fillna(0.0)
    return df[RM_USAGE_COLUMNS].copy()


def _ensure_balance() -> pd.DataFrame:
    df = load_csv_strip(RM_BAL_FILE, headers_default=RM_BAL_COLUMNS)
    for c in RM_BAL_COLUMNS:
        if c not in df.columns:
            df[c] = ""
    df["Quantity"] = pd.to_numeric(df["Quantity"], errors="coerce").fillna(0.0)
    return df[RM_BAL_COLUMNS].copy()


def save_usage(df: pd.DataFrame) -> None:
    out = df.copy()
    for c in RM_USAGE_COLUMNS:
        if c not in out.columns:
            out[c] = ""
    save_csv(out[RM_USAGE_COLUMNS], RM_USAGE_FILE)


def save_balance(df: pd.DataFrame) -> None:
    out = df.copy()
    for c in RM_BAL_COLUMNS:
        if c not in out.columns:
            out[c] = ""
    out["Quantity"] = pd.to_numeric(out["Quantity"], errors="coerce").fillna(0.0)
    save_csv(out[RM_BAL_COLUMNS], RM_BAL_FILE)


def is_raw_material_row(kit_row) -> bool:
    source = _norm_text(kit_row.get("InventorySource", "")).upper()
    if source == "RM":
        return True
    ctype = _norm_text(kit_row.get("ComponentType", "")).lower()
    return ctype in RAW_HINTS


def rebuild_rm_balance_from_logs() -> pd.DataFrame:
    receipts = load_csv_strip(RM_RECEIPT_FILE)
    usage = _ensure_usage()
    bal_map: dict[str, dict] = {}

    if not receipts.empty:
        work = receipts.copy()
        for col in ["Material Name", "Material Code", "Material Category", "Quantity", "Unit", "Inspection Status", "Date", "Notes"]:
            if col not in work.columns:
                work[col] = ""
        work = work[work["Inspection Status"].astype(str).str.strip().str.lower() == "accepted"].copy()
        if "Material Category" in work.columns:
            work = work[work["Material Category"].astype(str).str.strip().str.lower() == "raw material"].copy()
        if not work.empty:
            work["Material"] = work["Material Name"].map(_norm_text)
            work["MaterialCode"] = work["Material Code"].map(_norm_text)
            work["UOM"] = work["Unit"].map(_norm_text)
            work["Quantity"] = pd.to_numeric(work["Quantity"], errors="coerce").fillna(0.0)
            work["BusinessDate"] = work["Date"].map(_norm_text)
            work["Notes"] = work["Notes"].map(_norm_text)
            work["_key"] = work["Material"].map(_norm_key)
            grp = work.groupby(["_key", "Material", "MaterialCode", "UOM"], dropna=False, as_index=False)
            rec_sum = grp.agg(Quantity=("Quantity", "sum"), LastUpdated=("BusinessDate", "last"), Notes=("Notes", "last"))
            for _, r in rec_sum.iterrows():
                key = _norm_key(r.get("Material", ""))
                if not key:
                    continue
                bal_map[key] = {
                    "Material": _norm_text(r.get("Material", "")),
                    "MaterialCode": _norm_text(r.get("MaterialCode", "")),
                    "Quantity": float(r.get("Quantity", 0.0) or 0.0),
                    "UOM": _norm_text(r.get("UOM", "")),
                    "LastUpdated": _norm_text(r.get("LastUpdated", "")),
                    "Notes": _norm_text(r.get("Notes", "")),
                }

    if not usage.empty:
        u = usage.copy()
        u["Material"] = u["Material"].map(_norm_text)
        u["MaterialCode"] = u["MaterialCode"].map(_norm_text)
        u["UOM"] = u["UOM"].map(_norm_text)
        u["BusinessDate"] = u["BusinessDate"].map(_norm_text)
        u["Notes"] = u["Notes"].map(_norm_text)
        u["DeltaQty"] = pd.to_numeric(u["DeltaQty"], errors="coerce").fillna(0.0)
        for _, r in u.iterrows():
            key = _norm_key(r.get("Material", ""))
            if not key:
                continue
            if key not in bal_map:
                bal_map[key] = {
                    "Material": _norm_text(r.get("Material", "")),
                    "MaterialCode": _norm_text(r.get("MaterialCode", "")),
                    "Quantity": 0.0,
                    "UOM": _norm_text(r.get("UOM", "")),
                    "LastUpdated": _norm_text(r.get("BusinessDate", "")),
                    "Notes": "",
                }
            bal_map[key]["Quantity"] = float(bal_map[key].get("Quantity", 0.0)) + float(r.get("DeltaQty", 0.0) or 0.0)
            if _norm_text(r.get("MaterialCode", "")) and not _norm_text(bal_map[key].get("MaterialCode", "")):
                bal_map[key]["MaterialCode"] = _norm_text(r.get("MaterialCode", ""))
            if _norm_text(r.get("UOM", "")) and not _norm_text(bal_map[key].get("UOM", "")):
                bal_map[key]["UOM"] = _norm_text(r.get("UOM", ""))
            if _norm_text(r.get("BusinessDate", "")):
                bal_map[key]["LastUpdated"] = _norm_text(r.get("BusinessDate", ""))
            if _norm_text(r.get("Notes", "")):
                bal_map[key]["Notes"] = _norm_text(r.get("Notes", ""))

    out = pd.DataFrame(list(bal_map.values()), columns=RM_BAL_COLUMNS)
    if out.empty:
        out = pd.DataFrame(columns=RM_BAL_COLUMNS)
    else:
        out["Quantity"] = pd.to_numeric(out["Quantity"], errors="coerce").fillna(0.0)
        out = out.sort_values(by=["Material"]).reset_index(drop=True)
    save_balance(out)
    return out


def load_rm_balance(rebuild_if_missing: bool = True) -> pd.DataFrame:
    if rebuild_if_missing:
        return rebuild_rm_balance_from_logs()
    return _ensure_balance()


def get_raw_material_on_hand(material: str) -> float:
    material_key = _norm_key(material)
    if not material_key:
        return 0.0
    bal = load_rm_balance(rebuild_if_missing=True)
    if bal.empty:
        return 0.0
    bal["_key"] = bal["Material"].map(_norm_key)
    match = bal[bal["_key"] == material_key]
    if match.empty:
        return 0.0
    return float(pd.to_numeric(match.iloc[0].get("Quantity", 0.0), errors="coerce") or 0.0)


def raw_material_exists(material: str) -> bool:
    bal = load_rm_balance(rebuild_if_missing=True)
    if bal.empty:
        return False
    keys = set(bal["Material"].map(_norm_key).tolist())
    return _norm_key(material) in keys


def get_raw_material_code(material: str) -> str:
    material_key = _norm_key(material)
    bal = load_rm_balance(rebuild_if_missing=True)
    if bal.empty:
        return ""
    bal["_key"] = bal["Material"].map(_norm_key)
    match = bal[bal["_key"] == material_key]
    if match.empty:
        return ""
    return _norm_text(match.iloc[0].get("MaterialCode", ""))


def record_raw_material_receipt(*, material: str, material_code: str, quantity: float, unit: str, business_date: str, notes: str = "") -> pd.DataFrame:
    _ = material, material_code, quantity, unit, business_date, notes
    return rebuild_rm_balance_from_logs()


def adjust_raw_material_quantity(*, component: str, delta: float, reference: str = "", notes: str = "", date_received: str | None = None, uom: str = "") -> float:
    component = _norm_text(component)
    if not component:
        raise ValueError("Raw material name cannot be empty.")
    delta = float(delta)
    current_qty = get_raw_material_on_hand(component)
    # Negative balances are allowed so production can be recorded before late receiving entries are backfilled.
    usage = _ensure_usage()
    row = {
        "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "BusinessDate": _norm_text(date_received) or datetime.now().strftime("%m-%d-%Y"),
        "Material": component,
        "MaterialCode": get_raw_material_code(component),
        "DeltaQty": delta,
        "UOM": _norm_text(uom),
        "Reference": _norm_text(reference),
        "Notes": _norm_text(notes),
    }
    usage = pd.concat([usage, pd.DataFrame([row])], ignore_index=True)
    save_usage(usage)
    rebuild_rm_balance_from_logs()
    return get_raw_material_on_hand(component)


def view_rm_balance() -> None:
    bal = load_rm_balance(rebuild_if_missing=True)
    if bal.empty:
        print("\nNo RM-BAL-01 records found.\n")
        return
    display = bal.copy()
    display["Quantity"] = pd.to_numeric(display["Quantity"], errors="coerce").fillna(0.0)
    print(display.to_string(index=False))


def view_rm_usage_log() -> None:
    usage = _ensure_usage()
    if usage.empty:
        print("\nNo RM-01-Usage records found.\n")
        return
    print(usage.to_string(index=False))
