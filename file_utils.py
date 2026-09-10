import os
import csv
from typing import List, Optional, Dict, Any

import pandas as pd
from pandas.errors import EmptyDataError


def ensure_csv(filename: str, headers: Optional[List[str]] = None) -> pd.DataFrame:
    """
    Ensure a CSV file exists and is readable.
    - If file does not exist, create with given headers.
    - If file exists but is empty, rewrite with headers.
    - Returns a DataFrame (possibly empty).
    """
    if not os.path.exists(filename):
        df = pd.DataFrame(columns=headers or [])
        df.to_csv(filename, index=False)
        return df

    try:
        df = pd.read_csv(filename)
    except EmptyDataError:
        # File exists but has no content
        df = pd.DataFrame(columns=headers or [])
        df.to_csv(filename, index=False)
        return df

    # Normalize columns (strip whitespace)
    df.columns = df.columns.str.strip()
    return df


def load_csv_strip(filename: str, headers_default: Optional[List[str]] = None) -> pd.DataFrame:
    """
    Load CSV safely (never crashes on empty or missing file).
    If headers_default is provided:
      - any missing columns are added and filled with empty/0
      - the DataFrame will at least contain all the default columns.
    """
    df = ensure_csv(filename, headers_default)

    if headers_default:
        # Ensure all default columns exist
        for col in headers_default:
            if col not in df.columns:
                df[col] = ""
        # Keep existing extra columns as well (do NOT drop them).
        # Only reorder so default columns appear first.
        ordered_cols = headers_default + [c for c in df.columns if c not in headers_default]
        df = df[ordered_cols]

    return df


def save_csv(df: pd.DataFrame, filename: str) -> None:
    """
    Save DataFrame to CSV with index=False.
    """
    df.to_csv(filename, index=False)



def ensure_trailing_newline(filename: str) -> None:
    """Ensure an existing file ends with a newline before appending rows."""
    if not os.path.exists(filename) or os.path.getsize(filename) == 0:
        return
    with open(filename, "rb+") as f:
        f.seek(-1, os.SEEK_END)
        last = f.read(1)
        if last not in (b"\n", b"\r"):
            f.write(b"\n")


def append_csv_row_safe(filename: str, row: Dict[str, Any], headers: List[str]) -> None:
    """
    Safely append one dictionary row to a CSV file.

    This prevents row-gluing/corrupt CSV issues by:
    - creating the file with headers when missing/empty
    - ensuring the existing file ends with a newline before append
    - writing via csv.DictWriter with a fixed header order
    """
    if not headers:
        raise ValueError("headers must be provided for append_csv_row_safe")

    file_missing_or_empty = (not os.path.exists(filename)) or os.path.getsize(filename) == 0

    if file_missing_or_empty:
        with open(filename, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
            writer.writeheader()
    else:
        ensure_trailing_newline(filename)

    clean_row = {h: row.get(h, "") for h in headers}
    with open(filename, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        writer.writerow(clean_row)
