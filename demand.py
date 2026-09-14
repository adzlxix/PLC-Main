"""
demand.py

Demand calculation and reorder reporting.

Reorder policy:
- Reorder Point (ROP) = calculated daily component usage x 28 days.
- 28 days is a fixed four-week stock horizon.
- Daily component usage comes from LineCapacity.csv and Kits.csv.
- For each component, demand uses the MAX requirement on each line, then SUMS
  those line requirements across lines.
- Waste % from Kits.csv is included.
- A line with 0 pallets/day has no defined demand. Items used only on zero-capacity
  lines are flagged "NO DAILY OUTPUT" instead of being treated as a meaningful 0 ROP.

Exports:
- Low-stock CSV
- Email-ready TXT summary

Compatibility:
- Provides load_line_capacity() and edit_line_capacity() for main.py / health_check.py.
"""

from __future__ import annotations

from datetime import datetime
import os
import pandas as pd

from file_utils import load_csv_strip, save_csv, normalize_id, normalize_id_series
from helpers import Color, menu_title

INVENTORY_FILE = "INV-01.csv"
KITS_FILE = "Kits.csv"
LINE_CAPACITY_FILE = "LineCapacity.csv"
LINE_SETTINGS_FILE = "LineSettings.csv"
LOW_STOCK_EXPORT_DIR = "low_stock_reports"
REORDER_HORIZON_DAYS = 28

def _norm_line(value) -> str:
    return normalize_id(value)



def load_line_capacity() -> pd.DataFrame:
    try:
        return load_csv_strip(LINE_CAPACITY_FILE)
    except Exception:
        return pd.DataFrame()


def load_line_settings() -> dict:
    try:
        df = load_csv_strip(LINE_SETTINGS_FILE)
        if df.empty:
            return {}
        if "Line" in df.columns and "LineName" in df.columns:
            out = {}
            for _, r in df.iterrows():
                k = normalize_id(r["Line"])
                v = str(r["LineName"]).strip()
                if k and v:
                    out[k] = v
            return out
        return {}
    except Exception:
        return {}


def edit_line_capacity() -> None:
    """Edit the normal daily output assumption for each line, in pallets/day."""
    menu_title("Edit Daily Line Output")
    df = load_line_capacity()

    if df.empty:
        df = pd.DataFrame(
            {"Line": ["1", "2", "3", "4"], "MaxPalletsPerDay": [0.0, 0.0, 0.0, 0.0]}
        )
    else:
        if "Line" not in df.columns:
            df["Line"] = ""
        if "MaxPalletsPerDay" not in df.columns:
            df["MaxPalletsPerDay"] = 0.0

    df["Line"] = normalize_id_series(df["Line"])
    df["MaxPalletsPerDay"] = pd.to_numeric(
        df["MaxPalletsPerDay"], errors="coerce"
    ).fillna(0.0)

    line_names = load_line_settings()

    print("\nThese values drive the 4-week reorder point calculation.")
    print("ROP = daily component usage x 28 days\n")
    print("Current daily outputs:")
    for _, r in df.iterrows():
        line = str(r["Line"])
        name = line_names.get(line, "")
        label = f"Line {line}" + (f" – {name}" if name else "")
        print(f"  {label}: {float(r['MaxPalletsPerDay']):.2f} pallets/day")

    print("\nEnter updates (press ENTER to keep the current value).")
    for i in range(len(df)):
        line = str(df.loc[i, "Line"])
        name = line_names.get(line, "")
        label = f"Line {line}" + (f" – {name}" if name else "")
        current = float(df.loc[i, "MaxPalletsPerDay"])
        new_val = input(f"{label} [{current:.2f}]: ").strip()
        if new_val == "":
            continue
        try:
            value = float(new_val)
            if value < 0:
                raise ValueError
            df.loc[i, "MaxPalletsPerDay"] = value
        except ValueError:
            print(Color.RED + "Invalid number — skipped.\n" + Color.RESET)

    save_csv(df, LINE_CAPACITY_FILE)
    print(Color.GREEN + "\n✔ Daily line outputs updated.\n" + Color.RESET)


