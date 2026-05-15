"""Alert, anomaly, and maintenance presentation blocks."""

from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from services.export_service import dataframe_to_csv_bytes, make_export_filename
from utils.formatters import humanize_timestamp


def render_alert_feed(alerts: pd.DataFrame) -> None:
    """Render a premium alert feed."""
    if alerts.empty:
        st.markdown(
            """
            <div class="empty-state compact">
                <div class="empty-state-title">No active live alerts</div>
                <div class="empty-state-description">The filtered fleet scope is currently stable.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    st.download_button(
        "Export alert feed",
        data=dataframe_to_csv_bytes(alerts),
        file_name=make_export_filename("fleet_alert_feed"),
        mime="text/csv",
        use_container_width=True,
    )
    for row in alerts.head(10).itertuples(index=False):
        severity = str(row.severity).lower()
        st.markdown(
            f"""
            <div class="alert-feed-card severity-{severity}">
                <div class="alert-feed-top">
                    <div class="alert-feed-title">
                        <span class="signal-dot {severity}"></span>
                        {html.escape(str(row.title))}
                    </div>
                    <span class="severity-badge severity-{severity}">{html.escape(str(row.severity))}</span>
                </div>
                <div class="alert-feed-body">{html.escape(str(row.message))}</div>
                <div class="alert-feed-meta">
                    <span>Truck {int(row.truck_id):02d}</span>
                    <span>{html.escape(str(row.driver_id))}</span>
                    <span>{humanize_timestamp(row.timestamp)}</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_anomaly_center(anomalies: pd.DataFrame, problem_trucks: pd.DataFrame) -> None:
    """Render anomaly intelligence cards and top problematic trucks."""
    if anomalies.empty and problem_trucks.empty:
        st.markdown(
            """
            <div class="empty-state compact">
                <div class="empty-state-title">No anomaly escalation</div>
                <div class="empty-state-description">No suspicious fuel, speed, engine, or GPS behavior was detected in the live window.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    critical_count = int((anomalies["severity"] == "Critical").sum()) if not anomalies.empty else 0
    high_count = int((anomalies["severity"] == "High").sum()) if not anomalies.empty else 0
    fuel_events = int((anomalies["category"].isin(["Fuel Theft", "Suspicious Fuel Drop"])).sum()) if not anomalies.empty else 0
    gps_events = int((anomalies["category"].isin(["GPS Jump", "Suspicious GPS Drift"])).sum()) if not anomalies.empty else 0
    st.markdown(
        f"""
        <div class="signal-grid">
            <div class="signal-card"><span>{critical_count}</span><small>critical anomalies</small></div>
            <div class="signal-card"><span>{high_count}</span><small>high anomalies</small></div>
            <div class="signal-card"><span>{fuel_events}</span><small>fuel anomalies</small></div>
            <div class="signal-card"><span>{gps_events}</span><small>GPS anomalies</small></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not anomalies.empty:
        for row in anomalies.head(6).itertuples(index=False):
            severity = str(row.severity).lower()
            st.markdown(
                f"""
                <div class="event-list-card">
                    <div class="event-list-top">
                        <strong>{html.escape(str(row.category))}</strong>
                        <span class="severity-badge severity-{severity}">{html.escape(str(row.severity))}</span>
                    </div>
                    <div class="event-list-body">{html.escape(str(row.message))}</div>
                    <div class="event-list-meta">
                        <span>Truck {int(row.truck_id):02d}</span>
                        <span>{html.escape(str(row.driver_id))}</span>
                        <span>{humanize_timestamp(row.occurred_at)}</span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    if not problem_trucks.empty:
        st.markdown("<div class='subsection-label'>Most Problematic Trucks</div>", unsafe_allow_html=True)
        for row in problem_trucks.head(5).itertuples(index=False):
            st.markdown(
                f"""
                <div class="ranked-row">
                    <div>
                        <strong>{html.escape(str(row.truck_label))}</strong>
                        <div>Driver {html.escape(str(row.driver_id))}</div>
                    </div>
                    <div class="ranked-row-right">
                        <span>{float(row.anomaly_score):.0f}</span>
                        <small>{html.escape(str(row.severity))}</small>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def render_maintenance_center(maintenance_view: pd.DataFrame) -> None:
    """Render live maintenance and predicted failure information."""
    if maintenance_view.empty:
        st.markdown(
            """
            <div class="empty-state compact">
                <div class="empty-state-title">No maintenance workload</div>
                <div class="empty-state-description">No trucks are currently flagged for maintenance in the selected scope.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    active = int(maintenance_view["in_maintenance"].sum())
    critical = int((maintenance_view["predicted_failure_band"] == "Critical").sum())
    watch = int((maintenance_view["predicted_failure_band"] == "Watch").sum())
    st.markdown(
        f"""
        <div class="signal-grid">
            <div class="signal-card"><span>{active}</span><small>active maintenance</small></div>
            <div class="signal-card"><span>{critical}</span><small>critical failures</small></div>
            <div class="signal-card"><span>{watch}</span><small>watchlist trucks</small></div>
            <div class="signal-card"><span>{maintenance_view['predicted_failure_score'].mean():.0f}</span><small>avg failure score</small></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    for row in maintenance_view.head(6).itertuples(index=False):
        severity = "critical" if str(row.predicted_failure_band) == "Critical" else "high" if str(row.predicted_failure_band) == "Watch" else "normal"
        st.markdown(
            f"""
            <div class="event-list-card">
                <div class="event-list-top">
                    <strong>{html.escape(str(row.truck_label))}</strong>
                    <span class="severity-badge severity-{severity}">{html.escape(str(row.predicted_failure_band))}</span>
                </div>
                <div class="event-list-body">{html.escape(str(row.maintenance_desc or row.maintenance_type or 'Operational observation only'))}</div>
                <div class="event-list-meta">
                    <span>{html.escape(str(row.maintenance_type or 'Observation'))}</span>
                    <span>{float(row.predicted_failure_score):.0f}/100</span>
                    <span>{float(row.engine_temp):.1f} C</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
