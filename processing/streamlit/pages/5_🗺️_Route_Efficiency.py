"""
pages/5_🗺️_Route_Efficiency.py
─────────────────────────────────────────────────────────────────────────────
Route-level analytics from batch layer:
  - batch_route_efficiency → per-route stats, best truck/driver per route
─────────────────────────────────────────────────────────────────────────────
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import date

from utils.cassandra_client import query_df
from utils.styles import CSS

st.set_page_config(page_title="Route Efficiency", page_icon="🗺️", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)

with st.sidebar:
    st.markdown("## 🗺️ Route Efficiency")
    st.divider()
    run_date = st.date_input("Select date", value=date.today())
    st.divider()
    if st.button("🔄 Refresh", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

st.title("🗺️ Route Efficiency Analysis")
st.caption(f"Per-route performance for **{run_date}**")

@st.cache_data(ttl=300)
def load_routes(stat_date: str):
    return query_df(
        "SELECT * FROM batch_route_efficiency WHERE stat_date = %s ALLOW FILTERING",
        [stat_date]
    )

df = load_routes(str(run_date))

if df.empty:
    st.warning(f"No route efficiency data for {run_date}.")
    st.stop()

df["route"] = df["start_city"] + " → " + df["end_city"]
df = df.sort_values("avg_fuel_per_100km", ascending=True)

# ── KPIs ───────────────────────────────────────────────────────────────────────
r1, r2, r3, r4 = st.columns(4)
r1.metric("Routes Analyzed",   len(df))
r2.metric("Total Trips",       int(df["total_trips"].sum()))
r3.metric("Best Fuel Route",   df.iloc[0]["route"] if len(df) > 0 else "—")
r4.metric("Best Fuel/100km",   f"{df.iloc[0]['avg_fuel_per_100km']:.2f} %/km" if len(df) > 0 else "—")

st.divider()

col_l, col_r = st.columns(2)

with col_l:
    st.subheader("⛽ Fuel Efficiency by Route")
    colors = [
        "#00e676" if v < df["avg_fuel_per_100km"].quantile(0.33)
        else "#ff9500" if v < df["avg_fuel_per_100km"].quantile(0.66)
        else "#ff4d4d"
        for v in df["avg_fuel_per_100km"]
    ]
    fig = go.Figure(go.Bar(
        y=df["route"], x=df["avg_fuel_per_100km"],
        orientation="h", marker_color=colors,
        text=[f"{v:.2f}" for v in df["avg_fuel_per_100km"]],
        textposition="outside",
    ))
    fig.update_layout(
        plot_bgcolor="#0d1421", paper_bgcolor="#0d1421",
        font_color="#c8d8e8", height=max(300, len(df) * 28),
        xaxis_title="%/km",
        margin=dict(l=10, r=60, t=10, b=40),
    )
    st.plotly_chart(fig, use_container_width=True)

with col_r:
    st.subheader("🚀 Average Speed by Route")
    fig2 = px.bar(
        df.sort_values("avg_speed_kmh", ascending=True),
        y="route", x="avg_speed_kmh", orientation="h",
        labels={"route": "", "avg_speed_kmh": "km/h"},
        color="avg_speed_kmh",
        color_continuous_scale=[[0,"#0d1421"],[0.5,"#00b4ff"],[1,"#00e676"]],
        text_auto=".0f",
    )
    fig2.update_layout(
        plot_bgcolor="#0d1421", paper_bgcolor="#0d1421",
        font_color="#c8d8e8", height=max(300, len(df) * 28),
        coloraxis_showscale=False,
        margin=dict(l=10, r=40, t=10, b=40),
    )
    st.plotly_chart(fig2, use_container_width=True)

# ── Route details table ────────────────────────────────────────────────────────
st.subheader("📋 Route Details")
show = [c for c in [
    "route","total_trips","avg_distance_km","avg_fuel_per_100km",
    "avg_speed_kmh","avg_duration_min","avg_alerts_per_trip",
    "most_efficient_truck","best_fuel_per_100km"
] if c in df.columns or c == "route"]

st.dataframe(
    df[show].rename(columns={
        "route":"Route","total_trips":"Trips",
        "avg_distance_km":"Avg Dist (km)","avg_fuel_per_100km":"Fuel %/km",
        "avg_speed_kmh":"Avg Speed","avg_duration_min":"Avg Duration (min)",
        "avg_alerts_per_trip":"Alerts/Trip",
        "most_efficient_truck":"Best Truck","best_fuel_per_100km":"Best Fuel %/km",
    }),
    use_container_width=True, hide_index=True,
)