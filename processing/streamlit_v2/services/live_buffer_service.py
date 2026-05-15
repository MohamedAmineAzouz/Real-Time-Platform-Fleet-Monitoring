"""Session-based live snapshot history for streaming-style analytics."""

from __future__ import annotations

import hashlib
from datetime import datetime

import pandas as pd
import streamlit as st

from config.settings import get_settings
from utils.logging_utils import get_logger


logger = get_logger(__name__)
settings = get_settings()


BUFFER_KEY = "live_snapshot_buffer"
BUFFER_HASH_KEY = "live_snapshot_hash"
BUFFER_SEQ_KEY = "live_snapshot_sequence"


def _signature(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "empty"
    signature_columns = [
        "truck_id",
        "processed_at",
        "event_time",
        "speed",
        "fuel_level",
        "engine_temp",
        "alert_type",
        "anomaly",
        "theft",
        "in_maintenance",
    ]
    scoped = frame.copy()
    for column in signature_columns:
        if column not in scoped.columns:
            scoped[column] = None
    payload = scoped[signature_columns].sort_values("truck_id").to_json(orient="records", date_format="iso")
    return hashlib.md5(payload.encode("utf-8")).hexdigest()


def update_live_buffer(snapshot: pd.DataFrame) -> pd.DataFrame:
    st.session_state.setdefault(BUFFER_KEY, pd.DataFrame())
    st.session_state.setdefault(BUFFER_HASH_KEY, "")
    st.session_state.setdefault(BUFFER_SEQ_KEY, 0)

    current_hash = _signature(snapshot)
    if current_hash == st.session_state[BUFFER_HASH_KEY]:
        return st.session_state[BUFFER_KEY]

    buffer = st.session_state[BUFFER_KEY]
    refresh_sequence = int(st.session_state[BUFFER_SEQ_KEY]) + 1
    captured_at = pd.Timestamp.utcnow().tz_localize(None)

    appended = snapshot.copy()
    appended["buffer_refresh_id"] = refresh_sequence
    appended["buffer_captured_at"] = captured_at

    buffer = pd.concat([buffer, appended], ignore_index=True)

    unique_refreshes = buffer["buffer_refresh_id"].drop_duplicates().sort_values().tolist()
    if len(unique_refreshes) > settings.max_buffer_snapshots:
        keep_refreshes = unique_refreshes[-settings.max_buffer_snapshots :]
        buffer = buffer[buffer["buffer_refresh_id"].isin(keep_refreshes)].reset_index(drop=True)

    st.session_state[BUFFER_KEY] = buffer
    st.session_state[BUFFER_HASH_KEY] = current_hash
    st.session_state[BUFFER_SEQ_KEY] = refresh_sequence
    logger.info("Appended live snapshot to buffer refresh=%s rows=%s", refresh_sequence, len(appended))
    return buffer


def build_metric_history(buffer: pd.DataFrame) -> pd.DataFrame:
    if buffer.empty:
        return pd.DataFrame()

    scoped = buffer.copy()
    scoped["buffer_captured_at"] = pd.to_datetime(scoped["buffer_captured_at"], errors="coerce")
    scoped["speed"] = pd.to_numeric(scoped["speed"], errors="coerce").fillna(0)
    scoped["fuel_level"] = pd.to_numeric(scoped["fuel_level"], errors="coerce").fillna(0)
    scoped["engine_temp"] = pd.to_numeric(scoped["engine_temp"], errors="coerce").fillna(0)
    scoped["distance_km"] = pd.to_numeric(scoped.get("distance_km"), errors="coerce").fillna(0)
    scoped["high_consumption_metric"] = (
        scoped.get("high_consumption_live", scoped.get("high_consumption", False))
        .fillna(False)
        .astype(int)
    )

    history = (
        scoped.groupby(["buffer_refresh_id", "buffer_captured_at"], as_index=False)
        .agg(
            active_trucks=("truck_id", "nunique"),
            active_alerts=("is_alert", "sum"),
            maintenance_trucks=("in_maintenance", "sum"),
            theft_incidents=("theft", "sum"),
            average_speed=("speed", "mean"),
            average_fuel=("fuel_level", "mean"),
            high_consumption_trucks=("high_consumption_metric", "sum"),
            average_engine_temp=("engine_temp", "mean"),
            total_distance=("distance_km", "sum"),
            streaming_events=("truck_id", "count"),
            refueling_trucks=("refueling", "sum"),
        )
        .sort_values("buffer_refresh_id")
    )

    history["fuel_efficiency_score"] = (
        100
        - (history["high_consumption_trucks"] * 7)
        - (history["refueling_trucks"] * 3)
        - (history["average_engine_temp"] - 75).clip(lower=0) * 0.9
    ).clip(lower=0, upper=100)
    return history.reset_index(drop=True)


def filter_buffer_by_trucks(buffer: pd.DataFrame, truck_ids: list[int]) -> pd.DataFrame:
    if buffer.empty or not truck_ids:
        return buffer
    return buffer[buffer["truck_id"].isin(truck_ids)].reset_index(drop=True)
