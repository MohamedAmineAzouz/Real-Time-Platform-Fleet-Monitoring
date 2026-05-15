"""Formatting helpers for enterprise analytics surfaces."""

from __future__ import annotations

from datetime import datetime

import pandas as pd


def humanize_timestamp(value: object) -> str:
    if value is None or value == "":
        return "Unknown"
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return str(value)
    return parsed.strftime("%Y-%m-%d %H:%M:%S")


def humanize_latency(seconds: float) -> str:
    if seconds <= 1:
        return "sub-second"
    if seconds < 60:
        return f"{seconds:.0f}s"
    return f"{seconds / 60:.1f}m"


def format_delta(delta_pct: float) -> str:
    sign = "+" if delta_pct >= 0 else ""
    return f"{sign}{delta_pct:.1f}%"


def format_number(value: float | int, digits: int = 0) -> str:
    return f"{value:,.{digits}f}"


def format_metric(value: object, suffix: str = "") -> str:
    if isinstance(value, float):
        if suffix:
            return f"{value:,.1f}{suffix}"
        return f"{value:,.1f}"
    return f"{value}{suffix}"
