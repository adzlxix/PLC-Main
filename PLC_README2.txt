PLC Inventory & Operations Control System Version: v3 (Integrated
Production, Inventory & Downtime) Owner: PLC / Imperial Maintained by:
Plant Operations

PURPOSE This Python-based system provides operational control,
traceability, and reporting for PLC manufacturing operations. It
supports production logging, inventory tracking, downtime logging, and
executive reporting while remaining ISO-friendly and intentionally
lightweight.

SYSTEM PHILOSOPHY 1. CSV files are the system of record 2. Python
enforces rules, not volume of data entry 3. One responsibility per
module 4. ISO-aligned by design

PROJECT STRUCTURE See project root for: main.py production.py
inventory.py receiving.py kits.py demand.py downtime.py equipment.py
helpers.py file_utils.py health_check.py CSV files: PROD-01.csv,
INV-01.csv, INV-01-History.csv, RCV-01.csv, Kits.csv, LineCapacity.csv,
EQ-01.csv, DT-01.csv

PRODUCTION Logs finished goods production, consumes inventory, supports
weekly executive reporting.

INVENTORY Tracks component stock with full movement history and
controlled adjustments.

RECEIVING Logs incoming materials and updates inventory with
confirmation and rejection support.

PRODUCTS & BOMS Defines finished products and associated components,
enforcing inventory linkage.

EQUIPMENT MASTER (EQ-01) Reference list of machines by line. Headers:
Line MachineType/Name Machine Code Notes

DOWNTIME LOG (DT-01) Logs downtime events, both machine-level and
line-level. Headers: Line MachineType/Name Machine Code Date Downtime
Start Downtime End Downtime Minutes Downtime Category Issue Work Done
Parts Used Tech Initials Notes

LINE-LEVEL DOWNTIME Non-machine downtime is logged as: MachineType/Name
= LINE-LEVEL Machine Code = N/A

CONTROLLED DOWNTIME CATEGORIES Mechanical Electrical Material Shortage
Changeover Cleaning / Sanitation Quality Hold Staffing Planned
Maintenance Other

WEEKLY REPORTING Reports are grouped by line and show total pallets for
cases, total units for bulk, and daily averages. Designed for copy/paste
into emails or Google Docs.

GOOGLE SHEETS All CSVs can be uploaded to Google Sheets with matching
headers. Python remains the logic layer.

NOT A CMMS This system intentionally avoids preventive maintenance
scheduling, financial tracking, or ERP replacement.

CHANGE MANAGEMENT Schema changes should be deliberate. CSV edits are
acceptable and expected.

FUTURE ENHANCEMENTS Downtime correlation in reports, CSV exports,
QuickBooks code sync, optional preventive maintenance.

END OF DOCUMENT
