"""Layout and navigation primitives for the fleet command center."""

from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from typing import Any

import pandas as pd
import streamlit as st
from streamlit_option_menu import option_menu

from config.settings import get_settings
from services.speed_layer_service import DashboardFilters
from utils.formatters import format_number, humanize_latency, humanize_timestamp


settings = get_settings()


VIEW_COPY = {
    "Command Center": (
        "Live operational command center for streaming truck telemetry, active incidents, fleet health, and geospatial monitoring."
    ),
    "Fleet Explorer": (
        "High-detail live fleet explorer with drilldowns, tabular telemetry inspection, and timeline analytics for the latest speed layer state."
    ),
    "Reliability Center": (
        "Anomaly intelligence and maintenance command view for trucks that need attention, interventions, or deeper engineering review."
    ),
}


@lru_cache(maxsize=1)
def _load_logo_markup() -> str:
    if settings.logo_path.exists():
        return settings.logo_path.read_text(encoding="utf-8")
    return "<div class='logo-fallback'>FC</div>"


def configure_streamlit_page() -> None:
    """Set page-wide Streamlit metadata."""
    st.set_page_config(
        page_title=settings.app_title,
        page_icon=settings.page_icon,
        layout="wide",
        initial_sidebar_state="expanded",
        menu_items={
            "About": "Real-time fleet command center for logistics telemetry and operational control.",
        },
    )


