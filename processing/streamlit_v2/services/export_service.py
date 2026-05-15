"""Export helpers for the analytics platform."""

from __future__ import annotations

import pandas as pd

from utils.formatters import dataframe_to_csv_bytes, make_export_filename


def build_csv_export(frame: pd.DataFrame, prefix: str, suffix: str | None = None) -> tuple[bytes, str]:
    return dataframe_to_csv_bytes(frame), make_export_filename(prefix, suffix)
