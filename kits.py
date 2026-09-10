"""
kits.py

Manages:
- Kits.csv (BOM / Finished Products)
- Add/Edit products and components
- Improved viewing & component reuse
"""

from typing import Optional, Tuple, List

import pandas as pd

from file_utils import load_csv_strip, save_csv
from helpers import Color, menu_title, numeric_input, confirm
from component_type_manager import get_component_types, add_new_component_type
from inventory import add_or_update_inventory_component, load_inventory
from raw_materials import load_rm_balance, get_raw_material_code
from line_utils import choose_line as choose_configured_line

KITS_FILE = "Kits.csv"

KITS_COLUMNS = [
    "Finished Product",
    "ProductCode",
    "Line",
    "UnitType",            # case / drum / bucket / tote
    "UnitsPerPallet",
    "Component",
    "ComponentCode",
    "ComponentType",
    "Qty Per Production Unit",
    "ConsumptionBasis",      # PER_UNIT / PER_CASE / PER_PALLET
    "Waste %",
    "InventorySource",     # optional: INV / RM
    "UsageUOM",            # optional: ea / gal / lb
]


def pretty_print_kits(df):
    """
    Read-only, grouped visual view for Kits.csv
    """
    for product, group in df.groupby("Finished Product"):
        line = group["Line"].iloc[0]
        unit = group["UnitType"].iloc[0]

        print("\n" + "=" * 50)
        print(f"PRODUCT: {product}")
        print(f"Line: {line} | Unit Type: {unit}")
        print("=" * 50)

        print(f"{'Component':30} {'Code':15} {'Basis':12} {'Qty':>10}")
        print("-" * 72)

        for _, r in group.iterrows():
            print(
                f"{r['Component'][:30]:30} "
                f"{r['ComponentCode'][:15]:15} "
                f"{str(r.get('ConsumptionBasis', 'PER_UNIT'))[:12]:12} "
                f"{float(r['Qty Per Production Unit']):>10.2f}"
            )


# You can edit this list to change or extend allowed product unit types.
ALLOWED_UNIT_TYPES = ["case", "drum", "bucket", "tote"]


def load_kits() -> pd.DataFrame:
    df = load_csv_strip(KITS_FILE, headers_default=KITS_COLUMNS)

    # Normalize numeric
    for col in ("UnitsPerPallet", "Qty Per Production Unit", "Waste %"):
        df[col] = pd.to_numeric(df.get(col, 0.0), errors="coerce").fillna(0.0)

    # Make sure optional columns exist
    for col in ("InventorySource", "UsageUOM", "ConsumptionBasis"):
        if col not in df.columns:
            df[col] = ""

    # Normalize strings
    for col in (
        "Finished Product",
        "ProductCode",
        "Line",
        "UnitType",
        "Component",
        "ComponentCode",
        "ComponentType",
        "InventorySource",
        "UsageUOM",
        "ConsumptionBasis",
    ):
        series = df[col] if col in df.columns else ""
        if hasattr(series, "fillna"):
            series = series.fillna("")
        df[col] = pd.Series(series).astype(str).str.strip()

    df["ConsumptionBasis"] = df["ConsumptionBasis"].astype(str).str.strip().str.upper()
    df.loc[~df["ConsumptionBasis"].isin(["PER_UNIT", "PER_CASE", "PER_PALLET"]), "ConsumptionBasis"] = "PER_UNIT"

    return df


def _select_unit_type() -> Optional[str]:
    print("\nSelect Unit Type for FINISHED PRODUCT:")
    for i, ut in enumerate(ALLOWED_UNIT_TYPES, start=1):
        print(f"{i}) {ut}")
    choice = input("Choose number (or ENTER to cancel): ").strip()
    if not choice:
        return None
    if not choice.isdigit() or not (1 <= int(choice) <= len(ALLOWED_UNIT_TYPES)):
        print(Color.RED + "Invalid UnitType selection." + Color.RESET)
        return None
    return ALLOWED_UNIT_TYPES[int(choice) - 1]


