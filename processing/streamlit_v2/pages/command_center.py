"""Main live command center view."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from components.alerts import render_alert_feed, render_anomaly_center, render_maintenance_center
from components.charts import (
    alert_distribution_chart,
    anomaly_category_chart,
    engine_temperature_chart,
    fuel_consumption_ranking_chart,
    fuel_efficiency_bubble_chart,
    fuel_level_distribution_chart,
    problem_truck_score_chart,
    speed_distribution_chart,
    speed_timeline_chart,
    streaming_volume_chart,
)
from components.kpi_cards import render_kpi_cards
from components.layout import render_empty_state, render_panel_header
from components.maps import render_fleet_map, render_map_insights


def render_command_center(
    snapshot: pd.DataFrame,
    metric_history: pd.DataFrame,
    kpis: list[dict[str, object]],
    alerts: pd.DataFrame,
    anomalies: pd.DataFrame,
    maintenance_view: pd.DataFrame,
    problem_trucks: pd.DataFrame,
    truck_timeline: pd.DataFrame,
    theme_mode: str,
) -> None:
    """Render the core real-time fleet command center."""
    if snapshot.empty:
        render_empty_state(
            "No live fleet records match the current filters.",
            "Broaden the filters or verify that `truck_latest` is receiving fresh streaming telemetry.",
        )
        return

    render_kpi_cards(kpis)

    map_col, alert_col = st.columns([1.7, 1.0], gap="large")
    with map_col:
        render_panel_header(
            "GPS and Fleet Geo Command",
            "Live truck positions, density clustering, alert locations, and maintenance zones.",
            badge=f"{snapshot['truck_id'].nunique()} active trucks",
        )
        render_fleet_map(snapshot, theme_mode)
        render_map_insights(snapshot)
    with alert_col:
        render_panel_header(
            "Real-Time Alert Center",
            "Critical, theft, overspeed, anomaly, and maintenance events sorted by urgency.",
            badge=f"{len(alerts)} live incidents",
        )
        render_alert_feed(alerts)

    speed_col, speed_trend_col = st.columns(2, gap="large")
    with speed_col:
        render_panel_header("Speed Analytics", "Live speed distribution and severity mix.")
        st.plotly_chart(speed_distribution_chart(snapshot, theme_mode), use_container_width=True)
    with speed_trend_col:
        render_panel_header("Speed Trend Over Time", "Refresh-to-refresh speed movement for the selected trucks.")
        st.plotly_chart(speed_timeline_chart(truck_timeline, theme_mode), use_container_width=True)

    fuel_col, fuel_rank_col = st.columns(2, gap="large")
    with fuel_col:
        render_panel_header("Fuel Level Analytics", "Fuel availability distribution across the live fleet.")
        st.plotly_chart(fuel_level_distribution_chart(snapshot, theme_mode), use_container_width=True)
    with fuel_rank_col:
        render_panel_header("Fuel Consumption Ranking", "Highest real-time fuel consumption rates in the current scope.")
        st.plotly_chart(fuel_consumption_ranking_chart(snapshot, theme_mode), use_container_width=True)

    engine_col, alert_chart_col = st.columns(2, gap="large")
    with engine_col:
        render_panel_header("Engine Analytics", "Thermal behavior and overheating pressure against vehicle speed.")
        st.plotly_chart(engine_temperature_chart(snapshot, theme_mode), use_container_width=True)
    with alert_chart_col:
        render_panel_header("Alert Analytics", "Current alert composition across active live incidents.")
        st.plotly_chart(alert_distribution_chart(alerts, theme_mode), use_container_width=True)

    live_col, efficiency_col = st.columns(2, gap="large")
    with live_col:
        render_panel_header("Streaming Telemetry Load", "Refresh volume, alert pressure, and moving fleet cadence.")
        st.plotly_chart(streaming_volume_chart(metric_history, theme_mode), use_container_width=True)
    with efficiency_col:
        render_panel_header("Fuel Efficiency Scoreboard", "Cross-view of speed, consumption, and efficiency score.")
        st.plotly_chart(fuel_efficiency_bubble_chart(snapshot, theme_mode), use_container_width=True)

    anomaly_col, maintenance_col = st.columns(2, gap="large")
    with anomaly_col:
        render_panel_header("AI Anomaly Center", "Suspicious fuel, speed, engine, and GPS behaviors detected in the live window.")
        st.plotly_chart(anomaly_category_chart(anomalies, theme_mode), use_container_width=True)
        st.plotly_chart(problem_truck_score_chart(problem_trucks, theme_mode), use_container_width=True)
        render_anomaly_center(anomalies, problem_trucks)
    with maintenance_col:
        render_panel_header("Maintenance Command", "Maintenance flags, warning signals, and predicted failure watchlist.")
        render_maintenance_center(maintenance_view)
