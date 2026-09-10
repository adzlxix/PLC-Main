"""
code_mapping.py

Keeps QuickBooks Item Code as the master code.
Names/descriptions may change for ease, but matching must be done by CODE only.
"""

from __future__ import annotations
import os
import pandas as pd

from file_utils import load_csv_strip, save_csv
from helpers import Color, menu_title, confirm

CODEMAP_FILE = "CodeMap-01.csv"
CODEMAP_COLUMNS = ["LegacyCode", "QBCode", "DisplayName", "Source", "Status", "Notes"]


def load_map() -> pd.DataFrame:
    df = load_csv_strip(CODEMAP_FILE, headers_default=CODEMAP_COLUMNS)
    for c in CODEMAP_COLUMNS:
        if c not in df.columns:
            df[c] = ""
    df["LegacyCode"] = df["LegacyCode"].astype(str).str.strip().str.upper()
    df["QBCode"] = df["QBCode"].astype(str).str.strip().str.upper()
    return df


def save_map(df: pd.DataFrame) -> None:
    save_csv(df[CODEMAP_COLUMNS], CODEMAP_FILE)


def _legacy_codes() -> pd.DataFrame:
    rows = []
    def add(code, name, source):
        code = str(code or "").strip().upper()
        if not code or code == "NAN":
            return
        rows.append({"LegacyCode": code, "DisplayName": str(name or "").strip(), "Source": source})

    for file, code_col, name_col in [
        ("INV-01.csv", "ComponentCode", "Component"),
        ("FG-01.csv", "ProductCode", "Product"),
        ("RM-BAL-01.csv", "MaterialCode", "Material"),
        ("Kits.csv", "ProductCode", "Finished Product"),
        ("Kits.csv", "ComponentCode", "Component"),
    ]:
        try:
            df = load_csv_strip(file)
            if code_col in df.columns:
                for _, r in df.iterrows():
                    add(r.get(code_col), r.get(name_col, ""), file)
        except Exception:
            pass
    out = pd.DataFrame(rows)
    if out.empty:
        return pd.DataFrame(columns=["LegacyCode", "DisplayName", "Source"])
    out = out.drop_duplicates(subset=["LegacyCode"]).sort_values("LegacyCode")
    return out


def _qb_items_from_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.columns = df.columns.str.strip()
    # Common QB export columns: Item, Description
    item_col = "Item" if "Item" in df.columns else df.columns[0]
    desc_col = "Description" if "Description" in df.columns else item_col
    out = pd.DataFrame({
        "QBCode": df[item_col].astype(str).str.strip().str.upper(),
        "QBName": df[desc_col].astype(str).str.strip(),
    })
    out = out[(out["QBCode"] != "") & (out["QBCode"] != "NAN")].drop_duplicates("QBCode")
    return out


def build_from_quickbooks_item_csv() -> None:
    menu_title("Build Code Map From QuickBooks Item List")
    path = input("Path to QuickBooks item list CSV (ex: item list.CSV): ").strip().strip('"')
    if not path or not os.path.exists(path):
        print(Color.RED + "File not found.\n" + Color.RESET)
        return

    qb = _qb_items_from_csv(path)
    legacy = _legacy_codes()
    existing = load_map()

    existing_pairs = set(zip(existing["LegacyCode"], existing["QBCode"]))
    rows = []
    qb_codes = set(qb["QBCode"].tolist())
    for _, r in legacy.iterrows():
        lc = str(r["LegacyCode"]).upper()
        status = "MATCHED" if lc in qb_codes else "NEEDS MAP"
        qbcode = lc if lc in qb_codes else ""
        if (lc, qbcode) not in existing_pairs:
            rows.append({
                "LegacyCode": lc,
                "QBCode": qbcode,
                "DisplayName": r.get("DisplayName", ""),
                "Source": r.get("Source", ""),
                "Status": status,
                "Notes": "Auto-generated. QBCode is master.",
            })
    combined = pd.concat([existing, pd.DataFrame(rows)], ignore_index=True)
    combined = combined.drop_duplicates(subset=["LegacyCode"], keep="first")
    save_map(combined)

    matched = int((combined["Status"] == "MATCHED").sum())
    needs = int((combined["Status"] == "NEEDS MAP").sum())
    print(Color.GREEN + f"\n✔ CodeMap updated: {len(combined)} rows. Matched: {matched}. Needs map: {needs}.\n" + Color.RESET)


def view_summary() -> None:
    df = load_map()
    menu_title("Code Mapping Summary")
    if df.empty:
        print(Color.YELLOW + "No CodeMap rows yet. Build from QuickBooks item list first.\n" + Color.RESET)
        return
    print(df["Status"].value_counts(dropna=False).to_string())
    print("\nNeeds mapping examples:")
    view = df[df["Status"].astype(str).str.upper().isin(["NEEDS MAP", ""])].head(30)
    if view.empty:
        print("  None")
    else:
        print(view[["LegacyCode", "QBCode", "DisplayName", "Source", "Status"]].to_string(index=False))
    print()


def manual_map_code() -> None:
    df = load_map()
    if df.empty:
        print(Color.YELLOW + "No CodeMap rows yet. Build/import first.\n" + Color.RESET)
        return
    q = input("Search legacy code/name to map: ").strip().lower()
    if not q:
        return
    matches = df[
        df["LegacyCode"].astype(str).str.lower().str.contains(q, na=False)
        | df["DisplayName"].astype(str).str.lower().str.contains(q, na=False)
    ].copy().reset_index()
    if matches.empty:
        print(Color.YELLOW + "No matches.\n" + Color.RESET)
        return
    for i, r in matches.head(30).iterrows():
        print(f"{i+1}) {r['LegacyCode']} -> {r.get('QBCode','')} | {r.get('DisplayName','')} | {r.get('Status','')}")
    choice = input("Choose row: ").strip()
    if not choice.isdigit():
        return
    idx = int(choice) - 1
    if idx < 0 or idx >= min(len(matches), 30):
        print(Color.RED + "Invalid choice.\n" + Color.RESET)
        return
    original = matches.loc[idx, "index"]
    qb = input("Correct QuickBooks Item Code: ").strip().upper()
    if not qb:
        return
    note = input("Notes (optional): ").strip()
    df.loc[original, "QBCode"] = qb
    df.loc[original, "Status"] = "MAPPED"
    if note:
        df.loc[original, "Notes"] = note
    save_map(df)
    print(Color.GREEN + "\n✔ Mapping saved. Remember: code is the master, not item name.\n" + Color.RESET)


def export_needs_mapping() -> None:
    df = load_map()
    out = df[df["Status"].astype(str).str.upper().isin(["NEEDS MAP", ""])].copy()
    path = "codes_needing_mapping.csv"
    out.to_csv(path, index=False)
    print(Color.GREEN + f"\n✔ Exported: {path}\n" + Color.RESET)


def code_mapping_menu() -> None:
    while True:
        menu_title("Code Mapping / QB Reconciliation")
        print("1) Build/update CodeMap from QuickBooks item list CSV")
        print("2) View summary")
        print("3) Manually map a legacy code to QB code")
        print("4) Export codes needing mapping")
        print("5) Back")
        choice = input("Choose: ").strip()
        if choice == "1":
            build_from_quickbooks_item_csv()
        elif choice == "2":
            view_summary()
        elif choice == "3":
            manual_map_code()
        elif choice == "4":
            export_needs_mapping()
        elif choice == "5":
            break
        else:
            print(Color.RED + "Invalid choice.\n" + Color.RESET)
