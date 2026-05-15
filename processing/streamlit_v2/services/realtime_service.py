"""Transform and summarize streaming truck snapshot analytics."""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from config.settings import get_settings
from database.repositories import fetch_truck_latest
from utils.formatters import safe_divide
from utils.logging_utils import get_logger


logger = get_logger(__name__)
settings = get_settings()

STREAMING_COLUMNS = [
    "truck_id",
    "processed_at",
    "event_time",
    "latitude",
    "longitude",
    "speed",
    "fuel_level",
    "engine_temp",
    "driver_id",
    "start_city",
    "end_city",
    "odometer_km",
    "refueling",
    "refuel_city",
    "anomaly",
    "theft",
    "theft_amount",
    "alert_type",
    "is_alert",
    "distance_km",
    "fuel_consumed_l",
    "fuel_consumed_trip",
    "fuel_refueled",
    "in_maintenance",
    "maintenance_type",
    "maintenance_desc",
]


def load_realtime_dataset(force_refresh: bool = False) -> pd.DataFrame:
    if force_refresh:
        fetch_truck_latest.clear()

    raw = fetch_truck_latest()
    logger.info("Realtime dataset rows=%s", len(raw))
    return _prepare_realtime_dataset(raw)


def _prepare_realtime_dataset(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=STREAMING_COLUMNS + ["status", "minutes_since_update", "risk_score"])

    df = frame.copy()
    for column in STREAMING_COLUMNS:
        if column not in df.columns:
            df[column] = None

    for column in ["processed_at", "event_time"]:
        df[column] = pd.to_datetime(df[column], errors="coerce")

    numeric_columns = [
        "speed",
        "fuel_level",
        "engine_temp",
        "latitude",
        "longitude",
        "distance_km",
        "fuel_consumed_l",
        "fuel_consumed_trip",
        "fuel_refueled",
        "odometer_km",
        "theft_amount",
    ]
    for column in numeric_columns:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    bool_columns = ["refueling", "theft", "is_alert", "in_maintenance"]
    for column in bool_columns:
        df[column] = df[column].fillna(False).astype(bool)

    df["truck_id"] = pd.to_numeric(df["truck_id"], errors="coerce").fillna(0).astype(int)
    df["truck_label"] = df["truck_id"].apply(lambda value: f"Truck {value:02d}")
    df["start_city"] = df["start_city"].fillna("Unknown")
    df["end_city"] = df["end_city"].fillna("Unknown")
    df["alert_type"] = df["alert_type"].fillna("NORMAL")
    df["anomaly"] = df["anomaly"].fillna("none")
    df["fuel_level"] = df["fuel_level"].fillna(0).clip(lower=0, upper=100)
    df["speed"] = df["speed"].fillna(0).clip(lower=0)
    df["engine_temp"] = df["engine_temp"].fillna(0)

    reference_time = pd.Timestamp.utcnow().tz_localize(None)
    freshness_anchor = df["event_time"].fillna(df["processed_at"])
    df["minutes_since_update"] = (
        (reference_time - freshness_anchor).dt.total_seconds().div(60).fillna(9999)
    )

    df["status"] = "Idle"
    df.loc[df["speed"] > 5, "status"] = "Moving"
    df.loc[df["refueling"], "status"] = "Refueling"
    df.loc[df["in_maintenance"], "status"] = "Maintenance"
    df.loc[df["minutes_since_update"] > settings.realtime_stale_after_minutes, "status"] = "Delayed"

    df["risk_score"] = (
        df["is_alert"].astype(int) * 30
        + (df["alert_type"] == "OVERSPEED").astype(int) * 20
        + (df["alert_type"] == "OVERHEAT").astype(int) * 25
        + (df["alert_type"] == "LOW_FUEL").astype(int) * 18
        + df["theft"].astype(int) * 30
        + df["in_maintenance"].astype(int) * 12
        + (df["fuel_level"] < settings.low_fuel_pct).astype(int) * 10
    )

    df["temperature_band"] = pd.cut(
        df["engine_temp"],
        bins=[-1, 75, settings.high_temp_c, 300],
        labels=["Nominal", "Elevated", "Critical"],
    ).astype(str)

    df["speed_band"] = pd.cut(
        df["speed"],
        bins=[-1, 5, 60, settings.overspeed_kmh, 250],
        labels=["Stopped", "Urban", "Cruising", "Overspeed"],
    ).astype(str)

    return df.sort_values(["risk_score", "event_time"], ascending=[False, False]).reset_index(drop=True)


