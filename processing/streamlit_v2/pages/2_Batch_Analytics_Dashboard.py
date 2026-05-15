"""Historical fleet analytics dashboard backed by batch_daily_truck_stats."""

from __future__ import annotations

from datetime import timedelta

import pandas as pd
import streamlit as st

from components.charts import (
    create_alert_bar,
    create_efficiency_scatter,
    create_maintenance_driver_chart,
    create_risk_heatmap,
    create_top_risk_bar,
    create_trend_combo,
)
from components.filters import render_batch_filters
from components.kpi_cards import KpiCard, render_kpi_cards
from components.layout import configure_page, render_footer, render_page_header, render_section_heading, render_sidebar_shell
from components.status import render_empty_state, render_exception, render_status_banner
from components.tables import render_dataframe_panel
from services.batch_service import (
    build_alert_mix,
    build_comparison_summary,
    build_daily_trends,
    build_period_summary,
    build_risk_matrix,
    build_truck_rollup,
    load_batch_dataset,
    resolve_default_batch_window,
)
from services.export_service import build_csv_export
from utils.formatters import format_km, format_liters, format_number
from utils.state import init_app_state
from utils.theme import apply_theme


init_app_state()
configure_page("Batch Analytics Dashboard")
sidebar_state = render_sidebar_shell(
    page_name="Batch Analytics Dashboard",
    data_source="batch_daily_truck_stats",
    allow_refresh=False,
)
theme_mode = str(sidebar_state["theme_mode"])
apply_theme(theme_mode)

default_start, default_end = resolve_default_batch_window(default_days=7)
seed_start = st.session_state.get("batch_start_date", default_start)
seed_end = st.session_state.get("batch_end_date", default_end)

try:
    seed_batch_df = load_batch_dataset(min(seed_start, seed_end), max(seed_start, seed_end))
except Exception:
    seed_batch_df = pd.DataFrame()

render_page_header(
    title="Batch Analytics Dashboard",
    subtitle="Historical fleet analysis for daily trends, fuel efficiency, alert intensity, utilization, and maintenance risk proxies.",
    tags=["Historical Trends", "Daily Aggregates", "Fleet Efficiency"],
)