def _select_component_type() -> Optional[str]:
    """
    Show component types, with an 'Other' option that allows adding a new type permanently.
    """
    types = get_component_types()
    if not types:
        types = ["bottle", "cap", "label", "drum", "bucket", "box"]

    print("\nSelect Component Type:")
    for i, t in enumerate(types, start=1):
        print(f"{i}) {t}")
    print(f"{len(types) + 1}) Other (add new type)")

    choice = input("Choose number (or ENTER to cancel): ").strip()
    if not choice:
        return None

    if not choice.isdigit():
        print(Color.RED + "Invalid selection." + Color.RESET)
        return None

    idx = int(choice)
    if 1 <= idx <= len(types):
        return types[idx - 1]

    if idx == len(types) + 1:
        new_type = input("Enter new component type: ").strip().lower()
        if not new_type:
            print(Color.RED + "Empty type. Cancelled." + Color.RESET)
            return None
        add_new_component_type(new_type)
        return new_type

    print(Color.RED + "Invalid selection." + Color.RESET)
    return None


def _select_inventory_source() -> Optional[str]:
    print("\nComponent Source:")
    print("1) Inventory (INV)")
    print("2) Raw Material (RM)")
    choice = input("Choose number (or ENTER to cancel): ").strip()
    if not choice:
        return None
    if choice == "1":
        return "INV"
    if choice == "2":
        return "RM"
    print(Color.RED + "Invalid selection." + Color.RESET)
    return None


def _guess_usage_uom(source: str, component_type: str) -> str:
    if str(source).upper() == "RM":
        return "gal"
    return "ea"


def _select_consumption_basis(existing: str = "") -> Optional[str]:
    """
    Choose how this component is consumed during production.
    PER_UNIT   = qty per production unit entered (case/drum/bucket/tote)
    PER_CASE   = qty per case; mathematically uses the completed case count
    PER_PALLET = qty per completed pallet; partial pallets round up to 1 pallet
    """
    options = [
        ("PER_UNIT", "Per production unit"),
        ("PER_CASE", "Per case"),
        ("PER_PALLET", "Per completed pallet"),
    ]

    existing = str(existing or "").strip().upper()
    if existing and existing not in [k for k, _ in options]:
        existing = "PER_UNIT"

    print("\nConsumption Basis:")
    for i, (key, label) in enumerate(options, start=1):
        suffix = " [current]" if existing == key else ""
        print(f"{i}) {label} ({key}){suffix}")

    prompt = "Choose number"
    if existing:
        prompt += " (or ENTER to keep current)"
    else:
        prompt += " (or ENTER to cancel)"

    choice = input(prompt + ": ").strip()
    if not choice:
        return existing or None
    if choice.isdigit() and 1 <= int(choice) <= len(options):
        return options[int(choice) - 1][0]

    print(Color.RED + "Invalid ConsumptionBasis selection." + Color.RESET)
    return None


def _basis_qty_prompt(consumption_basis: str, unit_type: str) -> str:
    basis = str(consumption_basis or "PER_UNIT").upper()
    if basis == "PER_PALLET":
        return "Qty Per Completed Pallet: "
    if basis == "PER_CASE":
        return "Qty Per Case: "
    return f"Qty Per Production Unit (per {unit_type}): "


def _list_products(df: pd.DataFrame) -> List[Tuple[str, str, str, str, float]]:
    """
    Print and return list of distinct products for selection.
    (Reused by edit_product.)
    """
    menu_title("Products in Kits")

    products = _get_distinct_products(df)
    if not products:
        print(Color.YELLOW + "No products defined yet.\n" + Color.RESET)
        return []

    for i, (fp, pc, ln, ut, upp) in enumerate(products, start=1):
        print(
            f"{i}) Line {ln} | {fp} | Code={pc} | UnitType={ut} | UnitsPerPallet={upp}"
        )
    print()
    return products


def _select_product(df: pd.DataFrame) -> Optional[Tuple[str, str, str, str, float]]:
    products = _list_products(df)
    if not products:
        return None

    choice = input("Select product number (or ENTER to cancel): ").strip()
    if not choice:
        return None
    if not choice.isdigit() or not (1 <= int(choice) <= len(products)):
        print(Color.RED + "Invalid product selection.\n" + Color.RESET)
        return None

    return products[int(choice) - 1]


