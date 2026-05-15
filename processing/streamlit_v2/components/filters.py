"""Sidebar filter controls for realtime and batch dashboards."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from config.settings import get_settings


settings = get_settings()


@dataclass(frozen=True)
class RealtimeFilterSelection:
    truck_ids: list[int]
    cities: list[str]
    alert_types: list[str]
    max_age_minutes: int


@dataclass(frozen=True)
class BatchFilterSelection:
    start_date: date
    end_date: date
    truck_ids: list[int]
    min_risk_score: float
    compare_to_previous: bool


def render_realtime_filters(frame: pd.DataFrame) -> RealtimeFilterSelection:
    with st.sidebar:
        st.markdown("### Speed Layer Filters")

        truck_options = sorted(frame["truck_id"].dropna().astype(int).unique().tolist()) if not frame.empty else []
        city_options = (
            sorted(set(frame["start_city"].dropna().tolist()) | set(frame["end_city"].dropna().tolist()))
            if not frame.empty
            else []
        )
        alert_options = (
            sorted([value for value in frame["alert_type"].dropna().unique().tolist() if value != "NORMAL"])
            if not frame.empty
            else []
        )

        selected_trucks = st.multiselect(
            "Truck",
            options=truck_options,
            format_func=lambda value: f"Truck {value:02d}",
        )
        selected_cities = st.multiselect("City", options=city_options)
        selected_alerts = st.multiselect("Alert Type", options=alert_options)
        max_age_minutes = int(
            st.slider(
                "Freshness window (minutes)",
                min_value=5,
                max_value=240,
                value=int(st.session_state.get("realtime_lookback_minutes", settings.realtime_default_lookback_minutes)),
                step=5,
                key="realtime_lookback_minutes",
            )
        )

    return RealtimeFilterSelection(
        truck_ids=selected_trucks,
        cities=selected_cities,
        alert_types=selected_alerts,
        max_age_minutes=max_age_minutes,
    )


def render_batch_filters(default_start: date, default_end: date, truck_options: list[int]) -> BatchFilterSelection:
    with st.sidebar:
        st.markdown("### Batch Analytics Filters")
        start_date = st.date_input("Start date", value=default_start, key="batch_start_date")
        end_date = st.date_input("End date", value=default_end, key="batch_end_date")
        selected_trucks = st.multiselect(
            "Truck",
            options=truck_options,
            format_func=lambda value: f"Truck {value:02d}",
        )
        min_risk_score = float(st.slider("Minimum risk score", min_value=0, max_value=100, value=0))
        compare_to_previous = st.toggle("Compare with previous period", value=True)

        if start_date > end_date:
            st.warning("Start date is after end date. The page will swap them automatically.")

        max_span = settings.batch_max_range_days - 1
        if (max(start_date, end_date) - min(start_date, end_date)) > timedelta(days=max_span):
            st.warning(f"Long time ranges may increase query time. Recommended maximum: {settings.batch_max_range_days} days.")

    if start_date > end_date:
        start_date, end_date = end_date, start_date

    return BatchFilterSelection(
        start_date=start_date,
        end_date=end_date,
        truck_ids=selected_trucks,
        min_risk_score=min_risk_score,
        compare_to_previous=compare_to_previous,
    )
