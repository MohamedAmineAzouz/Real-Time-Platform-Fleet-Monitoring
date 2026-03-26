"""
pages/3_👤_Driver_Performance.py
─────────────────────────────────────────────────────────────────────────────
Driver ranking and performance scoring from batch layer:
  - batch_driver_performance → scores, rankings, fuel efficiency per driver
─────────────────────────────────────────────────────────────────────────────
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import date

from utils.cassandra_client import query_df
from utils.styles import CSS, score_color

st.set_page_config(page_title="Driver Performance", page_icon="👤", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)

with st.sidebar:
    st.markdown("## 👤 Driver Performance")
    st.divider()
    run_date = st.date_input("Select date", value=date.today())
    top_n    = st.slider("Show top N drivers", 5, 20, 10)
    st.divider()
    if st.button("🔄 Refresh", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

st.title("👤 Driver Performance Ranking")
st.caption(f"Composite scoring for **{run_date}** — Speed 30% · Fuel 30% · Alerts 25% · Distance 15%")

@st.cache_data(ttl=300)
def load_performance(stat_date: str):
    return query_df(
        "SELECT * FROM batch_driver_performance WHERE stat_date = %s ALLOW FILTERING",
        [stat_date]
    )

df = load_performance(str(run_date))

if df.empty:
    st.warning(f"No driver performance data for {run_date}.")
    st.stop()

df = df.sort_values("performance_score", ascending=False).reset_index(drop=True)
df["rank_display"] = df.index + 1
df["driver_short"] = df["driver_id"].str[:8] + "…"

# ── Top 3 podium ───────────────────────────────────────────────────────────────
st.subheader("🏆 Top Performers")
podium_cols = st.columns(3)
medals = ["🥇", "🥈", "🥉"]
podium_colors = ["#ffd700", "#c0c0c0", "#cd7f32"]

for i, (col, medal, color) in enumerate(zip(podium_cols, medals, podium_colors)):
    if i >= len(df):
        break
    row = df.iloc[i]
    score = row.get("performance_score", 0)
    with col:
        st.markdown(
            f"""<div style="background:#0d1421;border:1px solid {color}66;border-top:3px solid {color};
            border-radius:8px;padding:16px;text-align:center">
            <div style="font-size:32px">{medal}</div>
            <div style="font-family:monospace;font-size:11px;color:#4a6080;margin:4px 0">
                {row['driver_short']}
            </div>
            <div style="font-size:36px;font-weight:700;color:{color};line-height:1">{score:.0f}</div>
            <div style="font-size:10px;color:#4a6080;letter-spacing:2px">SCORE</div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:4px;margin-top:10px;font-size:10px;color:#c8d8e8">
                <span>⚡ {row.get('avg_speed',0):.0f} km/h</span>
                <span>⛽ {row.get('fuel_per_100km',0):.1f} %/km</span>
                <span>🚨 {row.get('alert_rate_per_100',0):.1f}/100</span>
                <span>📏 {row.get('total_distance_km',0):,.0f} km</span>
            </div></div>""",
            unsafe_allow_html=True
        )

st.divider()

# ── Score breakdown radar ──────────────────────────────────────────────────────
st.subheader("📡 Score Component Breakdown")

score_cols = ["speed_score", "fuel_score", "alert_score", "distance_score"]
available_score_cols = [c for c in score_cols if c in df.columns]

if available_score_cols:
    top_df  = df.head(top_n)
    fig_bar = go.Figure()
    colors_map = {
        "speed_score": "#00b4ff", "fuel_score": "#00e676",
        "alert_score": "#ff9500", "distance_score": "#b44fff"
    }
    labels_map = {
        "speed_score": "Speed 30%", "fuel_score": "Fuel 30%",
        "alert_score": "Alerts 25%", "distance_score": "Distance 15%"
    }
    for col in available_score_cols:
        fig_bar.add_trace(go.Bar(
            name=labels_map.get(col, col),
            x=top_df["driver_short"],
            y=top_df[col],
            marker_color=colors_map.get(col, "#888"),
        ))
    fig_bar.update_layout(
        barmode="group",
        plot_bgcolor="#0d1421", paper_bgcolor="#0d1421",
        font_color="#c8d8e8", height=380,
        yaxis=dict(range=[0, 105], title="Score"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        margin=dict(l=10, r=10, t=40, b=80),
    )
    st.plotly_chart(fig_bar, use_container_width=True)

# ── Full ranking table ─────────────────────────────────────────────────────────
st.subheader(f"📋 Full Ranking (Top {top_n})")

display = df.head(top_n)[["rank_display","driver_short","performance_score",
                            "total_distance_km","fuel_per_100km",
                            "speed_compliance_rate","alert_rate_per_100",
                            "theft_events"]].copy()

display.columns = ["Rank","Driver","Score","Distance (km)",
                   "Fuel %/km","Speed Compliance","Alert Rate","Theft Events"]

# Color-code the score column
def color_score(val):
    c = score_color(val)
    return f"color: {c}; font-weight: 700"

st.dataframe(
    display.style.applymap(color_score, subset=["Score"]),
    use_container_width=True,
    hide_index=True,
)