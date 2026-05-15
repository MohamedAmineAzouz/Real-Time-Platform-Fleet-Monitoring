"""Anomaly and maintenance intelligence derived from live speed layer snapshots."""

from __future__ import annotations

import math

import pandas as pd

from config.settings import get_settings
from utils.logging_utils import get_logger


logger = get_logger(__name__)
settings = get_settings()


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return 2 * radius * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def detect_live_anomalies(buffer: pd.DataFrame, snapshot: pd.DataFrame) -> pd.DataFrame:
    if buffer.empty:
        return pd.DataFrame()

    scoped = buffer.copy().sort_values(["truck_id", "buffer_captured_at"])
    scoped["buffer_captured_at"] = pd.to_datetime(scoped["buffer_captured_at"], errors="coerce")
    scoped["prev_fuel_level"] = scoped.groupby("truck_id")["fuel_level"].shift(1)
    scoped["prev_speed"] = scoped.groupby("truck_id")["speed"].shift(1)
    scoped["prev_engine_temp"] = scoped.groupby("truck_id")["engine_temp"].shift(1)
    scoped["prev_latitude"] = scoped.groupby("truck_id")["latitude"].shift(1)
    scoped["prev_longitude"] = scoped.groupby("truck_id")["longitude"].shift(1)
    scoped["prev_time"] = scoped.groupby("truck_id")["buffer_captured_at"].shift(1)

    records: list[dict[str, object]] = []
    for row in scoped.itertuples(index=False):
        if pd.isna(row.prev_time):
            continue

        elapsed_seconds = max((row.buffer_captured_at - row.prev_time).total_seconds(), 1)
        elapsed_hours = elapsed_seconds / 3600.0
        geo_distance = 0.0
        if not any(pd.isna(value) for value in [row.latitude, row.longitude, row.prev_latitude, row.prev_longitude]):
            geo_distance = _haversine_km(float(row.prev_latitude), float(row.prev_longitude), float(row.latitude), float(row.longitude))
        implied_speed = geo_distance / elapsed_hours if elapsed_hours > 0 else 0.0
        fuel_drop_pct = max(float(row.prev_fuel_level or 0) - float(row.fuel_level or 0), 0.0)
        speed_delta = abs(float(row.speed or 0) - float(row.prev_speed or 0))
        temp_delta = abs(float(row.engine_temp or 0) - float(row.prev_engine_temp or 0))

        route_text = f"{row.start_city or 'Unknown'} -> {row.end_city or 'Unknown'}"
        base_payload = {
            "truck_id": int(row.truck_id),
            "driver_id": row.driver_id or "Unassigned",
            "occurred_at": row.buffer_captured_at,
            "route": route_text,
            "alert_type": row.alert_type or "NORMAL",
        }

        if bool(row.theft):
            records.append(
                {
                    **base_payload,
                    "category": "Fuel Theft",
                    "severity": "Critical",
                    "score": 96,
                    "message": "Live theft flag detected by the speed layer.",
                }
            )
        if fuel_drop_pct >= settings.suspicious_fuel_drop_pct and not bool(row.refueling):
            records.append(
                {
                    **base_payload,
                    "category": "Suspicious Fuel Drop",
                    "severity": "High" if fuel_drop_pct < settings.suspicious_fuel_drop_pct * 1.5 else "Critical",
                    "score": min(99, 70 + fuel_drop_pct * 3),
                    "message": f"Fuel dropped by {fuel_drop_pct:.1f}% between live refresh intervals.",
                }
            )
        if float(row.speed or 0) >= settings.critical_speed_kmh:
            records.append(
                {
                    **base_payload,
                    "category": "Critical Overspeed",
                    "severity": "Critical",
                    "score": min(99, 78 + float(row.speed or 0) * 0.1),
                    "message": f"Truck is moving at {float(row.speed or 0):.1f} km/h.",
                }
            )
        elif float(row.speed or 0) >= settings.overspeed_kmh:
            records.append(
                {
                    **base_payload,
                    "category": "Overspeed",
                    "severity": "High",
                    "score": min(95, 60 + float(row.speed or 0) * 0.15),
                    "message": f"Truck exceeded the overspeed threshold at {float(row.speed or 0):.1f} km/h.",
                }
            )
        if float(row.engine_temp or 0) >= settings.critical_temp_c:
            records.append(
                {
                    **base_payload,
                    "category": "Engine Overheat",
                    "severity": "Critical",
                    "score": min(99, 80 + float(row.engine_temp or 0) * 0.08),
                    "message": f"Engine temperature reached {float(row.engine_temp or 0):.1f} C.",
                }
            )
        elif float(row.engine_temp or 0) >= settings.high_temp_c or temp_delta >= 10:
            records.append(
                {
                    **base_payload,
                    "category": "Engine Temperature",
                    "severity": "High",
                    "score": min(94, 60 + float(row.engine_temp or 0) * 0.1),
                    "message": f"Engine temperature is elevated at {float(row.engine_temp or 0):.1f} C.",
                }
            )
        if implied_speed >= settings.gps_jump_speed_kmh:
            records.append(
                {
                    **base_payload,
                    "category": "GPS Jump",
                    "severity": "Critical",
                    "score": min(99, 85 + implied_speed * 0.05),
                    "message": f"GPS jump implies {implied_speed:.1f} km/h movement between refreshes.",
                }
            )
        if geo_distance <= settings.no_movement_distance_km and float(row.speed or 0) >= 80:
            records.append(
                {
                    **base_payload,
                    "category": "Suspicious GPS Drift",
                    "severity": "High",
                    "score": min(96, 72 + speed_delta),
                    "message": "Truck reports high speed while GPS movement remains near-zero.",
                }
            )

    anomaly_df = pd.DataFrame(records)
    if anomaly_df.empty:
        return anomaly_df

    anomaly_df = anomaly_df.sort_values(["occurred_at", "score"], ascending=[False, False]).reset_index(drop=True)
    logger.info("Detected %s live anomalies from the session buffer", len(anomaly_df))
    return anomaly_df