def calculate_daily_usage():
    """
    Calculate expected daily component usage.

    MAX per line avoids adding mutually-exclusive products that run on the same line.
    SUM across lines accounts for the same component being consumed on multiple lines.

    Returns:
        final_usage: dict[str, float]
        usage_explain: dict[str, dict[str, dict]]
    """
    kits = load_csv_strip(KITS_FILE)
    caps = load_csv_strip(LINE_CAPACITY_FILE)

    final_usage: dict[str, float] = {}
    usage_explain: dict[str, dict[str, dict]] = {}

    if kits.empty or caps.empty:
        return final_usage, usage_explain

    caps = caps.copy()
    caps["Line"] = caps["Line"].map(_norm_line)
    caps["MaxPalletsPerDay"] = pd.to_numeric(
        caps["MaxPalletsPerDay"], errors="coerce"
    ).fillna(0.0)

    for _, kit in kits.iterrows():
        component = str(kit.get("Component", "")).strip()
        line = _norm_line(kit.get("Line", ""))
        product = str(kit.get("Finished Product", "")).strip()

        if not component or not line:
            continue

        cap_row = caps[caps["Line"] == line]
        if cap_row.empty:
            continue

        pallets_day = float(cap_row.iloc[0]["MaxPalletsPerDay"])
        if pallets_day <= 0:
            continue

        units_per_pallet = pd.to_numeric(pd.Series([kit.get("UnitsPerPallet", 1)]), errors="coerce").fillna(1).iloc[0]
        qty_per_unit = pd.to_numeric(pd.Series([kit.get("Qty Per Production Unit", 1)]), errors="coerce").fillna(1).iloc[0]
        waste = pd.to_numeric(pd.Series([kit.get("Waste %", 0)]), errors="coerce").fillna(0).iloc[0] / 100.0

        daily = float(pallets_day) * float(units_per_pallet) * float(qty_per_unit) * (1 + float(waste))

        usage_explain.setdefault(component, {})
        prev = float(usage_explain[component].get(line, {}).get("daily", 0) or 0)

        if daily > prev:
            usage_explain[component][line] = {
                "product": product,
                "daily": daily,
                "pallets": pallets_day,
                "units_per_pallet": float(units_per_pallet),
                "qty_per_unit": float(qty_per_unit),
                "waste": float(waste),
            }

    for comp, lines in usage_explain.items():
        final_usage[comp] = sum(v["daily"] for v in lines.values())

    return final_usage, usage_explain


def _components_on_zero_output_lines() -> set[str]:
    """Components whose kits exist only on lines with no daily output configured."""
    kits = load_csv_strip(KITS_FILE)
    caps = load_csv_strip(LINE_CAPACITY_FILE)
    if kits.empty or caps.empty:
        return set()

    caps = caps.copy()
    caps["Line"] = caps["Line"].map(_norm_line)
    caps["MaxPalletsPerDay"] = pd.to_numeric(caps["MaxPalletsPerDay"], errors="coerce").fillna(0)
    cap_map = dict(zip(caps["Line"], caps["MaxPalletsPerDay"]))

    lines_by_component: dict[str, set[str]] = {}
    for _, r in kits.iterrows():
        comp = str(r.get("Component", "")).strip()
        line = _norm_line(r.get("Line", ""))
        if comp and line:
            lines_by_component.setdefault(comp, set()).add(line)

    out = set()
    for comp, lines in lines_by_component.items():
        if lines and all(float(cap_map.get(line, 0) or 0) <= 0 for line in lines):
            out.add(comp)
    return out


def build_reorder_table() -> pd.DataFrame:
    inv = load_csv_strip(INVENTORY_FILE)
    daily_usage, _ = calculate_daily_usage()
    no_output = _components_on_zero_output_lines()

    if inv.empty:
        return pd.DataFrame()

    rows = []
    for _, row in inv.iterrows():
        component = str(row.get("Component", "")).strip()
        if not component:
            continue
        on_hand = float(pd.to_numeric(pd.Series([row.get("Quantity", 0)]), errors="coerce").fillna(0).iloc[0])
        daily = float(daily_usage.get(component, 0) or 0)
        rop = daily * REORDER_HORIZON_DAYS
        shortage = max(rop - on_hand, 0.0)
        days_on_hand = (on_hand / daily) if daily > 0 else None

        if component in no_output:
            status = "NO DAILY OUTPUT"
        elif daily <= 0:
            status = "NO DEMAND"
        elif on_hand < rop:
            status = "LOW STOCK"
        else:
            status = "OK"

        rows.append({
            "Component": component,
            "ComponentCode": str(row.get("ComponentCode", "")).strip(),
            "ComponentType": str(row.get("ComponentType", "")).strip(),
            "OnHand": on_hand,
            "DailyUsage": daily,
            "ReorderPoint_4Weeks": rop,
            "DaysOnHand": days_on_hand,
            "ShortageToROP": shortage,
            "Status": status,
        })

    return pd.DataFrame(rows)


def sync_reorder_points_to_inventory() -> None:
    """Write the calculated 28-day ROP into INV-01.csv for other dashboards/reports."""
    inv = load_csv_strip(INVENTORY_FILE)
    table = build_reorder_table()
    if inv.empty or table.empty:
        return

    rop_map = table.set_index("Component")["ReorderPoint_4Weeks"].to_dict()
    status_map = table.set_index("Component")["Status"].to_dict()
    inv["ReorderPoint"] = inv["Component"].map(rop_map)
    # Do not show a misleading numeric 0 for configured kits on zero-output lines.
    inv.loc[inv["Component"].map(status_map).eq("NO DAILY OUTPUT"), "ReorderPoint"] = pd.NA
    save_csv(inv, INVENTORY_FILE)


