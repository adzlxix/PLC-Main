from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, Optional

import pandas as pd

from file_utils import ensure_csv, save_csv

AUDIT_FILE = "AUDIT-01.csv"

AUDIT_HEADERS = [
    "Timestamp",      # ISO timestamp
    "Module",         # e.g., production / labels / finished_goods / shipping
    "Action",         # e.g., ISSUE_LABELS / RECORD_PRODUCTION / SHIP / REVERSE
    "EntityType",     # e.g., LabelRun / Production / FGEntry / Shipment
    "EntityID",       # e.g., ProductionID / ShipmentID
    "User",           # operator / initials
    "DetailsJSON",    # free-form JSON for traceability
]


def log_audit(
    module: str,
    action: str,
    entity_type: str,
    entity_id: str,
    user: str = "",
    details: Optional[Dict[str, Any]] = None,
) -> None:
    """Append a single audit event to AUDIT-01.csv.

    Keep it simple and robust:
    - Always append-only (no updates in-place)
    - Details stored as JSON string for flexible future use
    """
    df = ensure_csv(AUDIT_FILE, AUDIT_HEADERS)

    ts = datetime.now().isoformat(timespec="seconds")
    payload = details or {}
    try:
        details_json = json.dumps(payload, ensure_ascii=False)
    except Exception:
        # Never fail an operational transaction because details couldn't serialize
        details_json = json.dumps({"_raw": str(payload)})

    new_row = {
        "Timestamp": ts,
        "Module": module,
        "Action": action,
        "EntityType": entity_type,
        "EntityID": entity_id,
        "User": user,
        "DetailsJSON": details_json,
    }

    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    save_csv(df, AUDIT_FILE)
