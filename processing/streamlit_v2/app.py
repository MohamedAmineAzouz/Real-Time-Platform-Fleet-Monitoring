"""Enterprise real-time fleet command center powered by Streamlit."""

from __future__ import annotations

from datetime import datetime

import streamlit as st
from streamlit_autorefresh import st_autorefresh

from components.layout import (
    configure_streamlit_page,
    render_sidebar,
    render_top_header,
    render_view_description,
)
from config.settings import get_settings
from pages.command_center import render_command_center
from pages.fleet_explorer import render_fleet_explorer
from pages.reliability_center import render_reliability_center
from services.anomaly_service import (
    build_live_alert_feed,
    build_maintenance_timeline,
    build_maintenance_view,
    build_problem_truck_rollup,
    detect_live_anomalies,
)
from services.live_buffer_service import build_metric_history, filter_buffer_by_trucks, update_live_buffer
from services.speed_layer_service import (
    apply_dashboard_filters,
    apply_view_filters,
    build_kpi_models,
    build_operational_summary,
    build_selected_truck_timeline,
    build_sidebar_filter_options,
    build_system_health_payload,
    build_table_dataset,
    load_speed_layer_snapshot,
)
from utils.logging_utils import get_logger
from utils.session_state import initialize_session_state
from utils.theme import apply_theme


logger = get_logger(__name__)
settings = get_settings()


def main() -> None:
    initialize_session_state()
    configure_streamlit_page()

    if st.session_state.auto_refresh_enabled:
        st_autorefresh(
            interval=settings.refresh_interval_seconds * 1000,
            key="fleet_live_autorefresh",
        )

    try:
        with st.spinner("Connecting to the speed layer and synchronizing live fleet state..."):
            raw_snapshot = load_speed_layer_snapshot(force_refresh=bool(st.session_state.force_refresh))
            st.session_state.force_refresh = False
            live_buffer = update_live_buffer(raw_snapshot)
            metric_history = build_metric_history(live_buffer)
            enriched_snapshot = apply_view_filters(raw_snapshot, live_buffer)
            anomalies = detect_live_anomalies(live_buffer, enriched_snapshot)
            maintenance_view = build_maintenance_view(enriched_snapshot, anomalies)
            problem_trucks = build_problem_truck_rollup(enriched_snapshot, anomalies)
            maintenance_timeline = build_maintenance_timeline(metric_history, maintenance_view)
    except Exception as exc:
        logger.exception("Failed to initialize command center")
        st.set_page_config(page_title=settings.app_title, layout="wide")
        st.error("The fleet command center could not initialize.")
        st.exception(exc)
        return

    filter_options = build_sidebar_filter_options(enriched_snapshot)
    overall_summary = build_operational_summary(enriched_snapshot, metric_history, anomalies, maintenance_view)
    overall_system_health = build_system_health_payload(overall_summary, metric_history)

    sidebar_payload = render_sidebar(
        filter_options=filter_options,
        system_health=overall_system_health,
        latest_snapshot=enriched_snapshot,
        metric_history=metric_history,
    )
    apply_theme(sidebar_payload["theme_mode"])

    filtered_snapshot = apply_dashboard_filters(enriched_snapshot, sidebar_payload["filters"])
    filtered_buffer = (
        filter_buffer_by_trucks(live_buffer, filtered_snapshot["truck_id"].tolist())
        if not filtered_snapshot.empty
        else live_buffer.iloc[0:0].copy()
    )
    filtered_metric_history = build_metric_history(filtered_buffer)
    filtered_anomalies = anomalies[anomalies["truck_id"].isin(filtered_snapshot["truck_id"])] if not anomalies.empty else anomalies
    filtered_maintenance = maintenance_view[maintenance_view["truck_id"].isin(filtered_snapshot["truck_id"])] if not maintenance_view.empty else maintenance_view
    filtered_problem_trucks = problem_trucks[problem_trucks["truck_id"].isin(filtered_snapshot["truck_id"])] if not problem_trucks.empty else problem_trucks
    filtered_maintenance_timeline = (
        maintenance_timeline[maintenance_timeline["truck_id"].isin(filtered_snapshot["truck_id"])]
        if not maintenance_timeline.empty and "truck_id" in maintenance_timeline.columns
        else maintenance_timeline
    )
    filtered_summary = build_operational_summary(
        filtered_snapshot,
        filtered_metric_history,
        filtered_anomalies,
        filtered_maintenance,
    )
    filtered_system_health = build_system_health_payload(filtered_summary, filtered_metric_history)
    kpi_models = build_kpi_models(filtered_summary, filtered_metric_history)
    alert_feed = build_live_alert_feed(filtered_snapshot, filtered_anomalies)
    table_dataset = build_table_dataset(filtered_snapshot)
    truck_timeline = build_selected_truck_timeline(filtered_buffer, sidebar_payload["filters"].truck_ids)

    render_top_header(
        title="Real-Time Fleet Command Center",
        summary=filtered_summary,
        system_health=filtered_system_health,
        last_refresh=datetime.utcnow(),
    )
    render_view_description(sidebar_payload["selected_view"])

    selected_view = sidebar_payload["selected_view"]
    if selected_view == "Command Center":
        render_command_center(
            snapshot=filtered_snapshot,
            metric_history=filtered_metric_history,
            kpis=kpi_models,
            alerts=alert_feed,
            anomalies=filtered_anomalies,
            maintenance_view=filtered_maintenance,
            problem_trucks=filtered_problem_trucks,
            truck_timeline=truck_timeline,
            theme_mode=sidebar_payload["theme_mode"],
        )
    elif selected_view == "Fleet Explorer":
        render_fleet_explorer(
            snapshot=filtered_snapshot,
            metric_history=filtered_metric_history,
            alerts=alert_feed,
            table_dataset=table_dataset,
            anomalies=filtered_anomalies,
            truck_timeline=truck_timeline,
            theme_mode=sidebar_payload["theme_mode"],
        )
    else:
        render_reliability_center(
            snapshot=filtered_snapshot,
            anomalies=filtered_anomalies,
            maintenance_view=filtered_maintenance,
            maintenance_timeline=filtered_maintenance_timeline,
            problem_trucks=filtered_problem_trucks,
            truck_timeline=truck_timeline,
            theme_mode=sidebar_payload["theme_mode"],
        )


if __name__ == "__main__":
    main()
