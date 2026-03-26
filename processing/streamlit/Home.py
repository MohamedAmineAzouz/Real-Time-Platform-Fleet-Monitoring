"""
Home.py — Fleet Overview
─────────────────────────────────────────────────────────────────────────────
Entry point. Combines live data (speed layer) with daily summary (batch layer).
─────────────────────────────────────────────────────────────────────────────
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import date

from utils.cassandra_client import query_df
from utils.styles import CSS, alert_color, ALERT_ICONS, fmt_pct, fmt_km

st.set_page_config(
    page_title="FleetPulse Analytics",
    page_icon="🚛",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(CSS, unsafe_allow_html=True)


# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🚛 FleetPulse")
    st.caption("IoT Fleet Monitoring Platform")
    st.divider()
    st.markdown("**Data Sources**")
    st.markdown("🟢 Speed Layer → Cassandra")
    st.markdown("🟡 Batch Layer → Cassandra")
    st.divider()
    if st.button("🔄 Refresh", use_container_width=True):
        st.cache_data.clear()
        st.rerun()


st.title("🚛 Fleet Overview")
st.caption("Real-time + Batch analytics — refreshed every 30s")

# ── Section 1: Live KPIs from speed layer ─────────────────────────────────────
st.subheader("⚡ Live Fleet Status", divider="blue")

@st.cache_data(ttl=5)
def load_live():
    return query_df("SELECT * FROM truck_latest")

live = load_live()

if live.empty:
    st.warning("No live data — is the speed layer running?")
else:
    total      = len(live)
    alerts     = live[live["is_alert"] == True]
    alert_cnt  = len(alerts)
    normal_cnt = total - alert_cnt
    avg_speed  = live["speed"].mean()
    avg_fuel   = live["fuel_level"].mean()
    refueling  = live[live["refueling"] == True]

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total Trucks",   total)
    c2.metric("🟢 Normal",      normal_cnt)
    c3.metric("🔴 Alerts",      alert_cnt,
              delta=f"-{alert_cnt}" if alert_cnt == 0 else None,
              delta_color="inverse")
    c4.metric("Avg Speed",      f"{avg_speed:.0f} km/h")
    c5.metric("Avg Fuel",       f"{avg_fuel:.0f}%")

    if alert_cnt > 0:
        st.markdown("##### 🚨 Active Alerts")
        cols = st.columns(min(alert_cnt, 4))
        for i, (_, row) in enumerate(alerts.iterrows()):
            color = alert_color(row.get("alert_type", "NORMAL"))
            icon  = ALERT_ICONS.get(row.get("alert_type", "NORMAL"), "⚠️")
            with cols[i % 4]:
                st.markdown(
                    f"""<div style="background:{color}22;border:1px solid {color};
                    border-radius:8px;padding:10px 14px;margin:4px 0">
                    <div style="color:{color};font-weight:700;font-size:13px">
                        {icon} Truck #{row['truck_id']}
                    </div>
                    <div style="font-size:11px;color:#888;margin-top:4px">
                        {row.get('alert_type','—')} · {row.get('speed',0):.0f} km/h · ⛽{row.get('fuel_level',0):.0f}%
                    </div></div>""",
                    unsafe_allow_html=True
                )

    # Live map
    st.markdown("##### 🗺️ Live Truck Positions")
    map_df = live[["truck_id", "latitude", "longitude", "alert_type", "speed", "fuel_level"]].copy()
    map_df["color"] = map_df["alert_type"].apply(alert_color)
    map_df["label"] = map_df.apply(
        lambda r: f"T-{r['truck_id']:02d} | {r['speed']:.0f} km/h | ⛽{r['fuel_level']:.0f}%", axis=1
    )
    fig_map = px.scatter_mapbox(
        map_df,
        lat="latitude", lon="longitude",
        color="alert_type",
        color_discrete_map={k: v for k, v in {
            "NORMAL":"#00e676","OVERSPEED":"#ff9500","OVERHEAT":"#ff4d4d",
            "FUEL_THEFT":"#ff4d4d","FUEL_LEAK":"#ffdd00","LOW_FUEL":"#ff9500"
        }.items()},
        hover_name="label",
        zoom=5, height=420,
        mapbox_style="carto-darkmatter",
    )
    fig_map.update_layout(margin={"r":0,"t":0,"l":0,"b":0}, legend_title="Status")
    st.plotly_chart(fig_map, use_container_width=True)


# ── Section 2: Daily summary from batch layer ──────────────────────────────────
st.subheader("📊 Daily Batch Summary", divider="orange")

@st.cache_data(ttl=300)
def load_batch_today():
    today = str(date.today())
    return query_df(
        "SELECT * FROM batch_daily_truck_stats WHERE stat_date = %s ALLOW FILTERING",
        [today]
    )

batch = load_batch_today()

if batch.empty:
    st.info("No batch results for today yet — the DAG runs at 02:00 UTC.")
else:
    b1, b2, b3, b4 = st.columns(4)
    b1.metric("Total Distance",   fmt_km(batch["total_distance_km"].sum()))
    b2.metric("Total Fuel Used",  fmt_pct(batch["total_fuel_consumed_pct"].sum() if "total_fuel_consumed_pct" in batch else None))
    b3.metric("Total Alerts",     int(batch["total_alerts"].sum()))
    b4.metric("Avg Fuel/100km",   f"{batch['fuel_per_100km'].mean():.2f} %/km" if "fuel_per_100km" in batch else "—")

    col_l, col_r = st.columns(2)

    with col_l:
        st.markdown("**Distance per Truck**")
        fig_dist = px.bar(
            batch.sort_values("total_distance_km", ascending=False),
            x="truck_id", y="total_distance_km",
            labels={"truck_id": "Truck", "total_distance_km": "km"},
            color_discrete_sequence=["#00b4ff"],
        )
        fig_dist.update_layout(
            plot_bgcolor="#0d1421", paper_bgcolor="#0d1421",
            font_color="#c8d8e8", height=280,
        )
        st.plotly_chart(fig_dist, use_container_width=True)

    with col_r:
        st.markdown("**Alerts by Type**")
        alert_cols = ["overspeed_count","overheat_count","fuel_theft_count","low_fuel_count"]
        alert_cols = [c for c in alert_cols if c in batch.columns]
        if alert_cols:
            alert_totals = batch[alert_cols].sum().reset_index()
            alert_totals.columns = ["type", "count"]
            alert_totals["type"] = alert_totals["type"].str.replace("_count","").str.upper()
            fig_pie = px.pie(
                alert_totals, values="count", names="type",
                color="type",
                color_discrete_map={
                    "OVERSPEED":"#ff9500","OVERHEAT":"#ff4d4d",
                    "FUEL_THEFT":"#cc0000","LOW_FUEL":"#ffdd00"
                },
                hole=0.5,
            )
            fig_pie.update_layout(
                plot_bgcolor="#0d1421", paper_bgcolor="#0d1421",
                font_color="#c8d8e8", height=280,
                legend=dict(orientation="v"),
            )
            st.plotly_chart(fig_pie, use_container_width=True)

# ── Auto-refresh ───────────────────────────────────────────────────────────────
st.caption("⚡ Live data refreshes every 5s · 📊 Batch data refreshes every 5min")