"""
main.py

Clean, colored, minimal menu system for:
- Production
- Receiving
- Inventory
- Products (Kits / BOM)
- Reports
- Settings / Admin
- Downtime / Equipment Log
- CAPA / Corrective Actions
"""

from helpers import Color, menu_title
import production
import receiving
import inventory
import kits
import demand
import health_check
import downtime
import capa
import finished_goods
import shipping
import line_runtime
import monthly_reports
import code_mapping


def production_menu() -> None:
    while True:
        menu_title("Production")
        print("1) Record Production")
        print("2) View Production History (All)")
        print("3) View Production by Date Range")
        print("4) Issue Pallet Labels (LBL-01)")
        print("5) Line Runtime (hours / notes)")
        print("6) Back")

        choice = input("Choose: ").strip()

        if choice == "1":
            production.record_production()
        elif choice == "2":
            production.view_all_production_history()
        elif choice == "3":
            production.view_production_by_date_range()
        elif choice == "4":
            production.issue_pallet_labels()
        elif choice == "5":
            line_runtime.line_runtime_menu()
        elif choice == "6":
            break
        else:
            print(Color.RED + "Invalid choice.\n" + Color.RESET)


def receiving_menu() -> None:
    receiving.receiving_menu()


def inventory_menu() -> None:
    while True:
        menu_title("Inventory")
        print("1) Inventory Dashboard / Search")
        print("2) Adjust Inventory (Manual +/-)")
        print("3) Set Count / Stocktake")
        print("4) View Inventory History")
        print("5) Reset Inventory Component to ZERO")
        print("6) Back")

        choice = input("Choose: ").strip()

        if choice == "1":
            inventory.view_inventory()
        elif choice == "2":
            inventory.adjust_inventory_manual()
        elif choice == "3":
            inventory.set_inventory_component_count()
        elif choice == "4":
            inventory.view_inventory_history()
        elif choice == "5":
            inventory.reset_inventory_component_to_zero()
        elif choice == "6":
            break
        else:
            print(Color.RED + "Invalid choice.\n" + Color.RESET)




def finished_goods_menu() -> None:
    while True:
        menu_title("Finished Goods (FG-01)")
        print("1) View On-Hand (by ProductCode)")
        print("2) Record Adjustment (+/- pallets)")
        print("3) Set Finished Goods Count / Stocktake")
        print("4) Reverse Entry (correction)")
        print("5) Back")

        choice = input("Choose: ").strip()

        if choice == "1":
            finished_goods.view_on_hand()
        elif choice == "2":
            finished_goods.record_adjustment()
        elif choice == "3":
            finished_goods.set_finished_goods_count()
        elif choice == "4":
            finished_goods.reverse_entry()
        elif choice == "5":
            break
        else:
            print(Color.RED + "Invalid choice.\n" + Color.RESET)


def shipping_menu() -> None:
    while True:
        menu_title("Shipping (SHP-01)")
        print("1) Record Shipment (ships pallets from FG)")
        print("2) Reverse Shipment (correction)")
        print("3) Back")

        choice = input("Choose: ").strip()

        if choice == "1":
            shipping.record_shipment()
        elif choice == "2":
            shipping.reverse_shipment()
        elif choice == "3":
            break
        else:
            print(Color.RED + "Invalid choice.\n" + Color.RESET)

def products_menu() -> None:
    while True:
        menu_title("Products (Kits / BOM)")
        print("1) Add New Product")
        print("2) Edit Existing Product")
        print("3) View Kits")
        print("4) Back")

        choice = input("Choose: ").strip()

        if choice == "1":
            kits.add_product()
        elif choice == "2":
            kits.edit_product()
        elif choice == "3":
            kits.view_kits()
        elif choice == "4":
            break
        else:
            print(Color.RED + "Invalid choice.\n" + Color.RESET)


def reports_menu() -> None:
    while True:
        menu_title("Reports")
        print("1) Reorder Report (Full)")
        print("2) Low Stock Report Only")
        print("3) Export Low Stock (CSV + Email Text)")
        print("4) Daily Usage (Demand) Summary")
        print("5) Print Weekly Production Report")
        print("6) Historic Line Performance (Cases Only)")
        print("7) Generate Monthly Inventory CSV Report")
        print("8) Back")

        choice = input("Choose: ").strip()

        if choice == "1":
            demand.reorder_report(low_stock_only=False)
        elif choice == "2":
            demand.reorder_report(low_stock_only=True)
        elif choice == "3":
            demand.export_low_stock_report()
        elif choice == "4":
            usage, _ = demand.calculate_daily_usage()
            if not usage:
                print(Color.YELLOW + "\nNo usage data (check Kits and LineCapacity).\n" + Color.RESET)
            else:
                menu_title("Daily Usage (units/day)")
                for comp, val in sorted(usage.items()):
                    print(f"{comp}: {val:.2f}")
                print()
        elif choice == "5":
            production.print_weekly_production_report()
        elif choice == "6":
            production.historic_line_performance_cases()
        elif choice == "7":
            monthly_reports.generate_monthly_inventory_report()
        elif choice == "8":
            break
        else:
            print(Color.RED + "Invalid choice.\n" + Color.RESET)


def settings_menu() -> None:
    while True:
        menu_title("Settings / Admin")
        print("1) Edit Daily Line Output (Pallets/Day)")
        print("2) Run System Health Check")
        print("3) Code Mapping / QB Reconciliation")
        print("4) Back")

        choice = input("Choose: ").strip()

        if choice == "1":
            demand.edit_line_capacity()
        elif choice == "2":
            health_check.run_health_check()
        elif choice == "3":
            code_mapping.code_mapping_menu()
        elif choice == "4":
            break
        else:
            print(Color.RED + "Invalid choice.\n" + Color.RESET)


def downtime_menu() -> None:
    downtime.downtime_menu()


def capa_menu() -> None:
    capa.capa_menu()
    

def main() -> None:
    while True:
        print(
            "\n"
            + Color.CYAN
            + Color.BOLD
            + "===== PLC Inventory System ====="
            + Color.RESET
        )
        print("1) Production")
        print("2) Receiving")
        print("3) Inventory")
        print("4) Finished Goods")
        print("5) Shipping")
        print("6) Products (Kits / BOM)")
        print("7) Reports")
        print("8) Settings / Admin")
        print("9) Downtime / Equipment Log")
        print("10) CAPA / Corrective Actions")
        print("11) Exit")

        choice = input("Choose: ").strip()

        if choice == "1":
            production_menu()
        elif choice == "2":
            receiving_menu()
        elif choice == "3":
            inventory_menu()
        elif choice == "4":
            finished_goods_menu()
        elif choice == "5":
            shipping_menu()
        elif choice == "6":
            products_menu()
        elif choice == "7":
            reports_menu()
        elif choice == "8":
            settings_menu()
        elif choice == "9":
            downtime_menu()
        elif choice == "10":
            capa_menu()
        elif choice == "11":
            print(Color.GREEN + "\nExiting. Bye!\n" + Color.RESET)
            break
        else:
            print(Color.RED + "Invalid choice.\n" + Color.RESET)


if __name__ == "__main__":
    main()
