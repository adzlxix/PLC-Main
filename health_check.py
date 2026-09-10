"""
health_check.py

Simple system health check:
- Ensures key CSV files exist and are readable
- Reports missing / empty critical structures
"""

from helpers import Color, menu_title
from file_utils import ensure_csv
from inventory import load_inventory, load_inventory_history
from kits import load_kits
from demand import load_line_capacity
from receiving import load_receiving
from production import load_production


def run_health_check() -> None:
    menu_title("System Health Check")

    # Ensure core files exist
    inv = load_inventory()
    kits = load_kits()
    prod = load_production()
    rcv = load_receiving()
    hist = load_inventory_history()
    linecap = load_line_capacity()

    print("Inventory rows:", len(inv))
    print("Inventory History rows:", len(hist))
    print("Kits (BOM) rows:", len(kits))
    print("Production rows:", len(prod))
    print("Receiving rows:", len(rcv))
    print("LineCapacity rows:", len(linecap))

    if kits.empty:
        print(Color.YELLOW + "Warning: No products in Kits.csv." + Color.RESET)
    if inv.empty:
        print(Color.YELLOW + "Warning: No components in INV-01.csv." + Color.RESET)

    print(Color.GREEN + "\nHealth check completed.\n" + Color.RESET)