try:
    truck_options = (
        sorted(seed_batch_df["truck_id"].dropna().astype(int).unique().tolist())
        if not seed_batch_df.empty
        else list(range(1, 101))
    )
    filters = render_batch_filters(default_start=default_start, default_end=default_end, truck_options=truck_options)
    with st.spinner("Loading batch analytics dataset..."):
        batch_df = load_batch_dataset(filters.start_date, filters.end_date)

    if filters.truck_ids:
        batch_df = batch_df[batch_df["truck_id"].isin(filters.truck_ids)]

    if filters.min_risk_score > 0:
        batch_df = batch_df[batch_df["risk_score"] >= filters.min_risk_score]

    if batch_df.empty:
        render_empty_state(
            "No batch analytics rows matched the current selection",
            "Expand the date range or remove restrictive truck and risk filters.",
        )
        render_footer()
        raise SystemExit

    previous_df = pd.DataFrame()
    if filters.compare_to_previous:
        current_length = (filters.end_date - filters.start_date).days + 1
        previous_end = filters.start_date - timedelta(days=1)
        previous_start = previous_end - timedelta(days=current_length - 1)
        previous_df = load_batch_dataset(previous_start, previous_end)
        if filters.truck_ids:
            previous_df = previous_df[previous_df["truck_id"].isin(filters.truck_ids)]

    summary = build_period_summary(batch_df)
    comparison = build_comparison_summary(batch_df, previous_df) if filters.compare_to_previous else {}
    trends_df = build_daily_trends(batch_df)
    rollup_df = build_truck_rollup(batch_df)
    alert_mix_df = build_alert_mix(batch_df)
    risk_matrix = build_risk_matrix(batch_df)

    render_status_banner(
        f"Historical scope: {filters.start_date.isoformat()} to {filters.end_date.isoformat()} · "
        f"Trucks covered: {summary['active_trucks']}",
        tone="info",
    )

    def delta_text(metric_key: str, positive_is_good: bool = True) -> str | None:
        if metric_key not in comparison:
            return None
        delta = comparison[metric_key]["delta_pct"]
        sign = "+" if delta >= 0 else ""
        orientation = "better" if (delta >= 0 and positive_is_good) or (delta < 0 and not positive_is_good) else "watch"
        return f"{sign}{delta:.1f}% vs prior · {orientation}"

    render_kpi_cards(
        [
            KpiCard("Fleet Distance", format_km(summary["total_distance_km"]), delta=delta_text("total_distance_km"), tone="primary"),
            KpiCard("Fuel Consumed", format_liters(summary["total_fuel_consumed_l"]), delta=delta_text("total_fuel_consumed_l", positive_is_good=False), tone="warning"),
            KpiCard("Fuel / 100km", f"{summary['weighted_fuel_per_100km']:.2f}", delta=delta_text("weighted_fuel_per_100km", positive_is_good=False), caption="Weighted fleet efficiency", tone="warning"),
            KpiCard("Total Alerts", format_number(summary["total_alerts"]), delta=delta_text("total_alerts", positive_is_good=False), tone="danger"),
            KpiCard("Average Speed", f"{summary['average_speed_kmh']:.1f} km/h", delta=delta_text("average_speed_kmh"), tone="primary"),
            KpiCard("Utilization", f"{summary['average_utilization_pct']:.1f}%", delta=delta_text("average_utilization_pct"), tone="primary"),
        ]
    )

    export_bytes, export_name = build_csv_export(batch_df, "batch_analytics", f"{filters.start_date}_{filters.end_date}")
    st.download_button("Export filtered batch data to CSV", data=export_bytes, file_name=export_name, mime="text/csv")

    render_section_heading("Trend Analytics", "Distance, fuel efficiency, and alert volume over the selected historical window.")
    trend_col, alert_col = st.columns([1.7, 1])
    with trend_col:
        st.plotly_chart(create_trend_combo(trends_df, theme_mode, "Daily Fleet Trend"), use_container_width=True)
    with alert_col:
        st.plotly_chart(create_alert_bar(alert_mix_df, theme_mode, "Alert Composition"), use_container_width=True)

    render_section_heading("Risk and Efficiency Analysis", "Compare fleet efficiency, identify risky trucks, and inspect daily risk concentration.")
    analytics_col_1, analytics_col_2 = st.columns([1.2, 1])
    with analytics_col_1:
        st.plotly_chart(create_efficiency_scatter(rollup_df, theme_mode, "Efficiency Quadrant"), use_container_width=True)
    with analytics_col_2:
        st.plotly_chart(create_top_risk_bar(rollup_df, theme_mode, "Top Risky Trucks"), use_container_width=True)

    diagnostics_col_1, diagnostics_col_2 = st.columns([1.2, 1])
    with diagnostics_col_1:
        st.plotly_chart(create_risk_heatmap(risk_matrix, theme_mode, "Truck-Day Risk Heatmap"), use_container_width=True)
    with diagnostics_col_2:
        st.plotly_chart(create_maintenance_driver_chart(rollup_df, theme_mode, "Maintenance Risk Drivers"), use_container_width=True)

    render_section_heading("Operational Tables", "Analyst-ready detail views for truck ranking and daily trend validation.")
    tables_col_1, tables_col_2 = st.columns(2)

    with tables_col_1:
        render_dataframe_panel(
            "Risk Ranking",
            rollup_df[
                [
                    "truck_label",
                    "mean_risk_score",
                    "fuel_per_100km",
                    "total_distance_km",
                    "total_alerts",
                    "maintenance_proxy_score",
                ]
            ].rename(
                columns={
                    "truck_label": "Truck",
                    "mean_risk_score": "Risk Score",
                    "fuel_per_100km": "Fuel / 100km",
                    "total_distance_km": "Distance (km)",
                    "total_alerts": "Alerts",
                    "maintenance_proxy_score": "Maintenance Proxy",
                }
            ),
            caption="Aggregated truck-level ranking over the selected period.",
            height=360,
        )

    with tables_col_2:
        render_dataframe_panel(
            "Daily Trend Detail",
            trends_df.rename(
                columns={
                    "stat_date": "Date",
                    "total_distance_km": "Distance (km)",
                    "total_fuel_consumed_l": "Fuel (L)",
                    "fuel_per_100km": "Fuel / 100km",
                    "total_alerts": "Alerts",
                    "average_speed_kmh": "Average Speed",
                    "avg_utilization_pct": "Utilization (%)",
                }
            ),
            caption="Fleet-wide daily aggregates derived from the selected range.",
            height=360,
        )

except SystemExit:
    pass
except Exception as error:
    render_exception(error)

render_footer()
