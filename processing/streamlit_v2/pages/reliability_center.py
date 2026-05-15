"""Reliability and maintenance intelligence view."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from components.alerts import render_anomaly_center, render_maintenance_center
from components.charts import (
    anomaly_category_chart,
    engine_temperature_timeline_chart,
    maintenance_timeline_chart,
    maintenance_type_chart,
    predicted_failure_chart,
    problem_truck_score_chart,
)
from components.layout import render_empty_state, render_panel_header


def render_reliability_center(
    snapshot: pd.DataFrame,
    anomalies: pd.DataFrame,
    maintenance_view: pd.DataFrame,
    maintenance_timeline: pd.DataFrame,
    problem_trucks: pd.DataFrame,
    truck_timeline: pd.DataFrame,
    theme_mode: str,
) -> None:
    """Render anomaly and maintenance-focused operational intelligence."""
    if snapshot.empty and anomalies.empty and maintenance_view.empty:
        render_empty_state(
            "No reliability data is available for the selected scope.",
            "The current filter set does not expose anomaly or maintenance signals.",
        )
        return

    score_col, band_col = st.columns(2, gap="large")
    with score_col:
        render_panel_header("Problematic Trucks", "Highest anomaly score concentration in the current fleet scope.")
        st.plotly_chart(problem_truck_score_chart(problem_trucks, theme_mode), use_container_width=True)
    with band_col:
        render_panel_header("Failure Prediction Bands", "Operational split of stable, watch, and critical trucks.")
        st.plotly_chart(predicted_failure_chart(maintenance_view, theme_mode), use_container_width=True)

    anomaly_col, maintenance_col = st.columns(2, gap="large")
    with anomaly_col:
        render_panel_header("Anomaly Category Model", "Distribution of anomaly categories detected in the live buffer.")
        st.plotly_chart(anomaly_category_chart(anomalies, theme_mode), use_container_width=True)
    with maintenance_col:
        render_panel_header("Maintenance Type Mix", "Maintenance workload composition across the fleet.")
        st.plotly_chart(maintenance_type_chart(maintenance_view, theme_mode), use_container_width=True)

    timeline_col, thermal_col = st.columns(2, gap="large")
    with timeline_col:
        render_panel_header("Maintenance Timeline", "Maintenance pressure and engine heat over the buffer horizon.")
        st.plotly_chart(maintenance_timeline_chart(maintenance_timeline, theme_mode), use_container_width=True)
    with thermal_col:
        render_panel_header("Thermal Reliability Trend", "Engine temperature change for the most stressed trucks.")
        st.plotly_chart(engine_temperature_timeline_chart(truck_timeline, theme_mode), use_container_width=True)

    detail_col, queue_col = st.columns(2, gap="large")
    with detail_col:
        render_panel_header("Anomaly Queue", "Human-review queue for suspicious live behaviors.")
        render_anomaly_center(anomalies, problem_trucks)
    with queue_col:
        render_panel_header("Maintenance Queue", "Live maintenance interventions and predicted failure review.")
        render_maintenance_center(maintenance_view)
