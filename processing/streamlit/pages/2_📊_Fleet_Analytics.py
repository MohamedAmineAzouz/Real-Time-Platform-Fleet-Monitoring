"""
pages/2_📊_Fleet_Analytics.py
─────────────────────────────────────────────────────────────────────────────
Daily fleet analytics from batch layer:
  - batch_daily_truck_stats → distance, fuel, alerts per truck per day
─────────────────────────────────────────────────────────────────────────────
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import date, timedelta

from utils.cassandra_client import query_df
from utils.styles import CSS, fmt_km, fmt_pct, fmt_speed

st.set_page_config(page_title="Fleet Analytics", page_icon="📊", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)

with st.sidebar:
    st.markdown("## 📊 Fleet Analytics")
    st.divider()
    run_date = st.date_input("Select date", value=date.today())
    st.divider()
    if st.button("🔄 Refresh", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

st.title("📊 Daily Fleet Analytics")
st.caption(f"Batch results for **{run_date}** — computed nightly by Airflow + Spark")

# ── Load batch data ────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def load_daily_stats(stat_date: str):
    return query_df(
        "SELECT * FROM batch_daily_truck_stats WHERE stat_date = %s ALLOW FILTERING",
        [stat_date]
    )

df = load_daily_stats(str(run_date))

if df.empty:
    st.warning(f"No batch results for {run_date}. The DAG runs at 02:00 UTC.")
    st.info("💡 Trigger the DAG manually in Airflow UI to generate results now.")
    st.stop()

df["truck_label"] = df["truck_id"].apply(lambda x: f"T-{x:02d}")

# ── KPI row ────────────────────────────────────────────────────────────────────
fleet_dist   = df["total_distance_km"].sum()
fleet_alerts = int(df["total_alerts"].sum())
avg_fuel_eff = df["fuel_per_100km"].mean() if "fuel_per_100km" in df else None
most_driven  = df.loc[df["total_distance_km"].idxmax(), "truck_id"]

c1, c2, c3, c4 = st.columns(4)
c1.metric("Fleet Distance",   fmt_km(fleet_dist))
c2.metric("Total Alerts",     fleet_alerts)
c3.metric("Avg Fuel/100km",   f"{avg_fuel_eff:.2f} %/km" if avg_fuel_eff else "—")
c4.metric("Most Active",      f"T-{most_driven:02d}")

st.divider()

# ── Distance & fuel charts ─────────────────────────────────────────────────────
col_l, col_r = st.columns(2)

with col_l:
    st.subheader("📏 Distance Driven")
    fig = px.bar(
        df.sort_values("total_distance_km", ascending=False),
        x="truck_label", y="total_distance_km",
        labels={"truck_label": "", "total_distance_km": "km"},
        color="total_distance_km",
        color_continuous_scale=[[0,"#0d1421"],[0.5,"#00b4ff"],[1,"#00e676"]],
        text_auto=".0f",
    )
    fig.update_layout(
        plot_bgcolor="#0d1421", paper_bgcolor="#0d1421",
        font_color="#c8d8e8", height=320, coloraxis_showscale=False,
        margin=dict(l=10, r=10, t=10, b=40),
    )
    st.plotly_chart(fig, use_container_width=True)

with col_r:
    st.subheader("⛽ Fuel Efficiency (L/100km)")
    sorted_eff = df.sort_values("fuel_per_100km", ascending=True)
    eff_colors = [
        "#00e676" if v < 10 else "#ff9500" if v < 15 else "#ff4d4d"
        for v in sorted_eff["fuel_per_100km"]
    ]
    fig2 = go.Figure(go.Bar(
        x=sorted_eff["truck_label"],
        y=sorted_eff["fuel_per_100km"],
        marker_color=eff_colors,
        text=[f"{v:.1f}" for v in sorted_eff["fuel_per_100km"]],
        textposition="outside",
    ))
    fig2.update_layout(
        plot_bgcolor="#0d1421", paper_bgcolor="#0d1421",
        font_color="#c8d8e8", height=320,
        yaxis_title="%/km",
        margin=dict(l=10, r=10, t=10, b=40),
    )
    st.plotly_chart(fig2, use_container_width=True)

# ── Alert breakdown ────────────────────────────────────────────────────────────
st.subheader("🚨 Alert Breakdown by Truck")

alert_cols = {
    "overspeed_count": ("⚡ Overspeed", "#ff9500"),
    "overheat_count":  ("🌡️ Overheat",  "#ff4d4d"),
    "fuel_theft_count":("🚨 Theft",     "#cc0000"),
    "low_fuel_count":  ("⛽ Low Fuel",  "#ffdd00"),
}
available = {k: v for k, v in alert_cols.items() if k in df.columns}

if available:
    fig3 = go.Figure()
    for col, (label, color) in available.items():
        fig3.add_trace(go.Bar(
            name=label,
            x=df["truck_label"],
            y=df[col],
            marker_color=color,
        ))
    fig3.update_layout(
        barmode="stack",
        plot_bgcolor="#0d1421", paper_bgcolor="#0d1421",
        font_color="#c8d8e8", height=320,
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        margin=dict(l=10, r=10, t=40, b=40),
    )
    st.plotly_chart(fig3, use_container_width=True)

# ── Raw data table ─────────────────────────────────────────────────────────────
with st.expander("📋 Raw Data Table"):
    display_cols = [c for c in [
        "truck_label","total_distance_km","total_fuel_consumed_pct",
        "fuel_per_100km","avg_speed_kmh","max_speed_kmh",
        "total_alerts","overspeed_count","overheat_count",
        "fuel_theft_count","low_fuel_count","event_count"
    ] if c in df.columns or c == "truck_label"]
    st.dataframe(
        df[display_cols].rename(columns={"truck_label": "Truck"}),
        use_container_width=True, hide_index=True,
    )