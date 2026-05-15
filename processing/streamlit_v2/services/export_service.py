"""Reusable CSV export helpers."""

from __future__ import annotations

from datetime import datetime
from io import StringIO

import pandas as pd


def dataframe_to_csv_bytes(frame: pd.DataFrame) -> bytes:
    if frame.empty:
        return b""
    buffer = StringIO()
    frame.to_csv(buffer, index=False)
    return buffer.getvalue().encode("utf-8")


def make_export_filename(prefix: str) -> str:
    return f"{prefix}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
