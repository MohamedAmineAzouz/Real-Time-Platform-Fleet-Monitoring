"""Query repository for speed layer fleet snapshot data."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from config.settings import get_settings
from database.cassandra_client import query_dataframe
from utils.logging_utils import get_logger


logger = get_logger(__name__)
settings = get_settings()


TRUCK_LATEST_QUERY = """
SELECT
    truck_id,
    processed_at,
    event_time,
    latitude,
    longitude,
    speed,
    fuel_level,
    engine_temp,
    driver_id,
    start_city,
    end_city,
    odometer_km,
    refueling,
    anomaly,
    theft,
    alert_type,
    is_alert,
    distance_km,
    fuel_used,
    fuel_consumption_rate,
    high_consumption,
    fuel_consumed_trip,
    fuel_refueled,
    in_maintenance,
    maintenance_type,
    maintenance_desc
FROM truck_latest
"""


@st.cache_data(ttl=settings.refresh_cache_ttl_seconds, show_spinner=False)
def fetch_truck_latest_snapshot() -> pd.DataFrame:
    logger.info("Querying truck_latest speed layer snapshot")
    return query_dataframe(TRUCK_LATEST_QUERY)