def reorder_report(low_stock_only: bool = False):
    menu_title("Low Stock Report" if low_stock_only else "Full Reorder Report")

    table = build_reorder_table()
    _, explain = calculate_daily_usage()
    if table.empty:
        print(Color.YELLOW + "\nNo inventory data.\n" + Color.RESET)
        return

    sync_reorder_points_to_inventory()

    for _, row in table.iterrows():
        status = row["Status"]
        if low_stock_only and status != "LOW STOCK":
            continue

        component = row["Component"]
        on_hand = float(row["OnHand"])
        daily = float(row["DailyUsage"])
        rop = float(row["ReorderPoint_4Weeks"])
        color = Color.RED if status == "LOW STOCK" else (Color.YELLOW if status == "NO DAILY OUTPUT" else Color.GREEN)

        print("\n" + "=" * 55)
        print(color + f"Component: {component}" + Color.RESET)
        print(f"Status: {status}")
        print(f"On hand: {on_hand:.2f}")

        if status == "NO DAILY OUTPUT":
            print("ROP: NOT CALCULATED — set daily output for this item's line in Settings.")
            if low_stock_only:
                continue
        else:
            print(f"Daily usage: {daily:.2f}")
            print(f"4-week ROP: {rop:.2f}")
            if daily > 0:
                print(f"Days on hand: {float(row['DaysOnHand']):.1f}")

        if low_stock_only:
            continue

        if component in explain:
            print("\nDemand drivers:")
            for line in sorted(explain[component].keys(), key=lambda x: (len(x), x)):
                d = explain[component][line]
                waste_pct = int(round(float(d["waste"]) * 100))
                formula = (
                    f"{d['pallets']:.0f} pallets/day × {d['units_per_pallet']:.0f} units/pallet × "
                    f"{d['qty_per_unit']:.2f}/unit × (1 + {waste_pct}%) = {d['daily']:.2f}/day"
                )
                print(f"  Line {line} – {d['product']}")
                print(f"    {formula}")

            print("\nROP calculation:")
            print(f"  {daily:.2f}/day × {REORDER_HORIZON_DAYS} days = {rop:.2f}")

    print("\nEnd of report.\n")


def export_low_stock_report() -> tuple[str, str] | tuple[None, None]:
    """Create a CSV plus an email-ready text summary for all items below the 4-week ROP."""
    table = build_reorder_table()
    if table.empty:
        print(Color.YELLOW + "\nNo inventory data.\n" + Color.RESET)
        return None, None

    sync_reorder_points_to_inventory()

    low = table[table["Status"] == "LOW STOCK"].copy()
    low = low.sort_values(["DaysOnHand", "Component"], na_position="last")
    missing = table[table["Status"] == "NO DAILY OUTPUT"].copy().sort_values("Component")

    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    folder = os.path.join(LOW_STOCK_EXPORT_DIR, stamp)
    os.makedirs(folder, exist_ok=True)

    csv_path = os.path.join(folder, "low_stock_items.csv")
    txt_path = os.path.join(folder, "low_stock_email.txt")

    export_cols = [
        "Component", "ComponentCode", "ComponentType", "OnHand", "DailyUsage",
        "ReorderPoint_4Weeks", "DaysOnHand", "ShortageToROP"
    ]
    low[export_cols].to_csv(csv_path, index=False)

    lines = []
    lines.append("Low Stock Items – 4 Week Reorder Point")
    lines.append("")
    lines.append(f"Reorder policy: 28 days of expected production usage.")
    lines.append(f"Items below ROP: {len(low)}")
    lines.append("")
    if low.empty:
        lines.append("No items are currently below the 4-week reorder point.")
    else:
        lines.append("Item | On Hand | 4-Week ROP | Shortage | Days On Hand")
        lines.append("-" * 78)
        for _, r in low.iterrows():
            doh = "" if pd.isna(r["DaysOnHand"]) else f"{float(r['DaysOnHand']):.1f}"
            lines.append(
                f"{r['Component']} | {float(r['OnHand']):.0f} | "
                f"{float(r['ReorderPoint_4Weeks']):.0f} | {float(r['ShortageToROP']):.0f} | {doh}"
            )

    if not missing.empty:
        lines.append("")
        lines.append("Daily output still needs to be configured for these items' production lines:")
        for comp in missing["Component"].tolist():
            lines.append(f"- {comp}")

    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(Color.GREEN + f"\n✔ Low-stock CSV created: {csv_path}" + Color.RESET)
    print(Color.GREEN + f"✔ Email-ready summary created: {txt_path}\n" + Color.RESET)
    if not missing.empty:
        print(Color.YELLOW + f"⚠ {len(missing)} components are on lines with 0 daily output and do not yet have a valid ROP." + Color.RESET)
        print("Update them under Settings / Admin → Edit Daily Line Output.\n")

    return csv_path, txt_path