def build_live_alert_feed(snapshot: pd.DataFrame, anomalies: pd.DataFrame) -> pd.DataFrame:
    alert_rows = []
    if not snapshot.empty:
        scoped = snapshot[snapshot["is_alert"] | snapshot["theft"] | snapshot["in_maintenance"]].copy()
        for row in scoped.itertuples(index=False):
            severity = row.severity if hasattr(row, "severity") else "Medium"
            if bool(row.theft):
                severity = "Critical"
            elif bool(row.in_maintenance):
                severity = "High"
            elif row.alert_type in {"OVERHEAT", "FUEL_THEFT"}:
                severity = "Critical"
            alert_rows.append(
                {
                    "truck_id": int(row.truck_id),
                    "timestamp": row.processed_at,
                    "severity": severity,
                    "title": row.alert_type.replace("_", " ").title() if row.alert_type else "Maintenance Alert",
                    "message": f"{row.start_city} -> {row.end_city}",
                    "driver_id": row.driver_id or "Unassigned",
                }
            )

    if not anomalies.empty:
        for row in anomalies.head(30).itertuples(index=False):
            alert_rows.append(
                {
                    "truck_id": int(row.truck_id),
                    "timestamp": row.occurred_at,
                    "severity": row.severity,
                    "title": row.category,
                    "message": row.message,
                    "driver_id": row.driver_id,
                }
            )

    if not alert_rows:
        return pd.DataFrame(columns=["truck_id", "timestamp", "severity", "title", "message", "driver_id"])

    feed = pd.DataFrame(alert_rows).drop_duplicates(subset=["truck_id", "title", "timestamp"])
    return feed.sort_values("timestamp", ascending=False).head(18).reset_index(drop=True)


def build_maintenance_view(snapshot: pd.DataFrame, anomalies: pd.DataFrame) -> pd.DataFrame:
    if snapshot.empty:
        return pd.DataFrame()

    scoped = snapshot.copy()
    problem_counts = (
        anomalies.groupby("truck_id", as_index=False)
        .agg(
            anomaly_events=("category", "count"),
            anomaly_score=("score", "sum"),
        )
        if not anomalies.empty
        else pd.DataFrame(columns=["truck_id", "anomaly_events", "anomaly_score"])
    )
    scoped = scoped.merge(problem_counts, on="truck_id", how="left")
    scoped["anomaly_events"] = scoped["anomaly_events"].fillna(0)
    scoped["anomaly_score"] = scoped["anomaly_score"].fillna(0)
    scoped["predicted_failure_score"] = (
        (scoped["engine_temp"] - 75).clip(lower=0) * 1.1
        + scoped["anomaly_events"] * 6
        + scoped["anomaly_score"] * 0.12
        + scoped["high_consumption_live"].astype(int) * 14
        + scoped["in_maintenance"].astype(int) * 25
    ).clip(lower=0, upper=100)
    scoped["predicted_failure_band"] = pd.cut(
        scoped["predicted_failure_score"],
        bins=[-1, 35, 65, 100],
        labels=["Stable", "Watch", "Critical"],
    ).astype(str)
    return scoped.sort_values(["in_maintenance", "predicted_failure_score"], ascending=[False, False]).reset_index(drop=True)


def build_problem_truck_rollup(snapshot: pd.DataFrame, anomalies: pd.DataFrame) -> pd.DataFrame:
    if snapshot.empty:
        return pd.DataFrame()

    anomaly_rollup = (
        anomalies.groupby(["truck_id", "category"], as_index=False)
        .agg(anomaly_count=("category", "count"), anomaly_score=("score", "sum"))
        if not anomalies.empty
        else pd.DataFrame(columns=["truck_id", "category", "anomaly_count", "anomaly_score"])
    )
    wide = (
        anomaly_rollup.pivot_table(
            index="truck_id",
            values="anomaly_count",
            columns="category",
            aggfunc="sum",
            fill_value=0,
        )
        .reset_index()
        if not anomaly_rollup.empty
        else pd.DataFrame({"truck_id": snapshot["truck_id"]})
    )

    summary = snapshot[["truck_id", "truck_label", "driver_id", "severity", "fuel_level", "speed", "engine_temp"]].copy()
    merged = summary.merge(wide, on="truck_id", how="left").fillna(0)
    if not anomaly_rollup.empty:
        total_scores = anomaly_rollup.groupby("truck_id", as_index=False)["anomaly_score"].sum()
        merged = merged.merge(total_scores, on="truck_id", how="left").fillna({"anomaly_score": 0})
    else:
        merged["anomaly_score"] = 0
    return merged.sort_values(["anomaly_score", "engine_temp", "speed"], ascending=[False, False, False]).reset_index(drop=True)


def build_maintenance_timeline(metric_history: pd.DataFrame, maintenance_view: pd.DataFrame) -> pd.DataFrame:
    if metric_history.empty:
        return pd.DataFrame()
    timeline = metric_history[["buffer_captured_at", "maintenance_trucks", "average_engine_temp"]].copy()
    timeline.rename(columns={"buffer_captured_at": "timestamp"}, inplace=True)
    if not maintenance_view.empty:
        truck_ids = maintenance_view["truck_id"].astype(int).tolist()
        timeline["truck_id"] = [truck_ids[0] if truck_ids else -1] * len(timeline)
    return timeline
