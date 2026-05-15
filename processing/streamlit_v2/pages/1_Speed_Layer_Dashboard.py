"""Real-time fleet operations dashboard backed by truck_latest."""

from __future__ import annotations

import streamlit as st
from streamlit_autorefresh import st_autorefresh

from components.charts import (
    create_alert_bar,
    create_city_activity_bar,
    create_indicator_gauge,
    create_location_map,
    create_speed_temperature_scatter,
    create_status_donut,
)
from components.filters import render_realtime_filters
from components.kpi_cards import KpiCard, render_kpi_cards
from components.layout import configure_page, render_footer, render_page_header, render_section_heading, render_sidebar_shell
from components.status import render_empty_state, render_exception, render_status_banner
from components.tables import render_dataframe_panel
from services.export_service import build_csv_export
from services.realtime_service import (
    apply_realtime_filters,
    build_realtime_efficiency_snapshot,
    build_realtime_operational_table,
    build_realtime_summary,
    load_realtime_dataset,
    summarize_alert_distribution,
    summarize_city_activity,
    summarize_status_distribution,
)
from utils.formatters import (
    format_km,
    format_number,
    format_percent,
    format_relative_minutes,
    format_temperature,
)
from utils.state import init_app_state
from utils.theme import apply_theme


init_app_state()
configure_page("Speed Layer Dashboard")
sidebar_state = render_sidebar_shell(
    page_name="Speed Layer Dashboard",
    data_source="truck_latest",
    allow_refresh=True,
)
theme_mode = str(sidebar_state["theme_mode"])
apply_theme(theme_mode)

if sidebar_state["auto_refresh"]:
    st_autorefresh(interval=int(sidebar_state["refresh_interval"]) * 1000, key="speed_layer_autorefresh")

render_page_header(
    title="Speed Layer Dashboard",
    subtitle="Operational monitoring for live fleet telemetry, alert posture, fuel status, temperature risk, and geographic spread.",
    tags=["Latest Snapshot", "Auto Refresh", "Operational Control"],
)

try:
    with st.spinner("Loading live fleet telemetry..."):
        realtime_df = load_realtime_dataset(force_refresh=False)

    filters = render_realtime_filters(realtime_df)
    scoped_df = apply_realtime_filters(
        realtime_df,
        truck_ids=filters.truck_ids,
        cities=filters.cities,
        alert_types=filters.alert_types,
        max_age_minutes=filters.max_age_minutes,
    )

    if scoped_df.empty:
        render_empty_state(
            "No live records matched the current filters",
            "Widen the freshness window or clear some filters to restore the operational view.",
        )
        render_footer()
        raise SystemExit

    summary = build_realtime_summary(scoped_df)
    health = build_realtime_efficiency_snapshot(scoped_df)

    render_status_banner(
        f"Freshest live event: {format_relative_minutes(summary['heartbeat_minutes'])} · "
        f"Auto refresh: {'enabled' if sidebar_state['auto_refresh'] else 'disabled'}",
        tone="success" if summary["heartbeat_minutes"] <= 1 else "warning",
    )

    render_kpi_cards(
        [
            KpiCard("Tracked Trucks", format_number(summary["total_trucks"]), caption="Filtered operational scope", tone="primary"),
            KpiCard("Moving Trucks", format_number(summary["moving_trucks"]), caption="Currently in motion", tone="primary"),
            KpiCard("Active Alerts", format_number(summary["active_alerts"]), caption=format_percent(health["alert_rate_pct"]), tone="warning"),
            KpiCard("Maintenance", format_number(summary["maintenance_trucks"]), caption=format_percent(health["maintenance_share_pct"]), tone="warning"),
            KpiCard("Average Fuel", format_percent(summary["average_fuel_level"]), caption="Fleet latest level", tone="primary"),
            KpiCard("Peak Engine Temp", format_temperature(summary["max_engine_temp"]), caption="Current filtered maximum", tone="danger"),
        ]
    )

    export_bytes, export_name = build_csv_export(scoped_df, "speed_layer_dashboard", "latest")
    st.download_button("Export filtered live data to CSV", data=export_bytes, file_name=export_name, mime="text/csv")

    render_section_heading("Operational Risk View", "Status, alert composition, and critical operating gauges.")
    top_col_1, top_col_2, top_col_3, top_col_4 = st.columns([1.2, 1.2, 1, 1])

    with top_col_1:
        st.plotly_chart(create_status_donut(summarize_status_distribution(scoped_df), theme_mode, "Fleet Status"), use_container_width=True)
    with top_col_2:
        st.plotly_chart(create_alert_bar(summarize_alert_distribution(scoped_df), theme_mode, "Active Alert Mix"), use_container_width=True)
    with top_col_3:
        st.plotly_chart(
            create_indicator_gauge(summary["average_fuel_level"], "Average Fuel", theme_mode, 100, "%", 20),
            use_container_width=True,
        )
    with top_col_4:
        st.plotly_chart(
            create_indicator_gauge(summary["max_engine_temp"], "Peak Temperature", theme_mode, 150, " C", 100),
            use_container_width=True,
        )

    render_section_heading("Fleet Geography and Asset Signals", "Live position context and telemetry-driven anomaly indicators.")
    middle_col_1, middle_col_2 = st.columns([1.6, 1])
    with middle_col_1:
        st.plotly_chart(create_location_map(scoped_df, theme_mode, "Latest Fleet Positions"), use_container_width=True)
    with middle_col_2:
        st.plotly_chart(
            create_speed_temperature_scatter(scoped_df, theme_mode, "Speed vs Temperature"),
            use_container_width=True,
        )

    bottom_col_1, bottom_col_2 = st.columns([1, 1.4])
    with bottom_col_1:
        st.plotly_chart(create_city_activity_bar(summarize_city_activity(scoped_df), theme_mode, "City Activity"), use_container_width=True)
    with bottom_col_2:
        table_frame = build_realtime_operational_table(scoped_df)
        render_dataframe_panel(
            "Operational Watchlist",
            table_frame,
            caption="Filtered latest truck state ordered by risk score.",
            height=360,
        )

except SystemExit:
    pass
except Exception as error:
    render_exception(error)

render_footer()
