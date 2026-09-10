import json
import os
from typing import List

from helpers import Color

COMPONENT_TYPES_FILE = "component_types.json"

DEFAULT_COMPONENT_TYPES = [
    "bottle",
    "cap",
    "label",
    "drum",
    "bucket",
    "box",
]


def _load_raw_types() -> List[str]:
    """
    Load component types from JSON file if it exists, otherwise return defaults.
    """
    if not os.path.exists(COMPONENT_TYPES_FILE):
        return DEFAULT_COMPONENT_TYPES[:]

    try:
        with open(COMPONENT_TYPES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        types = data.get("types", [])
        if not isinstance(types, list):
            return DEFAULT_COMPONENT_TYPES[:]
        return [str(t).strip() for t in types if str(t).strip()]
    except Exception:
        # If file is corrupted, fall back to defaults
        print(
            Color.YELLOW
            + f"Warning: {COMPONENT_TYPES_FILE} is invalid. Using default component types."
            + Color.RESET
        )
        return DEFAULT_COMPONENT_TYPES[:]


def _save_raw_types(types: List[str]) -> None:
    """
    Save the list of component types to JSON file.
    """
    clean = sorted(set(t.lower().strip() for t in types if t.strip()))
    data = {"types": clean}
    with open(COMPONENT_TYPES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def get_component_types() -> List[str]:
    """
    Public accessor – returns sorted list of component types (lowercase).
    """
    return sorted(set(_load_raw_types()))


def add_new_component_type(new_type: str) -> None:
    """
    Add a new component type permanently, saved to JSON.
    """
    new_type = str(new_type).strip().lower()
    if not new_type:
        return

    types = _load_raw_types()
    if new_type in types:
        return

    types.append(new_type)
    _save_raw_types(types)
    print(
        Color.GREEN
        + f"Component type '{new_type}' added permanently."
        + Color.RESET
    )
