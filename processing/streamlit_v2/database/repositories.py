"""Reusable repository functions for analytics datasets."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from config.settings import get_settings
from database.connection import query_dataframe
from utils.logging_utils import get_logger


logger = get_logger(__name__)
settings = get_settings()


@st.cache_data(ttl=settings.realtime_cache_ttl_seconds, show_spinner=False)
def fetch_truck_latest() -> pd.DataFrame:
    logger.info("Fetching latest truck snapshot")
    return query_dataframe("SELECT * FROM truck_latest")


@st.cache_data(ttl=settings.batch_cache_ttl_seconds, show_spinner=False)
def fetch_daily_batch_partition(stat_date: str) -> pd.DataFrame:
    logger.info("Fetching batch partition for date=%s", stat_date)
    return query_dataframe(
        "SELECT * FROM batch_daily_truck_stats WHERE stat_date = %s",
        [stat_date],
    )


def fetch_daily_batch_range(start_date: date, end_date: date) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    cursor = start_date
    while cursor <= end_date:
        frame = fetch_daily_batch_partition(cursor.isoformat())
        if not frame.empty:
            frames.append(frame)
        cursor += timedelta(days=1)

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def find_latest_batch_date(reference_date: date | None = None) -> date | None:
    current = reference_date or date.today()
    for offset in range(settings.batch_latest_search_days):
        candidate = current - timedelta(days=offset)
        frame = fetch_daily_batch_partition(candidate.isoformat())
        if not frame.empty:
            return candidate
    return None