def _get_distinct_products(df: pd.DataFrame) -> List[Tuple[str, str, str, str, float]]:
    """
    Return distinct products as tuples:
    (Finished Product, ProductCode, Line, UnitType, UnitsPerPallet)
    """
    if df.empty:
        return []

    distinct = (
        df[["Finished Product", "ProductCode", "Line", "UnitType", "UnitsPerPallet"]]
        .drop_duplicates()
        .sort_values(by=["UnitType", "Line", "Finished Product"])
    )

    products: List[Tuple[str, str, str, str, float]] = []
    for _, row in distinct.iterrows():
        fp = row["Finished Product"]
        pc = row["ProductCode"]
        ln = row["Line"]
        ut = row["UnitType"]
        upp = float(row["UnitsPerPallet"])
        products.append((fp, pc, ln, ut, upp))
    return products


def _print_bom_block(
    df: pd.DataFrame,
    finished_product: str,
    product_code: str,
    line: str,
    unit_type: str,
    units_per_pallet: float,
) -> None:
    """
    Pretty-print a BOM block for a single product, with all its components.
    """
    rows = df[
        (df["Finished Product"] == finished_product)
        & (df["ProductCode"] == product_code)
        & (df["Line"] == line)
    ].reset_index(drop=True)

    print(
        Color.CYAN
        + Color.BOLD
        + f"\nProduct: {finished_product}  |  Code: {product_code}  |  Line: {line}  |  UnitType: {unit_type}  |  Units/Pallet: {units_per_pallet:.0f}"
        + Color.RESET
    )
    if rows.empty:
        print(Color.YELLOW + "  (No components defined)\n" + Color.RESET)
        return

    print("-" * 108)
    print(
        f"{'Component':30} {'Code':15} {'Type':10} {'Source':6} {'UOM':6} {'Basis':12} {'Qty':10} {'Waste%':7}"
    )
    print("-" * 108)
    for _, r in rows.iterrows():
        comp = str(r["Component"])
        code = str(r["ComponentCode"])
        ctype = str(r["ComponentType"])
        source = str(r.get("InventorySource", "")).strip()
        uom = str(r.get("UsageUOM", "")).strip()
        basis = str(r.get("ConsumptionBasis", "PER_UNIT")).strip().upper() or "PER_UNIT"
        qty = float(r["Qty Per Production Unit"])
        waste = float(r["Waste %"])
        print(
            f"{comp[:30]:30} {code[:15]:15} {ctype[:10]:10} {source[:6]:6} {uom[:6]:6} {basis[:12]:12} {qty:10.3f} {waste:7.2f}"
        )
    print("-" * 108)


def view_kits() -> None:
    """
    Interactive view for Kits:
    1) View all (raw table)
    2) Select product → view that BOM only
    3) Grouped by product (pretty sections)
    """
    df = load_kits()
    if df.empty:
        print(Color.YELLOW + "\nNo entries in Kits.csv.\n" + Color.RESET)
        return

    while True:
        menu_title("View Kits (BOM)")
        print("1) View All (raw table)")
        print("2) Select Product (single BOM)")
        print("3) Grouped by Product (formatted)")
        print("4) Back")

        choice = input("Choose: ").strip()

        if choice == "1":
            print()
            pretty_print_kits(df)
            print()

        elif choice == "2":
            products = _get_distinct_products(df)
            if not products:
                print(Color.YELLOW + "No products found.\n" + Color.RESET)
                continue

            menu_title("Select Product to View BOM")
            for idx, (fp, pc, ln, ut, upp) in enumerate(products, start=1):
                print(
                    f"{idx}) Line {ln} | {fp} | Code={pc} | UnitType={ut} | Units/Pallet={upp}"
                )
            sel = input("Select product number (or ENTER to cancel): ").strip()
            if not sel:
                continue
            if not sel.isdigit() or not (1 <= int(sel) <= len(products)):
                print(Color.RED + "Invalid selection.\n" + Color.RESET)
                continue

            fp, pc, ln, ut, upp = products[int(sel) - 1]
            _print_bom_block(df, fp, pc, ln, ut, upp)

        elif choice == "3":
            products = _get_distinct_products(df)
            if not products:
                print(Color.YELLOW + "No products found.\n" + Color.RESET)
                continue
            for fp, pc, ln, ut, upp in products:
                _print_bom_block(df, fp, pc, ln, ut, upp)

        elif choice == "4":
            break
        else:
            print(Color.RED + "Invalid choice.\n" + Color.RESET)