def render_sidebar(
    filter_options: dict[str, Any],
    system_health: dict[str, Any],
    latest_snapshot: pd.DataFrame,
    metric_history: pd.DataFrame,
) -> dict[str, Any]:
    """Render navigation, live status, and filtering controls in the sidebar."""
    truck_map = (
        latest_snapshot[["truck_id", "truck_label"]]
        .drop_duplicates()
        .sort_values("truck_id")
        .set_index("truck_label")["truck_id"]
        .to_dict()
        if not latest_snapshot.empty
        else {}
    )
    default_theme_index = 0 if st.session_state.get("theme_mode", settings.default_theme) == "dark" else 1
    stale_trucks = int((latest_snapshot.get("latency_seconds", pd.Series(dtype=float)) > settings.stale_after_seconds).sum())
    critical_trucks = int((latest_snapshot.get("severity", pd.Series(dtype=str)) == "Critical").sum())

    with st.sidebar:
        st.markdown(
            f"""
            <div class="sidebar-brand">
                <div class="sidebar-logo">{_load_logo_markup()}</div>
                <div>
                    <div class="sidebar-eyebrow">Fleet Control Tower</div>
                    <div class="sidebar-title">{settings.app_title}</div>
                    <div class="sidebar-subtitle">{settings.app_subtitle}</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        default_view = st.session_state.get("selected_view", "Command Center")
        view_options = list(VIEW_COPY)
        selected_view = option_menu(
            menu_title=None,
            options=view_options,
            icons=["broadcast-pin", "geo-alt-fill", "shield-exclamation"],
            default_index=view_options.index(default_view) if default_view in view_options else 0,
            styles={
                "container": {
                    "padding": "0 !important",
                    "background-color": "transparent",
                },
                "icon": {"font-size": "18px"},
                "nav-link": {
                    "font-size": "0.96rem",
                    "font-weight": "600",
                    "padding": "0.8rem 0.95rem",
                    "margin": "0.15rem 0",
                    "border-radius": "16px",
                },
                "nav-link-selected": {
                    "background-color": "rgba(56, 189, 248, 0.16)",
                    "color": "#ffffff",
                },
            },
        )
        st.session_state.selected_view = selected_view

        st.markdown(
            f"""
            <div class="sidebar-status-card">
                <div class="sidebar-status-top">
                    <span class="signal-dot {'critical' if critical_trucks else 'healthy'}"></span>
                    <span>{system_health.get('status_label', 'Unknown').upper()}</span>
                </div>
                <div class="sidebar-status-score">{system_health.get('health_score', 0)}</div>
                <div class="sidebar-status-caption">Operational health score</div>
                <div class="sidebar-status-grid">
                    <div><span>{format_number(system_health.get('live_events', 0))}</span><small>streaming rows</small></div>
                    <div><span>{system_health.get('healthy_ratio_pct', 0):.0f}%</span><small>healthy ratio</small></div>
                    <div><span>{critical_trucks}</span><small>critical trucks</small></div>
                    <div><span>{stale_trucks}</span><small>stale trucks</small></div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("<div class='sidebar-group-label'>Control Center</div>", unsafe_allow_html=True)
        theme_mode = st.radio(
            "Theme Mode",
            options=["dark", "light"],
            index=default_theme_index,
            horizontal=True,
            label_visibility="collapsed",
            key="theme_mode",
        )
        st.toggle(
            "Auto refresh live stream",
            value=st.session_state.get("auto_refresh_enabled", True),
            key="auto_refresh_enabled",
        )
        if st.button("Refresh Snapshot", use_container_width=True):
            st.session_state.force_refresh = True

        st.markdown("<div class='sidebar-group-label'>Fleet Filters</div>", unsafe_allow_html=True)
        selected_truck_labels = st.multiselect(
            "Truck Selector",
            options=list(truck_map.keys()),
            placeholder="All live trucks",
        )
        selected_driver_ids = st.multiselect(
            "Driver Selector",
            options=filter_options.get("driver_ids", []),
            placeholder="All drivers",
        )
        selected_alert_types = st.multiselect(
            "Alert Type",
            options=filter_options.get("alert_types", []),
            placeholder="All alert types",
        )
        selected_cities = st.multiselect(
            "City",
            options=filter_options.get("cities", []),
            placeholder="All cities",
        )
        maintenance_status = st.selectbox(
            "Maintenance Status",
            options=["All", "In Maintenance", "Operational Only"],
        )
        theft_only = st.checkbox("Theft Only")
        active_alerts_only = st.checkbox("Active Alerts Only")
        fuel_range = st.slider(
            "Fuel Consumption Range",
            min_value=float(filter_options.get("fuel_range", (0.0, 40.0))[0]),
            max_value=float(filter_options.get("fuel_range", (0.0, 40.0))[1]),
            value=tuple(float(v) for v in filter_options.get("fuel_range", (0.0, 40.0))),
            step=0.5,
        )
        speed_range = st.slider(
            "Speed Range",
            min_value=float(filter_options.get("speed_range", (0.0, 140.0))[0]),
            max_value=float(filter_options.get("speed_range", (0.0, 140.0))[1]),
            value=tuple(float(v) for v in filter_options.get("speed_range", (0.0, 140.0))),
            step=1.0,
        )

        latest_refresh = metric_history["buffer_captured_at"].max() if not metric_history.empty else None
        st.markdown(
            f"""
            <div class="sidebar-metadata">
                <div><strong>Last buffer refresh</strong><span>{humanize_timestamp(latest_refresh)}</span></div>
                <div><strong>Refresh cadence</strong><span>{settings.refresh_interval_seconds}s</span></div>
                <div><strong>Freshness gap</strong><span>{humanize_latency(float(system_health.get('freshness_seconds', 0)))}</span></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    selected_truck_ids = [int(truck_map[label]) for label in selected_truck_labels]
    return {
        "theme_mode": theme_mode,
        "selected_view": selected_view,
        "filters": DashboardFilters(
            truck_ids=selected_truck_ids,
            driver_ids=selected_driver_ids,
            alert_types=selected_alert_types,
            cities=selected_cities,
            maintenance_status=maintenance_status,
            theft_only=theft_only,
            active_alerts_only=active_alerts_only,
            fuel_range=fuel_range,
            speed_range=speed_range,
        ),
    }


def render_top_header(
    title: str,
    summary: dict[str, Any],
    system_health: dict[str, Any],
    last_refresh: datetime,
) -> None:
    """Render the top hero section of the dashboard."""
    status_label = str(system_health.get("status_label", "Unknown"))
    tone_class = {
        "Healthy": "healthy",
        "Degraded": "warning",
        "Critical": "critical",
        "No Data": "neutral",
    }.get(status_label, "neutral")
    last_event = summary.get("last_event_time")
    st.markdown(
        f"""
        <div class="hero-shell">
            <div class="hero-copy">
                <div class="hero-eyebrow">Fleet Streaming Command Center</div>
                <h1>{title}</h1>
                <p>Continuous monitoring of truck telemetry, live alerts, route behavior, fuel efficiency, and maintenance readiness.</p>
                <div class="hero-badges">
                    <span class="live-pill {tone_class}">
                        <span class="signal-dot {tone_class}"></span>
                        LIVE STREAM ACTIVE
                    </span>
                    <span class="hero-badge">Last refresh: {humanize_timestamp(last_refresh)}</span>
                    <span class="hero-badge">Last processed event: {humanize_timestamp(last_event)}</span>
                </div>
            </div>
            <div class="hero-stats">
                <div class="hero-stat-card">
                    <span>System Health</span>
                    <strong>{status_label}</strong>
                    <small>{system_health.get('health_score', 0)}/100 score</small>
                </div>
                <div class="hero-stat-card">
                    <span>Total Streaming Events</span>
                    <strong>{format_number(summary.get('total_streaming_events', 0))}</strong>
                    <small>{format_number(summary.get('active_trucks', 0))} active trucks</small>
                </div>
                <div class="hero-stat-card">
                    <span>Live Event Rate</span>
                    <strong>{format_number(summary.get('live_event_rate', 0))}</strong>
                    <small>rows per refresh cycle</small>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_view_description(view_name: str) -> None:
    """Render a premium contextual view description."""
    st.markdown(
        f"""
        <div class="view-description">
            <div class="view-description-title">{view_name}</div>
            <div class="view-description-body">{VIEW_COPY.get(view_name, '')}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_panel_header(title: str, subtitle: str, badge: str | None = None) -> None:
    """Render a consistent section header."""
    badge_markup = f"<span class='panel-badge'>{badge}</span>" if badge else ""
    st.markdown(
        f"""
        <div class="panel-header">
            <div>
                <div class="panel-title">{title}</div>
                <div class="panel-subtitle">{subtitle}</div>
            </div>
            {badge_markup}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_empty_state(title: str, description: str) -> None:
    """Render a friendly empty state when a view has no data."""
    st.markdown(
        f"""
        <div class="empty-state">
            <div class="empty-state-title">{title}</div>
            <div class="empty-state-description">{description}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
