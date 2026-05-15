"""Detailed live fleet exploration view."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from components.alerts import render_alert_feed
from components.charts import (
    alert_timeline_chart,
    engine_health_gauge,
    engine_temperature_timeline_chart,
    refueling_donut_chart,
    speed_timeline_chart,
    top_fastest_trucks_chart,
)
from components.grids import render_fleet_grid
from components.layout import render_empty_state, render_panel_header
from components.maps import render_fleet_map, render_map_insights


def render_fleet_explorer(
    snapshot: pd.DataFrame,
    metric_history: pd.DataFrame,
    alerts: pd.DataFrame,
    table_dataset: pd.DataFrame,
    anomalies: pd.DataFrame,
    truck_timeline: pd.DataFrame,
    theme_mode: str,
) -> None:
    """Render the live fleet explorer with deep table access."""
    if snapshot.empty:
        render_empty_state(
            "No fleet scope available for exploration.",
            "The current filters removed all trucks from the live snapshot.",
        )
        return

    top_col, side_col = st.columns([1.55, 1.0], gap="large")
    with top_col:
        render_panel_header("Fleet Explorer Map", "Operational drilldown by truck, route, and real-time state.")
        render_fleet_map(snapshot, theme_mode)
        render_map_insights(snapshot)
    with side_col:
        render_panel_header("Top Fastest Trucks", "Highest live speed readings in the selected fleet scope.")
        st.plotly_chart(top_fastest_trucks_chart(snapshot, theme_mode), use_container_width=True)
        render_panel_header("Refueling Overview", "Live fuel status across the currently visible fleet.")
        st.plotly_chart(refueling_donut_chart(snapshot, theme_mode), use_container_width=True)

    trend_col, engine_col = st.columns(2, gap="large")
    with trend_col:
        render_panel_header("Speed Timeline", "Refresh-by-refresh speed movement for selected trucks.")
        st.plotly_chart(speed_timeline_chart(truck_timeline, theme_mode), use_container_width=True)
    with engine_col:
        render_panel_header("Engine Health", "High-level engine health score based on current thermal pressure.")
        st.plotly_chart(engine_health_gauge(snapshot, theme_mode), use_container_width=True)

    alert_col, thermal_col = st.columns(2, gap="large")
    with alert_col:
        render_panel_header("Alert Timeline", "Combined alert and anomaly load over the live buffer horizon.")
        st.plotly_chart(alert_timeline_chart(alerts, anomalies, theme_mode), use_container_width=True)
    with thermal_col:
        render_panel_header("Engine Temperature Trend", "Thermal evolution over the live refresh buffer.")
        st.plotly_chart(engine_temperature_timeline_chart(truck_timeline, theme_mode), use_container_width=True)

    render_panel_header("Live Fleet Table", "AG Grid explorer with filters, search, selection, and export.")
    selected_rows = render_fleet_grid(table_dataset, theme_mode, key="fleet_explorer_grid")

    if selected_rows:
        selected_frame = pd.DataFrame(selected_rows)
        selected_ids = (
            pd.to_numeric(selected_frame.get("truck_id"), errors="coerce").dropna().astype(int).tolist()
            if "truck_id" in selected_frame.columns
            else []
        )
        selected_snapshot = snapshot[snapshot["truck_id"].isin(selected_ids)] if selected_ids else snapshot.iloc[0:0]
        selected_timeline = truck_timeline[truck_timeline["truck_id"].isin(selected_ids)] if selected_ids else truck_timeline.iloc[0:0]
        if not selected_snapshot.empty:
            render_panel_header(
                "Selected Truck Drilldown",
                f"Focused view for {len(selected_ids)} selected truck(s) from the AG Grid.",
            )
            detail_col, alert_feed_col = st.columns([1.25, 1.0], gap="large")
            with detail_col:
                st.plotly_chart(speed_timeline_chart(selected_timeline, theme_mode), use_container_width=True)
            with alert_feed_col:
                selected_alerts = alerts[alerts["truck_id"].isin(selected_ids)] if not alerts.empty else alerts
                render_alert_feed(selected_alerts)