def apply_realtime_filters(
    frame: pd.DataFrame,
    truck_ids: list[int] | None,
    cities: list[str] | None,
    alert_types: list[str] | None,
    max_age_minutes: int,
) -> pd.DataFrame:
    if frame.empty:
        return frame

    filtered = frame.copy()
    filtered = filtered[filtered["minutes_since_update"] <= max_age_minutes]

    if truck_ids:
        filtered = filtered[filtered["truck_id"].isin(truck_ids)]

    if cities:
        filtered = filtered[
            filtered["start_city"].isin(cities) | filtered["end_city"].isin(cities)
        ]

    if alert_types:
        filtered = filtered[filtered["alert_type"].isin(alert_types)]

    return filtered.reset_index(drop=True)


def build_realtime_summary(frame: pd.DataFrame) -> dict[str, float | int | str]:
    if frame.empty:
        return {
            "total_trucks": 0,
            "moving_trucks": 0,
            "active_alerts": 0,
            "maintenance_trucks": 0,
            "refueling_trucks": 0,
            "average_fuel_level": 0.0,
            "average_speed": 0.0,
            "max_engine_temp": 0.0,
            "heartbeat_minutes": 0.0,
        }

    heartbeat_minutes = float(frame["minutes_since_update"].min())
    return {
        "total_trucks": int(frame["truck_id"].nunique()),
        "moving_trucks": int((frame["status"] == "Moving").sum()),
        "active_alerts": int(frame["is_alert"].sum()),
        "maintenance_trucks": int(frame["in_maintenance"].sum()),
        "refueling_trucks": int(frame["refueling"].sum()),
        "average_fuel_level": float(frame["fuel_level"].mean()),
        "average_speed": float(frame["speed"].mean()),
        "max_engine_temp": float(frame["engine_temp"].max()),
        "heartbeat_minutes": heartbeat_minutes,
    }


def summarize_status_distribution(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["status", "truck_count"])
    return (
        frame.groupby("status", as_index=False)["truck_id"]
        .nunique()
        .rename(columns={"truck_id": "truck_count"})
        .sort_values("truck_count", ascending=False)
    )


def summarize_alert_distribution(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["alert_type", "count"])
    return (
        frame.groupby("alert_type", as_index=False)
        .size()
        .rename(columns={"size": "count"})
        .sort_values("count", ascending=False)
    )


def summarize_city_activity(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["city", "truck_count"])

    city_frame = pd.concat(
        [
            frame[["truck_id", "start_city"]].rename(columns={"start_city": "city"}),
            frame[["truck_id", "end_city"]].rename(columns={"end_city": "city"}),
        ],
        ignore_index=True,
    )

    return (
        city_frame.dropna()
        .groupby("city", as_index=False)["truck_id"]
        .nunique()
        .rename(columns={"truck_id": "truck_count"})
        .sort_values("truck_count", ascending=False)
    )


def build_realtime_operational_table(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame

    columns = [
        "truck_label",
        "status",
        "alert_type",
        "speed",
        "fuel_level",
        "engine_temp",
        "start_city",
        "end_city",
        "minutes_since_update",
        "anomaly",
        "maintenance_type",
    ]
    table = frame[columns].copy()
    table.rename(
        columns={
            "truck_label": "Truck",
            "status": "Status",
            "alert_type": "Alert",
            "speed": "Speed (km/h)",
            "fuel_level": "Fuel (%)",
            "engine_temp": "Engine Temp (C)",
            "start_city": "Origin",
            "end_city": "Destination",
            "minutes_since_update": "Freshness (min)",
            "anomaly": "Anomaly",
            "maintenance_type": "Maintenance",
        },
        inplace=True,
    )
    return table


def build_realtime_efficiency_snapshot(frame: pd.DataFrame) -> dict[str, float]:
    if frame.empty:
        return {"alert_rate_pct": 0.0, "maintenance_share_pct": 0.0, "live_share_pct": 0.0}

    total = max(len(frame), 1)
    return {
        "alert_rate_pct": frame["is_alert"].sum() / total * 100,
        "maintenance_share_pct": frame["in_maintenance"].sum() / total * 100,
        "live_share_pct": (frame["minutes_since_update"] <= settings.realtime_stale_after_minutes).sum() / total * 100,
    }
