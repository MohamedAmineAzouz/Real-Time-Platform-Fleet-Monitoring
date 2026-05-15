"""Entry page for the enterprise fleet analytics application."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from components.kpi_cards import KpiCard, render_kpi_cards
from components.layout import configure_page, render_footer, render_page_header, render_section_heading, render_sidebar_shell
from components.status import render_exception, render_status_banner
from config.settings import get_settings
from database.repositories import find_latest_batch_date
from services.batch_service import build_period_summary, load_batch_dataset
from services.realtime_service import build_realtime_summary, load_realtime_dataset
from utils.formatters import format_km, format_liters, format_number
from utils.state import init_app_state
from utils.theme import apply_theme


settings = get_settings()

init_app_state()
configure_page("Platform Overview")
sidebar_state = render_sidebar_shell(
    page_name="Platform Overview",
    data_source="truck_latest + batch_daily_truck_stats",
    allow_refresh=False,
)
apply_theme(str(sidebar_state["theme_mode"]))

render_page_header(
    title="Fleet Command Center",
    subtitle="A production-style enterprise analytics workspace for real-time operations and historical fleet performance.",
    tags=["Speed Layer", "Batch Analytics", "Cassandra", "Plotly", "Streamlit"],
)

try:
    with st.spinner("Loading operational snapshot..."):
        realtime_df = load_realtime_dataset()
        latest_batch_date = find_latest_batch_date()
        batch_df = load_batch_dataset(latest_batch_date, latest_batch_date) if latest_batch_date else pd.DataFrame()

    realtime_summary = build_realtime_summary(realtime_df)
    batch_summary = build_period_summary(batch_df)

    render_status_banner(
        "Use the sidebar navigation to move between the dedicated Speed Layer and Batch Analytics dashboards.",
        tone="success",
    )

    render_kpi_cards(
        [
            KpiCard("Fleet Coverage", format_number(realtime_summary["total_trucks"]), caption="Tracked trucks in latest snapshot", tone="primary"),
            KpiCard("Active Alerts", format_number(realtime_summary["active_alerts"]), caption="Current alerting assets", tone="warning"),
            KpiCard("Batch Distance", format_km(batch_summary["total_distance_km"]), caption=f"Latest historical date: {latest_batch_date or 'No data'}", tone="primary"),
            KpiCard("Batch Fuel", format_liters(batch_summary["total_fuel_consumed_l"]), caption="Historical fleet fuel total", tone="warning"),
        ]
    )

    render_section_heading("Workspace Design", "This application separates streaming operations from historical analytics to support both control-room and analyst workflows.")
    overview_col_1, overview_col_2 = st.columns(2)

    with overview_col_1:
        st.markdown(
            """
            <div class="content-card">
                <div class="content-card-title">Speed Layer Dashboard</div>
                <div class="content-card-copy">
                    Monitors current truck state from <code>truck_latest</code> with operational status, alert posture, live fuel signals,
                    engine temperature, routing visibility, and maintenance indicators.
                </div>
                <ul class="content-list">
                    <li>Live truck coverage and freshness monitoring</li>
                    <li>Alert prioritization and anomaly hotspots</li>
                    <li>Geo-analytics with fleet position context</li>
                    <li>Auto-refresh and filtered exports</li>
                </ul>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with overview_col_2:
        st.markdown(
            """
            <div class="content-card">
                <div class="content-card-title">Batch Analytics Dashboard</div>
                <div class="content-card-copy">
                    Analyzes historical fleet efficiency from <code>batch_daily_truck_stats</code> across distance, fuel usage,
                    alert intensity, utilization, and maintenance risk proxies.
                </div>
                <ul class="content-list">
                    <li>Multi-day trend analysis and period comparisons</li>
                    <li>Top-risk truck ranking and efficiency quadrants</li>
                    <li>Historical heatmaps and alert composition views</li>
                    <li>CSV extraction for downstream reporting</li>
                </ul>
            </div>
            """,
            unsafe_allow_html=True,
        )

    render_section_heading("Data Contract", "The current version is intentionally aligned to the fields already present in Cassandra.")
    schema_col_1, schema_col_2, schema_col_3 = st.columns(3)
    schema_col_1.metric("Streaming Source", "truck_latest")
    schema_col_2.metric("Historical Source", "batch_daily_truck_stats")
    schema_col_3.metric("Theme Mode", str(sidebar_state["theme_mode"]).title())

except Exception as error:
    render_exception(error)

render_footer()
