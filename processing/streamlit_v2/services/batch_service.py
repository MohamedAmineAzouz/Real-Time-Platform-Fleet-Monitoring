"""Historical analytics service for daily fleet batch statistics."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from database.repositories import fetch_daily_batch_range, find_latest_batch_date
from utils.formatters import safe_divide
from utils.logging_utils import get_logger


logger = get_logger(__name__)


def load_batch_dataset(start_date: date, end_date: date) -> pd.DataFrame:
    raw = fetch_daily_batch_range(start_date, end_date)
    logger.info("Batch dataset rows=%s start=%s end=%s", len(raw), start_date, end_date)
    return _prepare_batch_dataset(raw)


def resolve_default_batch_window(default_days: int) -> tuple[date, date]:
    latest = find_latest_batch_date()
    end_date = latest or date.today()
    start_date = end_date - timedelta(days=max(default_days - 1, 0))
    return start_date, end_date


def _prepare_batch_dataset(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()

    df = frame.copy()
    numeric_columns = [
        "total_distance_km",
        "total_fuel_consumed_l",
        "fuel_per_100km",
        "avg_speed_kmh",
        "max_speed_kmh",
        "hours_driven",
        "hours_stopped",
        "total_alerts",
        "overspeed_count",
        "overheat_count",
        "fuel_theft_count",
        "low_fuel_count",
        "event_count",
    ]

    for column in numeric_columns:
        df[column] = pd.to_numeric(df.get(column), errors="coerce").fillna(0)

    df["truck_id"] = pd.to_numeric(df["truck_id"], errors="coerce").fillna(0).astype(int)
    df["truck_label"] = df["truck_id"].apply(lambda value: f"Truck {value:02d}")
    df["stat_date"] = pd.to_datetime(df["stat_date"], errors="coerce").dt.date
    df["utilization_pct"] = (
        (df["hours_driven"] / (df["hours_driven"] + df["hours_stopped"]).replace(0, pd.NA))
        .fillna(0)
        .mul(100)
    )
    df["alerts_per_100km"] = (
        (df["total_alerts"] / df["total_distance_km"].replace(0, pd.NA))
        .fillna(0)
        .mul(100)
    )
    df["distance_per_event_km"] = (
        df["total_distance_km"] / df["event_count"].replace(0, pd.NA)
    ).fillna(0)
    df["maintenance_proxy_score"] = (
        df["overheat_count"] * 2.4
        + df["low_fuel_count"] * 1.4
        + df["hours_stopped"] * 4
    )
    df["risk_score"] = (
        df["overspeed_count"] * 1.1
        + df["overheat_count"] * 1.4
        + df["fuel_theft_count"] * 1.7
        + df["low_fuel_count"] * 0.9
        + df["alerts_per_100km"] * 0.7
        + df["fuel_per_100km"] * 0.4
        + (100 - df["utilization_pct"]) * 0.08
    )
    return df.sort_values(["stat_date", "risk_score"], ascending=[True, False]).reset_index(drop=True)


def build_period_summary(frame: pd.DataFrame) -> dict[str, float | int]:
    if frame.empty:
        return {
            "active_trucks": 0,
            "total_distance_km": 0.0,
            "total_fuel_consumed_l": 0.0,
            "weighted_fuel_per_100km": 0.0,
            "average_speed_kmh": 0.0,
            "total_alerts": 0,
            "average_utilization_pct": 0.0,
            "average_risk_score": 0.0,
        }

    total_distance = float(frame["total_distance_km"].sum())
    total_fuel = float(frame["total_fuel_consumed_l"].sum())
    total_hours_driven = float(frame["hours_driven"].sum())
    return {
        "active_trucks": int(frame["truck_id"].nunique()),
        "total_distance_km": total_distance,
        "total_fuel_consumed_l": total_fuel,
        "weighted_fuel_per_100km": safe_divide(total_fuel * 100, total_distance, 0.0),
        "average_speed_kmh": safe_divide(total_distance, total_hours_driven, 0.0),
        "total_alerts": int(frame["total_alerts"].sum()),
        "average_utilization_pct": float(frame["utilization_pct"].mean()),
        "average_risk_score": float(frame["risk_score"].mean()),
    }


def build_daily_trends(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()

    grouped = (
        frame.groupby("stat_date", as_index=False)
        .agg(
            total_distance_km=("total_distance_km", "sum"),
            total_fuel_consumed_l=("total_fuel_consumed_l", "sum"),
            total_alerts=("total_alerts", "sum"),
            total_hours_driven=("hours_driven", "sum"),
            avg_utilization_pct=("utilization_pct", "mean"),
        )
        .sort_values("stat_date")
    )
    grouped["fuel_per_100km"] = grouped.apply(
        lambda row: safe_divide(row["total_fuel_consumed_l"] * 100, row["total_distance_km"], 0.0),
        axis=1,
    )
    grouped["average_speed_kmh"] = grouped.apply(
        lambda row: safe_divide(row["total_distance_km"], row["total_hours_driven"], 0.0),
        axis=1,
    )
    return grouped


def build_truck_rollup(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()

    grouped = (
        frame.groupby(["truck_id", "truck_label"], as_index=False)
        .agg(
            total_distance_km=("total_distance_km", "sum"),
            total_fuel_consumed_l=("total_fuel_consumed_l", "sum"),
            total_alerts=("total_alerts", "sum"),
            overspeed_count=("overspeed_count", "sum"),
            overheat_count=("overheat_count", "sum"),
            fuel_theft_count=("fuel_theft_count", "sum"),
            low_fuel_count=("low_fuel_count", "sum"),
            hours_driven=("hours_driven", "sum"),
            hours_stopped=("hours_stopped", "sum"),
            average_speed_kmh=("avg_speed_kmh", "mean"),
            max_speed_kmh=("max_speed_kmh", "max"),
            mean_utilization_pct=("utilization_pct", "mean"),
            maintenance_proxy_score=("maintenance_proxy_score", "sum"),
            mean_risk_score=("risk_score", "mean"),
        )
        .sort_values("mean_risk_score", ascending=False)
    )
    grouped["fuel_per_100km"] = grouped.apply(
        lambda row: safe_divide(row["total_fuel_consumed_l"] * 100, row["total_distance_km"], 0.0),
        axis=1,
    )
    grouped["alerts_per_100km"] = grouped.apply(
        lambda row: safe_divide(row["total_alerts"] * 100, row["total_distance_km"], 0.0),
        axis=1,
    )
    return grouped


def build_alert_mix(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["alert_type", "count"])

    alert_totals = {
        "Overspeed": int(frame["overspeed_count"].sum()),
        "Overheat": int(frame["overheat_count"].sum()),
        "Fuel Theft": int(frame["fuel_theft_count"].sum()),
        "Low Fuel": int(frame["low_fuel_count"].sum()),
    }
    alert_frame = pd.DataFrame(
        [{"alert_type": key, "count": value} for key, value in alert_totals.items()]
    )
    return alert_frame[alert_frame["count"] > 0].sort_values("count", ascending=False)


def build_risk_matrix(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()

    matrix = (
        frame.pivot_table(
            index="truck_label",
            columns="stat_date",
            values="risk_score",
            aggfunc="mean",
            fill_value=0,
        )
        .sort_index()
    )
    return matrix


def build_comparison_summary(current_frame: pd.DataFrame, previous_frame: pd.DataFrame) -> dict[str, dict[str, float]]:
    current_summary = build_period_summary(current_frame)
    previous_summary = build_period_summary(previous_frame)

    comparison: dict[str, dict[str, float]] = {}
    for key, current_value in current_summary.items():
        previous_value = previous_summary.get(key, 0)
        comparison[key] = {
            "current": float(current_value),
            "previous": float(previous_value),
            "delta_pct": safe_divide(float(current_value) - float(previous_value), float(previous_value), 0.0) * 100,
        }
    return comparison
