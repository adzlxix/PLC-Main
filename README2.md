
# PLC Production & Inventory Management System

## Overview

This repository contains a **Python-based production, inventory, finished goods, and shipping management system** designed for a manufacturing plant environment.

The system is:
- CSV-backed (no database required)
- Ledger-based (append-only, ISO-friendly)
- Designed around real plant workflows
- Fully auditable and traceable
- Extensible without breaking core logic

It is built so that **any competent operator, engineer, or auditor** can understand and use it **without assistance from the original author**.

---

## Core Design Principles

1. **Single Source of Truth**
   - Raw materials, production, finished goods, and shipping are tracked in separate ledgers.
   - No silent overwrites or hidden state.

2. **Append-Only Records**
   - No destructive edits.
   - Corrections are made via reversal entries.

3. **Physical Reality First**
   - If materials are consumed → inventory decreases.
   - If pallets exist → finished goods increase.
   - If shipments leave → finished goods decrease.

4. **Auditability by Default**
   - Who did what, when, and why is always recorded.
   - A global audit log links all actions.

---

## System Architecture

```
main.py
│
├── production.py        # Production recording (manual & label-based)
├── inventory.py         # Raw material inventory ledger
├── receiving.py         # Incoming materials
├── kits.py              # BOM / kits
├── finished_goods.py    # Finished goods ledger (pallets on floor)
├── shipping.py          # Outgoing shipments
├── demand.py            # Usage, lead time, ROP calculations
├── downtime.py          # Downtime logging
├── capa.py              # CAPA records
├── audit.py             # Global audit log
├── helpers.py           # Input validation & utilities
└── file_utils.py        # CSV load/save utilities
```

---

## Typical Daily Workflow

1. Issue pallet labels (morning)
2. Run production
3. Record production (manual or label-based)
4. Raw materials are consumed automatically
5. Finished goods are posted automatically
6. Shipments reduce finished goods
7. All actions are logged to the audit trail

---

## Production (`production.py`)

### Production Types
- Manual Production
- Label-Based Production (recommended for palletized output)

### Production ID Format
```
PROD{Line}-{ProductCode}-{JulianDate}
Example: PROD3-ATWWPX-25360
```

### What Happens When Production Is Recorded
- Row added to `PROD-01.csv`
- Raw materials consumed via Kits/BOM
- Finished goods posted to FG ledger (palletized products only)
- Audit entry written

### Key Fields in `PROD-01.csv`
- ProductionID
- Date
- Line
- Product
- ProductCode
- UnitType
- UnitsCompleted
- PalletsCompleted
- RecordedBy
- RecordedOn
- Source (MANUAL / LABELS)

---

## Label Issuing

### Label ID Format
```
P{LL}{ProductCode}{Julian}{UnitChar}{Seq}
Example: P01ATGP5025363P001
```

### Label Lifecycle
ISSUED → USED → VOIDED

### Label File: `LBL-01.csv`
- LabelID
- ProductCode
- Line
- IssuedOn / IssuedBy
- UsedOn / UsedBy
- VoidedOn / VoidedBy
- Status

---

## Inventory (`inventory.py`)

### Inventory Model
- Ledger-based (append-only)

### Files
- `INV-01.csv` – derived snapshot
- `INV-01-History.csv` – authoritative ledger

### Inventory Adjustments
- Receiving
- Production consumption
- Manual adjustments (with reason)
- Reversals

---

## Kits / BOM (`kits.py`)

Defines raw material usage per finished unit.

### Required Columns
- Finished Product
- ProductCode
- Line
- Component
- Qty Per Production Unit
- Waste %

---

## Finished Goods (`finished_goods.py`)

### Purpose
Tracks **physical finished pallets on the floor**.

### Ledger Model
- Append-only
- Quantity is derived, not stored

### File: `FG-01.csv`
- EntryID
- Date
- ProductCode
- QtyChange (+ / -)
- Source (PRODUCTION / SHIPPING / ADJUSTMENT)
- ReferenceID
- User
- Notes

### Rules
- Production adds finished goods
- Shipping removes finished goods
- Adjustments require justification
- No edits; only reversals

---

## Shipping (`shipping.py`)

### Purpose
Records outgoing shipments and reduces finished goods.

### File: `SHP-01.csv`
- ShipmentID
- Date
- ProductCode
- QtyShipped
- ShippedBy
- Notes

### Guardrails
- Cannot ship more than available FG
- Every shipment is audit-logged
- Reversals restore FG

---

## Demand & Reorder Planning (`demand.py`)

### Tracks
- Average daily usage
- Lead time
- Reorder Point (ROP)

### Alerts
- Below ROP
- Stockout risk
- Overstock warnings

---

## Downtime (`downtime.py`)

Tracks production downtime for reporting and analysis.

### File: `DT-01.csv`
- Date
- Line
- Machine
- Issue
- Minutes
- RecordedBy

---

## CAPA (`capa.py`)

Corrective and Preventive Action records.

### File: `CAPA-01.csv`
- CAPAID
- Issue
- Root Cause
- Action
- Owner
- Status

---

## Global Audit Log (`audit.py`)

### File: `AUDIT-01.csv`

Logs every commit-like action across the system.

### Fields
- AuditID
- Timestamp
- User
- Module
- Action
- PrimaryRef
- Details (JSON)

### Purpose
- Full traceability
- ISO audit support
- Forensic reconstruction

---

## ISO Alignment Summary

This system supports ISO 9001 principles by:
- Maintaining controlled records
- Preventing silent edits
- Providing traceability
- Supporting corrective action
- Enabling management review

---

## Extending the System

The system is intentionally modular. Future extensions may include:
- Barcode scanning
- Customer & carrier details
- Multi-location warehousing
- ERP integration

All extensions should:
- Preserve append-only ledgers
- Use reversal entries
- Log to the global audit log

---

## Final Notes

This system is designed to be:
- Practical for daily plant use
- Defensible in audits
- Maintainable by future engineers

No part of the system relies on tribal knowledge or undocumented behavior.
