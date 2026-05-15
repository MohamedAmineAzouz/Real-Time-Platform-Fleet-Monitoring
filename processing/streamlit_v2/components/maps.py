"""Geospatial rendering for the fleet command center."""

from __future__ import annotations

import pandas as pd
import pydeck as pdk
import streamlit as st

from config.settings import get_settings


settings = get_settings()


def render_fleet_map(snapshot: pd.DataFrame, theme_mode: str) -> None:
    """Render a live PyDeck fleet map with density clustering and status layers."""
    scoped = snapshot.dropna(subset=["latitude", "longitude"]).copy()
    if scoped.empty:
        st.info("No GPS coordinates are available for the selected fleet scope.")
        return

    scoped["latitude"] = pd.to_numeric(scoped["latitude"], errors="coerce")
    scoped["longitude"] = pd.to_numeric(scoped["longitude"], errors="coerce")
    scoped["marker_radius"] = pd.to_numeric(scoped["marker_radius"], errors="coerce").fillna(12000).clip(7000, 28000)
    scoped["critical_radius"] = scoped["marker_radius"] + 5000
    scoped["maintenance_radius"] = scoped["marker_radius"] + 2500
    scoped["tooltip_title"] = scoped["truck_label"] + " | " + scoped["operational_status"]
    view_state = pdk.ViewState(
        latitude=float(scoped["latitude"].mean()) if len(scoped) else settings.map_latitude,
        longitude=float(scoped["longitude"].mean()) if len(scoped) else settings.map_longitude,
        zoom=settings.map_zoom,
        pitch=settings.map_pitch,
    )
    layers = [
        pdk.Layer(
            "HexagonLayer",
            data=scoped,
            get_position=["longitude", "latitude"],
            radius=22000,
            elevation_scale=18,
            elevation_range=[0, 1200],
            extruded=True,
            coverage=0.92,
            opacity=0.18,
        ),
        pdk.Layer(
            "ScatterplotLayer",
            data=scoped,
            get_position=["longitude", "latitude"],
            get_fill_color="state_color",
            get_line_color=[255, 255, 255, 120],
            get_radius="marker_radius",
            pickable=True,
            stroked=True,
            line_width_min_pixels=1.2,
            opacity=0.92,
        ),
    ]
    critical = scoped[scoped["severity"] == "Critical"]
    maintenance = scoped[scoped["in_maintenance"]]
    if not critical.empty:
        layers.append(
            pdk.Layer(
                "ScatterplotLayer",
                data=critical,
                get_position=["longitude", "latitude"],
                get_fill_color=[0, 0, 0, 0],
                get_line_color=[244, 63, 94, 220],
                get_radius="critical_radius",
                stroked=True,
                filled=False,
                line_width_min_pixels=3,
                pickable=False,
            )
        )
    if not maintenance.empty:
        layers.append(
            pdk.Layer(
                "ScatterplotLayer",
                data=maintenance,
                get_position=["longitude", "latitude"],
                get_fill_color=[0, 0, 0, 0],
                get_line_color=[245, 158, 11, 220],
                get_radius="maintenance_radius",
                stroked=True,
                filled=False,
                line_width_min_pixels=2,
                pickable=False,
            )
        )

    tooltip = {
        "html": """
        <div style="font-family: IBM Plex Sans, sans-serif;">
            <div style="font-weight:700; margin-bottom:4px;">{tooltip_title}</div>
            <div>Driver: {driver_id}</div>
            <div>Speed: {speed} km/h</div>
            <div>Fuel: {fuel_level}%</div>
            <div>Engine Temp: {engine_temp} C</div>
            <div>Alert: {alert_type}</div>
            <div>Route: {start_city} -> {end_city}</div>
        </div>
        """,
        "style": {
            "backgroundColor": "#08111c" if theme_mode == "dark" else "#ffffff",
            "color": "#f8fafc" if theme_mode == "dark" else "#08111c",
        },
    }
    deck = pdk.Deck(
        layers=layers,
        initial_view_state=view_state,
        map_style="dark" if theme_mode == "dark" else "light",
        tooltip=tooltip,
    )
    st.pydeck_chart(deck, use_container_width=True)


def render_map_insights(snapshot: pd.DataFrame) -> None:
    """Render map-adjacent geospatial KPI callouts."""
    if snapshot.empty:
        return
    alert_zones = int(snapshot["is_alert"].sum())
    theft_zones = int(snapshot["theft"].sum())
    maintenance_zones = int(snapshot["in_maintenance"].sum())
    gps_issues = int(snapshot["gps_behavior_flag"].sum()) if "gps_behavior_flag" in snapshot.columns else 0
    st.markdown(
        f"""
        <div class="map-insight-grid">
            <div class="mini-metric"><span>{alert_zones}</span><small>alert locations</small></div>
            <div class="mini-metric"><span>{theft_zones}</span><small>theft locations</small></div>
            <div class="mini-metric"><span>{maintenance_zones}</span><small>maintenance zones</small></div>
            <div class="mini-metric"><span>{gps_issues}</span><small>GPS anomalies</small></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
