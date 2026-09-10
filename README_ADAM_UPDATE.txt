PLC Python Inventory System - Adam Update

Purpose:
This build keeps QuickBooks Desktop as the official accounting system and keeps this Python tool as the operational inventory tracker only.

Main additions:
1. Inventory Dashboard
   - Inventory > Inventory Dashboard / Search
   - Raw materials view
   - Components/packaging view
   - Low/reorder/zero/negative view
   - Search inventory
   - Edit reorder levels
   - Export inventory backup CSV

2. Reorder Status Logic
   Uses Quantity, MinQty, ReorderPoint, MaxQty.
   Status values:
   - OK
   - LOW
   - REORDER
   - ZERO
   - NEGATIVE
   - NO MIN SET

3. Set Count / Stocktake
   - Inventory > Set Count / Stocktake
   - Finished Goods > Set Finished Goods Count / Stocktake
   This lets you enter the actual counted amount as of a specific date.
   The system creates the adjustment needed behind the scenes.

4. Monthly Inventory Reports
   - Reports > Generate Monthly Inventory CSV Report
   Creates a folder under monthly_reports/ with:
   - components_inventory.csv
   - raw_materials_from_inventory.csv
   - components_only.csv
   - finished_goods_on_hand.csv
   - raw_material_balance.csv
   - inventory_status_attention.csv
   - summary.csv

5. Code Mapping / QuickBooks Reconciliation
   - Settings / Admin > Code Mapping / QB Reconciliation
   QuickBooks Item Code is the master code.
   Names can be changed for ease, but matching should always happen by code.

Included reference exports:
- qb_exports/item list.CSV
- qb_exports/qb_open_sales_order.CSV
- other uploaded QB support CSVs/text files

Recommended use:
QuickBooks = official accounting inventory and financial reporting.
Python = operational physical stock, low-stock visibility, reorder needs, monthly stock backup.

QB PRICING IN MONTHLY REPORTS
-----------------------------
Monthly inventory reports now use qb_exports/item list.CSV to add QuickBooks Cost and Price.
Matching rule: ITEM CODE ONLY. Item names/descriptions are ignored for matching.

Report columns added where possible:
- QBCost
- QBPrice
- QBDescription
- QBType
- QBPreferredVendor
- QBPriceMatch
- InventoryValue or FG_EstimatedValue

Important note for Finished Goods:
FG-01 tracks pallets. If QuickBooks Cost is per case/drum instead of per pallet, FG_EstimatedValue is a reference only and should not be used as accounting valuation without confirming the unit.
