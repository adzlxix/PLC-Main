"""Shared line configuration helpers.

Line IDs and names are read from LineSettings.csv so adding Line 6+
only requires editing that CSV file.
"""

from __future__ import annotations

from file_utils import load_csv_strip
from helpers import Color

LINE_SETTINGS_FILE = "LineSettings.csv"
LINE_SETTINGS_COLUMNS = ["Line", "LineName"]


def load_line_settings() -> dict[str, str]:
    df = load_csv_strip(LINE_SETTINGS_FILE, headers_default=LINE_SETTINGS_COLUMNS)
    for col in LINE_SETTINGS_COLUMNS:
        if col not in df.columns:
            df[col] = ""

    lines: dict[str, str] = {}
    for _, row in df.iterrows():
        line = str(row.get("Line", "")).strip()
        name = str(row.get("LineName", "")).strip()
        if not line:
            continue
        lines[line] = name or f"Line {line}"
    return lines


def valid_line_ids() -> list[str]:
    return list(load_line_settings().keys())


def is_valid_line(line: str) -> bool:
    return str(line).strip() in load_line_settings()


def line_display_name(line: str) -> str:
    line = str(line).strip()
    name = load_line_settings().get(line, "")
    return f"Line {line} – {name}" if name else f"Line {line}"


def choose_line(prompt: str = "Choose line") -> str | None:
    lines = load_line_settings()
    if not lines:
        print(Color.RED + "No lines configured in LineSettings.csv." + Color.RESET)
        return None

    print("\nSelect Line:")
    for line, name in lines.items():
        print(f"{line}) {name}")

    while True:
        choice = input(f"{prompt} (or ENTER to cancel): ").strip()
        if not choice:
            return None
        if choice in lines:
            return choice
        print(Color.RED + "Invalid line. Update LineSettings.csv if this line should exist." + Color.RESET)