def _load_known_raw_materials() -> List[Tuple[str, str]]:
    bal = load_rm_balance(rebuild_if_missing=True)
    if bal.empty:
        return []
    known: dict[str, Tuple[str, str]] = {}
    for _, row in bal.iterrows():
        name = str(row.get("Material", "")).strip()
        code = str(row.get("MaterialCode", "")).strip().upper()
        if name:
            known[name.lower()] = (name, code)
    return sorted(known.values(), key=lambda x: x[0].lower())


def _maybe_reuse_component(comp_name: str, source: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Check if a component already exists in the selected source.
    Returns (reuse_existing, comp_code, comp_type).
    """
    comp_name = str(comp_name).strip()
    source = str(source).strip().upper()

    if source == "RM":
        known_rm = _load_known_raw_materials()
        match = next((row for row in known_rm if row[0].lower() == comp_name.lower()), None)
        if not match:
            return False, None, None

        existing_name, existing_code = match
        existing_type = "raw material"
        print(
            Color.CYAN
            + f"\nRaw material '{existing_name}' already exists in RM-BAL-01 "
              f"(Code={existing_code})."
            + Color.RESET
        )
        if confirm("Use this existing raw material (no new code/type needed)?"):
            return True, existing_code, existing_type
        return False, None, None

    inv = load_inventory()
    mask = inv["Component"].astype(str).str.lower() == comp_name.lower()
    if not mask.any():
        return False, None, None

    row = inv[mask].iloc[0]
    existing_code = str(row["ComponentCode"])
    existing_type = str(row["ComponentType"])

    print(
        Color.CYAN
        + f"\nComponent '{comp_name}' already exists in inventory "
          f"(Code={existing_code}, Type={existing_type})."
        + Color.RESET
    )
    if confirm("Use this existing component (no new code/type needed)?"):
        return True, existing_code, existing_type

    return False, None, None


def _build_component_row(
    *,
    finished_product: str,
    product_code: str,
    line: str,
    unit_type: str,
    units_per_pallet: float,
    component: str,
    component_code: str,
    component_type: str,
    qty_per_unit: float,
    waste_pct: float,
    consumption_basis: str,
    inventory_source: str,
    usage_uom: str,
) -> dict:
    return {
        "Finished Product": finished_product,
        "ProductCode": product_code,
        "Line": line,
        "UnitType": unit_type,
        "UnitsPerPallet": float(units_per_pallet),
        "Component": component,
        "ComponentCode": component_code,
        "ComponentType": component_type,
        "Qty Per Production Unit": float(qty_per_unit),
        "ConsumptionBasis": str(consumption_basis or "PER_UNIT").strip().upper(),
        "Waste %": float(waste_pct),
        "InventorySource": inventory_source,
        "UsageUOM": usage_uom,
    }


def _prompt_component_details(comp: str, unit_type: str) -> Optional[Tuple[str, str, str, str]]:
    source = _select_inventory_source()
    if not source:
        return None

    reuse, existing_code, existing_type = _maybe_reuse_component(comp, source)

    if reuse:
        comp_code = existing_code or ""
        ctype = existing_type or ("raw material" if source == "RM" else "")
        usage_uom = _guess_usage_uom(source, ctype)
        print(
            Color.GREEN
            + f"Using existing {'raw material' if source == 'RM' else 'component'} '{comp}' "
              f"(Code={comp_code}, Type={ctype}, Source={source})."
            + Color.RESET
        )
        return source, comp_code, ctype, usage_uom

    if source == "RM":
        known_code = get_raw_material_code(comp)
        comp_code_raw = input(
            f"MaterialCode (free text, will be UPPERCASE){' [ENTER to use '+known_code+']' if known_code else ''}: "
        ).strip()
        comp_code = (comp_code_raw or known_code).upper()
        if not comp_code:
            print(Color.RED + "MaterialCode cannot be empty.\n" + Color.RESET)
            return None
        ctype = "raw material"
        usage_uom = input("Usage UOM for this raw material [ENTER for gal]: ").strip().lower() or "gal"
        return source, comp_code, ctype, usage_uom

    comp_code_raw = input("ComponentCode (free text, will be UPPERCASE): ").strip()
    if not comp_code_raw:
        print(Color.RED + "ComponentCode cannot be empty.\n" + Color.RESET)
        return None
    comp_code = comp_code_raw.upper()

    ctype = _select_component_type()
    if not ctype:
        print(Color.RED + "No ComponentType selected. Component skipped.\n" + Color.RESET)
        return None

    add_or_update_inventory_component(
        component=comp,
        component_code=comp_code,
        component_type=ctype,
    )
    usage_uom = input("Usage UOM for this inventory component [ENTER for ea]: ").strip().lower() or "ea"
    return source, comp_code, ctype, usage_uom


def add_product() -> None:
    """
    Add a new finished product and its components.
    This is the ONLY place where new components are created.
    """
    df = load_kits()
    menu_title("Add New Product")

    finished_product = input("Finished Product name: ").strip()
    if not finished_product:
        print(Color.RED + "Cancelled (empty product name).\n" + Color.RESET)
        return

    print("Note: ProductCode is free text; it will be stored in UPPERCASE.")
    product_code = input("ProductCode: ").strip().upper()
    if not product_code:
        print(Color.RED + "Cancelled (empty product code).\n" + Color.RESET)
        return

    line = choose_configured_line()
    if not line:
        print(Color.RED + "Cancelled (no line selected).\n" + Color.RESET)
        return

    unit_type = _select_unit_type()
    if not unit_type:
        print(Color.RED + "Cancelled (no UnitType selected).\n" + Color.RESET)
        return

    units_per_pallet = numeric_input("UnitsPerPallet (whole number): ", allow_float=False)
    print()

    components_added: List[str] = []

    while True:
        comp = input("Component name (or ENTER to finish): ").strip()
        if comp == "":
            break

        details = _prompt_component_details(comp, unit_type)
        if not details:
            continue
        inventory_source, comp_code, ctype, usage_uom = details

        consumption_basis = _select_consumption_basis()
        if not consumption_basis:
            print(Color.YELLOW + "Component skipped (no ConsumptionBasis selected)." + Color.RESET)
            continue

        qty_per_unit = numeric_input(_basis_qty_prompt(consumption_basis, unit_type), allow_float=True)
        waste_pct = 0.0 if consumption_basis == "PER_PALLET" else numeric_input("Waste %: ", allow_float=True)

        new_row = _build_component_row(
            finished_product=finished_product,
            product_code=product_code,
            line=line,
            unit_type=unit_type,
            units_per_pallet=units_per_pallet,
            component=comp,
            component_code=comp_code,
            component_type=ctype,
            qty_per_unit=qty_per_unit,
            waste_pct=waste_pct,
            consumption_basis=consumption_basis,
            inventory_source=inventory_source,
            usage_uom=usage_uom,
        )

        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        components_added.append(f"{comp} [{inventory_source}]")

        print(
            Color.GREEN
            + f"Added component '{comp}' to product '{finished_product}'."
            + Color.RESET
        )
        print("Current components for this product:")
        for c in components_added:
            print(f" - {c}")
        print()

    save_csv(df, KITS_FILE)

    product_rows = df[
        (df["Finished Product"] == finished_product)
        & (df["ProductCode"] == product_code)
        & (df["Line"] == line)
    ]
    if not product_rows.empty:
        menu_title(f"Components for '{finished_product}' (Code={product_code})")
        for _, row in product_rows.iterrows():
            print(f" - {row['Component']} [{row.get('InventorySource', '')}]")
        print()

    print(Color.GREEN + "✔ Product and components saved to Kits.csv.\n" + Color.RESET)


def edit_product() -> None:
    """
    Simple edit flow: choose product, then allow editing component rows
    (qty/waste) or removing/adding components.
    """
    df = load_kits()
    selection = _select_product(df)
    if not selection:
        return

    fp, pc, line, unit_type, units_per_pallet = selection

    while True:
        menu_title(f"Edit Product: {fp} (Code={pc}, Line={line})")

        rows = df[
            (df["Finished Product"] == fp)
            & (df["ProductCode"] == pc)
            & (df["Line"] == line)
        ]

        if rows.empty:
            print(Color.YELLOW + "No components defined yet.\n" + Color.RESET)
        else:
            print("Current BOM:\n")
            display_cols = [
                "Component",
                "ComponentCode",
                "ComponentType",
                "InventorySource",
                "UsageUOM",
                "ConsumptionBasis",
                "Qty Per Production Unit",
                "Waste %",
            ]
            display = rows[[c for c in display_cols if c in rows.columns]]
            print(display.to_string(index=False))
            print()

        print("1) Add Component")
        print("2) Remove Component")
        print("3) Edit Component Qty/Waste")
        print("4) Back")

        choice = input("Choose: ").strip()

        if choice == "1":
            comp = input("Component name: ").strip()
            if not comp:
                print(Color.RED + "Empty component name.\n" + Color.RESET)
                continue

            details = _prompt_component_details(comp, unit_type)
            if not details:
                continue
            inventory_source, comp_code, ctype, usage_uom = details

            consumption_basis = _select_consumption_basis()
            if not consumption_basis:
                print(Color.YELLOW + "Component skipped (no ConsumptionBasis selected)." + Color.RESET)
                continue

            qty_per_unit = numeric_input(_basis_qty_prompt(consumption_basis, unit_type), allow_float=True)
            waste_pct = 0.0 if consumption_basis == "PER_PALLET" else numeric_input("Waste %: ", allow_float=True)

            new_row = _build_component_row(
                finished_product=fp,
                product_code=pc,
                line=line,
                unit_type=unit_type,
                units_per_pallet=units_per_pallet,
                component=comp,
                component_code=comp_code,
                component_type=ctype,
                qty_per_unit=qty_per_unit,
                waste_pct=waste_pct,
                consumption_basis=consumption_basis,
                inventory_source=inventory_source,
                usage_uom=usage_uom,
            )
            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
            save_csv(df, KITS_FILE)
            print(Color.GREEN + "Component added.\n" + Color.RESET)

        elif choice == "2":
            comp = input("Component name to remove: ").strip()
            if not comp:
                continue
            before = len(df)
            df = df[
                ~(
                    (df["Finished Product"] == fp)
                    & (df["ProductCode"] == pc)
                    & (df["Line"] == line)
                    & (df["Component"].astype(str).str.lower() == comp.lower())
                )
            ]
            after = len(df)
            if after < before:
                save_csv(df, KITS_FILE)
                print(Color.GREEN + "Component removed.\n" + Color.RESET)
            else:
                print(Color.YELLOW + "No matching component found.\n" + Color.RESET)

        elif choice == "3":
            comp = input("Component name to edit: ").strip()
            if not comp:
                continue
            mask = (
                (df["Finished Product"] == fp)
                & (df["ProductCode"] == pc)
                & (df["Line"] == line)
                & (df["Component"].astype(str).str.lower() == comp.lower())
            )
            if not mask.any():
                print(Color.YELLOW + "Component not found.\n" + Color.RESET)
                continue

            current_basis = str(df.loc[mask, "ConsumptionBasis"].iloc[0]) if "ConsumptionBasis" in df.columns else "PER_UNIT"
            consumption_basis = _select_consumption_basis(current_basis)
            if not consumption_basis:
                print(Color.YELLOW + "Component update cancelled (no ConsumptionBasis selected)." + Color.RESET)
                continue

            qty_per_unit = numeric_input(_basis_qty_prompt(consumption_basis, unit_type), allow_float=True)
            waste_pct = 0.0 if consumption_basis == "PER_PALLET" else numeric_input("New Waste %: ", allow_float=True)

            df.loc[mask, "Qty Per Production Unit"] = float(qty_per_unit)
            df.loc[mask, "ConsumptionBasis"] = consumption_basis
            df.loc[mask, "Waste %"] = float(waste_pct)
            save_csv(df, KITS_FILE)
            print(Color.GREEN + "Component updated.\n" + Color.RESET)

        elif choice == "4":
            break
        else:
            print(Color.RED + "Invalid choice.\n" + Color.RESET)
