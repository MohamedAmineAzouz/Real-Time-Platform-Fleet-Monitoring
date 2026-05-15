"""Core speed layer analytics built from the truck_latest snapshot."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from config.settings import get_settings
from database.repositories import fetch_truck_latest_snapshot
from utils.logging_utils import get_logger


logger = get_logger(__name__)
settings = get_settings()


NUMERIC_COLUMNS = [
    "truck_id",
    "latitude",
    "longitude",
    "speed",
    "fuel_level",
    "engine_temp",
    "odometer_km",
    "distance_km",
    "fuel_used",
    "fuel_consumption_rate",
    "fuel_consumed_trip",
    "fuel_refueled",
]


@dataclass(frozen=True)
class DashboardFilters:
    truck_ids: list[int]
    driver_ids: list[str]
    alert_types: list[str]
    cities: list[str]
    maintenance_status: str
    theft_only: bool
    active_alerts_only: bool
    fuel_range: tuple[float, float]
    speed_range: tuple[float, float]


def load_speed_layer_snapshot(force_refresh: bool = False) -> pd.DataFrame:
    if force_refresh:
        fetch_truck_latest_snapshot.clear()
    raw = fetch_truck_latest_snapshot()
    logger.info("Loaded raw speed layer snapshot rows=%s", len(raw))
    return _normalize_snapshot(raw)


def _normalize_snapshot(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()

    df = frame.copy()
    for column in NUMERIC_COLUMNS:
        if column not in df.columns:
            df[column] = 0
        df[column] = pd.to_numeric(df[column], errors="coerce").fillna(0)

    for column in ["processed_at", "event_time"]:
        if column not in df.columns:
            df[column] = pd.NaT
        df[column] = pd.to_datetime(df[column], errors="coerce").dt.tz_localize(None)

    bool_columns = ["refueling", "theft", "is_alert", "high_consumption", "in_maintenance"]
    for column in bool_columns:
        if column not in df.columns:
            df[column] = False
        df[column] = df[column].fillna(False).astype(bool)

    text_columns = ["driver_id", "start_city", "end_city", "alert_type", "anomaly", "maintenance_type", "maintenance_desc"]
    for column in text_columns:
        if column not in df.columns:
            df[column] = ""
        df[column] = df[column].fillna("")

    now = pd.Timestamp.utcnow().tz_localize(None)
    freshness_source = df["processed_at"].where(df["processed_at"].notna(), df["event_time"])
    df["latency_seconds"] = (now - freshness_source).dt.total_seconds().fillna(settings.stale_after_seconds * 10)
    df["truck_label"] = df["truck_id"].astype(int).map(lambda value: f"Truck {value:02d}")
    df["driver_label"] = df["driver_id"].replace("", "Unassigned")
    df["route_label"] = df["start_city"].replace("", "Unknown") + " -> " + df["end_city"].replace("", "Unknown")
    df["city_context"] = df["start_city"].replace("", "Unknown")
    df.loc[df["end_city"] != "", "city_context"] = df["city_context"] + " / " + df["end_city"]
    df["alert_type"] = df["alert_type"].replace("", "NORMAL")
    df["anomaly"] = df["anomaly"].replace("", "none")

    if (df["fuel_consumption_rate"] == 0).all():
        df["fuel_consumption_rate"] = (
            (df["fuel_used"].replace(0, pd.NA) / df["distance_km"].replace(0, pd.NA)) * 100
        ).fillna(0)

    df["fuel_consumption_rate"] = df["fuel_consumption_rate"].clip(lower=0)
    df["fuel_level"] = df["fuel_level"].clip(lower=0, upper=100)
    df["speed"] = df["speed"].clip(lower=0)
    df["engine_temp"] = df["engine_temp"].clip(lower=0)

    df["high_consumption_live"] = df["high_consumption"] | (df["fuel_consumption_rate"] >= 35) | (df["fuel_used"] >= 6)
    df["operational_status"] = "Healthy"
    df.loc[df["latency_seconds"] > settings.stale_after_seconds, "operational_status"] = "Delayed"
    df.loc[df["speed"] > 5, "operational_status"] = "In Transit"
    df.loc[df["refueling"], "operational_status"] = "Refueling"
    df.loc[df["in_maintenance"], "operational_status"] = "Maintenance"
    df.loc[df["is_alert"] | df["theft"], "operational_status"] = "Alert"

    df["severity"] = "Normal"
    df.loc[df["fuel_level"] <= settings.low_fuel_pct, "severity"] = "Medium"
    df.loc[df["speed"] >= settings.overspeed_kmh, "severity"] = "High"
    df.loc[df["in_maintenance"], "severity"] = "High"
    df.loc[df["engine_temp"] >= settings.high_temp_c, "severity"] = "High"
    df.loc[df["theft"] | (df["engine_temp"] >= settings.critical_temp_c) | (df["speed"] >= settings.critical_speed_kmh), "severity"] = "Critical"
    df["severity_rank"] = df["severity"].map({"Normal": 0, "Medium": 1, "High": 2, "Critical": 3}).fillna(0)

    df["state_color"] = df["severity"].map(
        {
            "Normal": [56, 189, 100],
            "Medium": [250, 204, 21],
            "High": [249, 115, 22],
            "Critical": [239, 68, 68],
        }
    )
    df["state_color"] = df["state_color"].where(df["state_color"].notna(), [[56, 189, 100]] * len(df))
    df.loc[df["in_maintenance"], "state_color"] = [[249, 115, 22]] * int(df["in_maintenance"].sum())
    df.loc[(df["anomaly"] != "none") & ~df["in_maintenance"] & ~(df["severity"] == "Critical"), "state_color"] = [[250, 204, 21]] * int(((df["anomaly"] != "none") & ~df["in_maintenance"] & ~(df["severity"] == "Critical")).sum())

    df["marker_radius"] = (
        18000
        + df["speed"].clip(upper=140) * 130
        + df["severity"].map({"Normal": 0, "Medium": 3000, "High": 6000, "Critical": 9000}).fillna(0)
    )

    df["fuel_efficiency_score"] = (
        100
        - df["fuel_consumption_rate"].clip(upper=60) * 1.2
        - df["high_consumption_live"].astype(int) * 18
        - (100 - df["fuel_level"]).clip(lower=0) * 0.18
    ).clip(lower=0, upper=100)

    return df.sort_values(["severity_rank", "speed", "engine_temp"], ascending=[False, False, False]).reset_index(drop=True)


def apply_view_filters(snapshot: pd.DataFrame, buffer: pd.DataFrame) -> pd.DataFrame:
    if snapshot.empty:
        return snapshot

    if buffer.empty:
        snapshot["recent_speed_delta"] = 0.0
        snapshot["recent_fuel_drop_pct"] = 0.0
        snapshot["recent_distance_delta_km"] = 0.0
        snapshot["implied_speed_kmh"] = 0.0
        snapshot["gps_behavior_flag"] = False
        return snapshot

    scoped = buffer.copy().sort_values(["truck_id", "buffer_captured_at"])
    scoped["prev_speed"] = scoped.groupby("truck_id")["speed"].shift(1)
    scoped["prev_fuel_level"] = scoped.groupby("truck_id")["fuel_level"].shift(1)
    scoped["prev_odometer"] = scoped.groupby("truck_id")["odometer_km"].shift(1)
    scoped["recent_speed_delta"] = (scoped["speed"] - scoped["prev_speed"]).fillna(0)
    scoped["recent_fuel_drop_pct"] = (scoped["prev_fuel_level"] - scoped["fuel_level"]).fillna(0).clip(lower=0)
    scoped["recent_distance_delta_km"] = (scoped["odometer_km"] - scoped["prev_odometer"]).fillna(scoped["distance_km"]).clip(lower=0)
    scoped["implied_speed_kmh"] = (
        scoped["recent_distance_delta_km"] / (settings.refresh_interval_seconds / 3600.0)
    ).fillna(0)
    latest_features = scoped.sort_values("buffer_captured_at").groupby("truck_id").tail(1)[
        ["truck_id", "recent_speed_delta", "recent_fuel_drop_pct", "recent_distance_delta_km", "implied_speed_kmh"]
    ]
    enriched = snapshot.merge(latest_features, on="truck_id", how="left")
    for column in ["recent_speed_delta", "recent_fuel_drop_pct", "recent_distance_delta_km", "implied_speed_kmh"]:
        enriched[column] = enriched[column].fillna(0)
    enriched["gps_behavior_flag"] = (
        (enriched["implied_speed_kmh"] >= settings.gps_jump_speed_kmh)
        | ((enriched["recent_distance_delta_km"] <= settings.no_movement_distance_km) & (enriched["speed"] >= 80))
    )
    return enriched


def build_sidebar_filter_options(snapshot: pd.DataFrame) -> dict[str, object]:
    if snapshot.empty:
        return {
            "truck_ids": [],
            "driver_ids": [],
            "alert_types": [],
            "cities": [],
            "speed_range": (0.0, 140.0),
            "fuel_range": (0.0, 60.0),
        }

    cities = sorted({city for city in pd.concat([snapshot["start_city"], snapshot["end_city"]]).unique().tolist() if city})
    return {
        "truck_ids": sorted(snapshot["truck_id"].astype(int).tolist()),
        "driver_ids": sorted([driver for driver in snapshot["driver_label"].unique().tolist() if driver]),
        "alert_types": sorted([alert for alert in snapshot["alert_type"].unique().tolist() if alert and alert != "NORMAL"]),
        "cities": cities,
        "speed_range": (
            float(snapshot["speed"].min()),
            float(max(snapshot["speed"].max(), settings.critical_speed_kmh)),
        ),
        "fuel_range": (
            float(snapshot["fuel_consumption_rate"].min()),
            float(max(snapshot["fuel_consumption_rate"].max(), 40)),
        ),
    }


def apply_dashboard_filters(snapshot: pd.DataFrame, filters: DashboardFilters) -> pd.DataFrame:
    if snapshot.empty:
        return snapshot

    filtered = snapshot.copy()
    if filters.truck_ids:
        filtered = filtered[filtered["truck_id"].isin(filters.truck_ids)]
    if filters.driver_ids:
        filtered = filtered[filtered["driver_label"].isin(filters.driver_ids)]
    if filters.alert_types:
        filtered = filtered[filtered["alert_type"].isin(filters.alert_types)]
    if filters.cities:
        filtered = filtered[
            filtered["start_city"].isin(filters.cities)
            | filtered["end_city"].isin(filters.cities)
        ]

    if filters.maintenance_status == "In Maintenance":
        filtered = filtered[filtered["in_maintenance"]]
    elif filters.maintenance_status == "Operational Only":
        filtered = filtered[~filtered["in_maintenance"]]

    if filters.theft_only:
        filtered = filtered[filtered["theft"]]
    if filters.active_alerts_only:
        filtered = filtered[filtered["is_alert"]]

    filtered = filtered[
        filtered["fuel_consumption_rate"].between(filters.fuel_range[0], filters.fuel_range[1], inclusive="both")
        & filtered["speed"].between(filters.speed_range[0], filters.speed_range[1], inclusive="both")
    ]
    return filtered.reset_index(drop=True)


def build_operational_summary(
    snapshot: pd.DataFrame,
    metric_history: pd.DataFrame,
    anomalies: pd.DataFrame,
    maintenance_view: pd.DataFrame,
) -> dict[str, float | int | str]:
    if snapshot.empty:
        return {
            "active_trucks": 0,
            "active_alerts": 0,
            "maintenance_trucks": 0,
            "theft_incidents": 0,
            "average_speed": 0.0,
            "average_fuel_level": 0.0,
            "high_consumption_trucks": 0,
            "average_engine_temperature": 0.0,
            "fuel_efficiency_score": 0.0,
            "total_distance_covered": 0.0,
            "total_streaming_events": 0,
            "system_health": "No Data",
            "last_event_time": None,
        }

    latest_distance = float(metric_history["total_distance"].sum()) if not metric_history.empty else float(snapshot["distance_km"].sum())
    total_streaming_events = int(metric_history["streaming_events"].sum()) if not metric_history.empty else int(len(snapshot))
    system_health = "Healthy"
    if float(snapshot["latency_seconds"].max()) > settings.stale_after_seconds * 2:
        system_health = "Degraded"
    if int(snapshot["severity"].isin(["Critical"]).sum()) >= max(1, len(snapshot) // 5):
        system_health = "Critical"

    return {
        "active_trucks": int(snapshot["truck_id"].nunique()),
        "active_alerts": int(snapshot["is_alert"].sum()),
        "maintenance_trucks": int(snapshot["in_maintenance"].sum()),
        "theft_incidents": int(snapshot["theft"].sum()),
        "average_speed": float(snapshot["speed"].mean()),
        "average_fuel_level": float(snapshot["fuel_level"].mean()),
        "high_consumption_trucks": int(snapshot["high_consumption_live"].sum()),
        "average_engine_temperature": float(snapshot["engine_temp"].mean()),
        "fuel_efficiency_score": float(snapshot["fuel_efficiency_score"].mean()),
        "total_distance_covered": latest_distance,
        "total_streaming_events": total_streaming_events,
        "system_health": system_health,
        "last_event_time": snapshot["processed_at"].max(),
        "critical_anomalies": int((anomalies["severity"] == "Critical").sum()) if not anomalies.empty else 0,
        "predicted_failures": int((maintenance_view["predicted_failure_band"] == "Critical").sum()) if not maintenance_view.empty else 0,
        "live_event_rate": int(metric_history["streaming_events"].iloc[-1]) if not metric_history.empty else int(len(snapshot)),
    }


def build_system_health_payload(summary: dict[str, float | int | str], metric_history: pd.DataFrame) -> dict[str, object]:
    latest_latency = 0.0
    if not metric_history.empty:
        latest_latency = float(metric_history["buffer_captured_at"].diff().dt.total_seconds().fillna(0).tail(1).iloc[0])
    health_score = (
        100
        - int(summary["active_alerts"]) * 4
        - int(summary["theft_incidents"]) * 12
        - int(summary["maintenance_trucks"]) * 3
        - int(summary["critical_anomalies"]) * 6
    )
    health_score = max(0, min(100, health_score))
    return {
        "status_label": str(summary["system_health"]),
        "health_score": health_score,
        "freshness_seconds": latest_latency,
        "live_events": int(summary["total_streaming_events"]),
        "healthy_ratio_pct": max(0.0, 100 - (int(summary["active_alerts"]) / max(int(summary["active_trucks"]), 1) * 100)),
    }


def _metric_series(metric_history: pd.DataFrame, column: str) -> list[float]:
    if metric_history.empty or column not in metric_history.columns:
        return [0.0]
    series = metric_history[column].tail(18).fillna(0).tolist()
    return [float(value) for value in series] if series else [0.0]


def _metric_delta(metric_history: pd.DataFrame, column: str) -> float:
    if metric_history.empty or column not in metric_history.columns or len(metric_history) < 2:
        return 0.0
    latest = float(metric_history[column].iloc[-1])
    previous = float(metric_history[column].iloc[-2])
    if previous == 0:
        return 0.0
    return ((latest - previous) / previous) * 100


def build_kpi_models(summary: dict[str, float | int | str], metric_history: pd.DataFrame) -> list[dict[str, object]]:
    return [
        _kpi("TR", "Active Trucks", int(summary["active_trucks"]), _metric_delta(metric_history, "active_trucks"), _metric_series(metric_history, "active_trucks"), "primary"),
        _kpi("AL", "Active Alerts", int(summary["active_alerts"]), _metric_delta(metric_history, "active_alerts"), _metric_series(metric_history, "active_alerts"), "danger"),
        _kpi("MT", "Trucks in Maintenance", int(summary["maintenance_trucks"]), _metric_delta(metric_history, "maintenance_trucks"), _metric_series(metric_history, "maintenance_trucks"), "warning"),
        _kpi("TH", "Theft Incidents", int(summary["theft_incidents"]), _metric_delta(metric_history, "theft_incidents"), _metric_series(metric_history, "theft_incidents"), "danger"),
        _kpi("SP", "Average Speed", f"{summary['average_speed']:.1f}", _metric_delta(metric_history, "average_speed"), _metric_series(metric_history, "average_speed"), "primary", "km/h"),
        _kpi("FL", "Average Fuel Level", f"{summary['average_fuel_level']:.1f}", _metric_delta(metric_history, "average_fuel"), _metric_series(metric_history, "average_fuel"), "warning", "%"),
        _kpi("HC", "High Consumption Trucks", int(summary["high_consumption_trucks"]), _metric_delta(metric_history, "high_consumption_trucks"), _metric_series(metric_history, "high_consumption_trucks"), "warning"),
        _kpi("ET", "Average Engine Temp", f"{summary['average_engine_temperature']:.1f}", _metric_delta(metric_history, "average_engine_temp"), _metric_series(metric_history, "average_engine_temp"), "danger", "C"),
        _kpi("ES", "Fuel Efficiency Score", f"{summary['fuel_efficiency_score']:.0f}", _metric_delta(metric_history, "fuel_efficiency_score"), _metric_series(metric_history, "fuel_efficiency_score"), "primary"),
        _kpi("KM", "Total Distance Covered", f"{summary['total_distance_covered']:.1f}", _metric_delta(metric_history, "total_distance"), _metric_series(metric_history, "total_distance"), "primary", "km"),
    ]


def _kpi(icon: str, label: str, value: object, delta_pct: float, sparkline: list[float], tone: str, suffix: str = "") -> dict[str, object]:
    return {
        "icon": icon,
        "label": label,
        "value": value,
        "suffix": suffix,
        "delta_pct": delta_pct,
        "sparkline": sparkline,
        "tone": tone,
    }


def build_table_dataset(snapshot: pd.DataFrame) -> pd.DataFrame:
    if snapshot.empty:
        return snapshot

    table = snapshot.copy()
    table["maintenance"] = table["maintenance_type"].where(table["in_maintenance"], "No")
    return table[
        [
            "truck_id",
            "driver_label",
            "speed",
            "fuel_level",
            "engine_temp",
            "alert_type",
            "anomaly",
            "theft",
            "maintenance",
            "city_context",
            "processed_at",
            "severity",
            "fuel_consumption_rate",
            "high_consumption_live",
            "route_label",
        ]
    ].rename(
        columns={
            "driver_label": "driver_id",
            "city_context": "city",
        }
    )


def build_selected_truck_timeline(buffer: pd.DataFrame, selected_truck_ids: list[int]) -> pd.DataFrame:
    if buffer.empty:
        return pd.DataFrame()

    scoped = buffer.copy()
    if selected_truck_ids:
        scoped = scoped[scoped["truck_id"].isin(selected_truck_ids)]

    scoped["buffer_captured_at"] = pd.to_datetime(scoped["buffer_captured_at"], errors="coerce")
    return scoped.sort_values(["truck_id", "buffer_captured_at"]).reset_index(drop=True)
