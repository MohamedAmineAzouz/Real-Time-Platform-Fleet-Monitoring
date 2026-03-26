"""
pages/1_⚡_Live_Monitoring.py
─────────────────────────────────────────────────────────────────────────────
Real-time fleet monitoring from speed layer:
  - truck_latest  → current state of every truck
  - alerts        → recent alert events (7-day TTL)
─────────────────────────────────────────────────────────────────────────────
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

from utils.cassandra_client import query_df
from utils.styles import CSS, alert_color, ALERT_ICONS, fmt_pct, fmt_km, fmt_speed, fmt_temp

st.set_page_config(page_title="Live Monitoring", page_icon="⚡", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)

# ── Sidebar controls ───────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚡ Live Monitoring")
    st.divider()
    auto_refresh = st.toggle("Auto-refresh (5s)", value=True)
    selected_filter = st.selectbox(
        "Filter by status",
        ["All", "Alerts only", "Normal only", "Refueling"]
    )
    st.divider()
    if st.button("🔄 Refresh now", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

st.title("⚡ Live Fleet Monitoring")

# ── Load truck_latest ──────────────────────────────────────────────────────────
@st.cache_data(ttl=5)
def load_trucks():
    return query_df("SELECT * FROM truck_latest")

trucks = load_trucks()

if trucks.empty:
    st.error("No data from speed layer. Is the streaming processor running?")
    st.stop()

# Apply filter
filtered = trucks.copy()
if selected_filter == "Alerts only":
    filtered = filtered[filtered["is_alert"] == True]
elif selected_filter == "Normal only":
    filtered = filtered[filtered["is_alert"] == False]
elif selected_filter == "Refueling":
    filtered = filtered[filtered["refueling"] == True]

# ── KPI row ────────────────────────────────────────────────────────────────────
c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Active Trucks",    len(trucks))
c2.metric("Alerts",           len(trucks[trucks["is_alert"] == True]))
c3.metric("Refueling",        len(trucks[trucks["refueling"] == True]))
c4.metric("Avg Speed",        fmt_speed(trucks["speed"].mean()))
c5.metric("Avg Fuel",         fmt_pct(trucks["fuel_level"].mean()))
c6.metric("Avg Engine Temp",  fmt_temp(trucks["engine_temp"].mean()))

st.divider()

# ── Truck cards ────────────────────────────────────────────────────────────────
st.subheader(f"Fleet Status ({len(filtered)} trucks)")

cols = st.columns(5)
for i, (_, row) in enumerate(filtered.iterrows()):
    alert_type = row.get("alert_type", "NORMAL")
    color      = alert_color(alert_type)
    icon       = ALERT_ICONS.get(alert_type, "✅")
    fuel_pct   = row.get("fuel_level", 0)
    is_ref     = row.get("refueling", False)
    trip_fuel  = row.get("fuel_consumed_trip", 0) or 0
    refueled   = row.get("fuel_refueled", 0) or 0

    # Fuel bar color
    fuel_color = "#ff4d4d" if fuel_pct < 20 else "#ff9500" if fuel_pct < 50 else "#00e676"
    fuel_bar   = f'<div style="background:#1a2a3a;height:4px;border-radius:2px;margin:6px 0">' \
                 f'<div style="background:{fuel_color};width:{fuel_pct:.0f}%;height:100%;border-radius:2px"></div></div>'

    refuel_line = f'<div style="color:#00e676;font-size:10px">⛽ Refueling at {row.get("refuel_city","?")} · +{refueled:.1f}%</div>' if is_ref else ""
    trip_line   = f'<div style="color:#ffffff;font-size:10px">Trip fuel: {trip_fuel:.1f}%</div>'

    with cols[i % 5]:
        st.markdown(
            f"""
        <div style="background:#0d1421;border:1px solid {color}44;border-left:3px solid {color};
        border-radius:8px;padding:12px;margin-bottom:8px">

        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
        <span style="font-family:monospace;font-size:14px;font-weight:700;color:#c8d8e8">
        🚛 T-{row['truck_id']:02d}
        </span>
        <span style="background:{color};color:#000;font-size:9px;font-weight:700;
        padding:2px 7px;border-radius:12px">{icon} {alert_type}</span>
        </div>

        <div style="display:grid;grid-template-columns:1fr 1fr;gap:4px;font-size:11px;color:#c8d8e8;margin-bottom:4px">
        <span>⚡ {row.get('speed',0):.0f} km/h</span>
        <span>⛽ {fuel_pct:.0f}%</span>
        <span>🌡️ {row.get('engine_temp',0):.0f}°C</span>
        <span>📍 {row.get('odometer_km',0):,.0f} km</span>
        </div>

        {fuel_bar}
        {trip_line}
        {refuel_line}

        <div style="font-size:9px;color:#ffffff;margin-top:4px">
        {row.get('start_city','?')} → {row.get('end_city','?')}
        </div>

        </div>
        """,
            unsafe_allow_html=True
        )

st.divider()

# ── Speed & Fuel charts ────────────────────────────────────────────────────────
col_l, col_r = st.columns(2)

with col_l:
    st.subheader("🚀 Speed by Truck")
    sorted_trucks = trucks.sort_values("speed", ascending=True)
    colors = [alert_color(a) for a in sorted_trucks["alert_type"]]
    fig = go.Figure(go.Bar(
        x=sorted_trucks["speed"],
        y=[f"T-{tid:02d}" for tid in sorted_trucks["truck_id"]],
        orientation="h",
        marker_color=colors,
        text=[f"{s:.0f}" for s in sorted_trucks["speed"]],
        textposition="outside",
    ))
    fig.add_vline(x=120, line_dash="dash", line_color="#ff4d4d", annotation_text="Limit 120")
    fig.update_layout(
        plot_bgcolor="#0d1421", paper_bgcolor="#0d1421",
        font_color="#c8d8e8", height=350,
        xaxis_title="km/h", yaxis_title="",
        margin=dict(l=10, r=40, t=10, b=40),
    )
    st.plotly_chart(fig, use_container_width=True)

with col_r:
    st.subheader("⛽ Fuel Level by Truck")
    sorted_fuel = trucks.sort_values("fuel_level", ascending=True)
    fuel_colors = [
        "#ff4d4d" if f < 20 else "#ff9500" if f < 50 else "#00e676"
        for f in sorted_fuel["fuel_level"]
    ]
    fig2 = go.Figure(go.Bar(
        x=sorted_fuel["fuel_level"],
        y=[f"T-{tid:02d}" for tid in sorted_fuel["truck_id"]],
        orientation="h",
        marker_color=fuel_colors,
        text=[f"{f:.0f}%" for f in sorted_fuel["fuel_level"]],
        textposition="outside",
    ))
    fig2.add_vline(x=20, line_dash="dash", line_color="#ff4d4d", annotation_text="Low 20%")
    fig2.update_layout(
        plot_bgcolor="#0d1421", paper_bgcolor="#0d1421",
        font_color="#c8d8e8", height=350,
        xaxis_title="%", yaxis_title="",
        xaxis_range=[0, 110],
        margin=dict(l=10, r=40, t=10, b=40),
    )
    st.plotly_chart(fig2, use_container_width=True)

# ── Recent alerts table ────────────────────────────────────────────────────────
st.subheader("🚨 Recent Alerts (last 50)")

@st.cache_data(ttl=10)
def load_alerts():
    alert_types = ["OVERSPEED", "OVERHEAT", "FUEL_THEFT", "FUEL_LEAK", "LOW_FUEL"]
    dfs = []
    for at in alert_types:
        df = query_df(
            "SELECT truck_id, alert_type, processed_at, speed, fuel_level, engine_temp, "
            "driver_id, latitude, longitude FROM alerts WHERE truck_id IN (1,2,3,4,5,6,7,8,9,10) "
            "AND alert_type = %s LIMIT 10 ALLOW FILTERING",
            [at]
        )
        dfs.append(df)
    return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()

alerts_df = load_alerts()

if not alerts_df.empty:
    alerts_df = alerts_df.sort_values("processed_at", ascending=False).head(50)
    alerts_df["truck"] = alerts_df["truck_id"].apply(lambda x: f"T-{x:02d}")
    alerts_df["time"]  = pd.to_datetime(alerts_df["processed_at"]).dt.strftime("%H:%M:%S")
    st.dataframe(
        alerts_df[["truck","alert_type","time","speed","fuel_level","engine_temp"]].rename(columns={
            "truck":"Truck","alert_type":"Type","time":"Time",
            "speed":"Speed (km/h)","fuel_level":"Fuel %","engine_temp":"Temp °C"
        }),
        use_container_width=True,
        hide_index=True,
    )
else:
    st.info("No recent alerts.")

# Auto-refresh
if auto_refresh:
    import time
    time.sleep(5)
    st.rerun()