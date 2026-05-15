"""Formatting helpers for enterprise dashboard presentation."""

from __future__ import annotations

from datetime import date, datetime
from io import BytesIO
from typing import Any

import pandas as pd


def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    if denominator in (0, 0.0, None):
        return default
    return numerator / denominator


def format_km(value: Any) -> str:
    return f"{float(value):,.1f} km" if value is not None else "0.0 km"


def format_liters(value: Any) -> str:
    return f"{float(value):,.1f} L" if value is not None else "0.0 L"


def format_percent(value: Any, digits: int = 1) -> str:
    return f"{float(value):,.{digits}f}%" if value is not None else "0.0%"


def format_number(value: Any, digits: int = 0) -> str:
    if value is None:
        return "0"
    return f"{float(value):,.{digits}f}"


def format_hours(value: Any) -> str:
    return f"{float(value):,.2f} h" if value is not None else "0.00 h"


def format_temperature(value: Any) -> str:
    return f"{float(value):,.1f} C" if value is not None else "0.0 C"


def format_relative_minutes(value: Any) -> str:
    if value is None:
        return "Unknown"

    minutes = float(value)
    if minutes < 1:
        return "Just now"
    if minutes < 60:
        return f"{minutes:.0f} min ago"
    return f"{minutes / 60:.1f} h ago"


def format_date_label(value: date | datetime | str) -> str:
    if isinstance(value, str):
        parsed = pd.to_datetime(value, errors="coerce")
        return parsed.strftime("%Y-%m-%d") if not pd.isna(parsed) else value
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    return value.isoformat()


def dataframe_to_csv_bytes(frame: pd.DataFrame) -> bytes:
    if frame.empty:
        return b""
    buffer = BytesIO()
    frame.to_csv(buffer, index=False)
    return buffer.getvalue()


def make_export_filename(prefix: str, suffix: str | None = None) -> str:
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    final_suffix = f"_{suffix}" if suffix else ""
    return f"{prefix}{final_suffix}_{stamp}.csv"
