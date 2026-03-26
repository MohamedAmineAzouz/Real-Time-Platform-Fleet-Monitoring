"""
pages/4_⛽_Fuel_&_Maintenance.py
─────────────────────────────────────────────────────────────────────────────
Fuel waste detection and maintenance prediction from batch layer:
  - batch_fuel_waste_anomalies → trucks consuming above fleet median
  - batch_maintenance_flags    → trucks needing maintenance
─────────────────────────────────────────────────────────────────────────────
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import date

from utils.cassandra_client import query_df
from utils.styles import CSS

st.set_page_config(page_title="Fuel & Maintenance", page_icon="⛽", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)

with st.sidebar:
    st.markdown("## ⛽ Fuel & Maintenance")
    st.divider()
    run_date = st.date_input("Select date", value=date.today())
    st.divider()
    if st.button("🔄 Refresh", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

st.title("⛽ Fuel Analysis & Maintenance Prediction")
st.caption(f"Batch analysis for **{run_date}**")

@st.cache_data(ttl=300)
def load_fuel_anomalies(stat_date: str):
    return query_df(
        "SELECT * FROM batch_fuel_waste_anomalies WHERE stat_date = %s ALLOW FILTERING",
        [stat_date]
    )

@st.cache_data(ttl=300)
def load_maintenance(stat_date: str):
    return query_df(
        "SELECT * FROM batch_maintenance_flags WHERE stat_date = %s ALLOW FILTERING",
        [stat_date]
    )

fuel_df  = load_fuel_anomalies(str(run_date))
maint_df = load_maintenance(str(run_date))

# ── Section 1: Fuel waste anomalies ───────────────────────────────────────────
st.subheader("🔴 Fuel Waste Anomalies")
st.caption("Trucks consuming > 1.5× fleet median fuel efficiency")

if fuel_df.empty:
    st.success("✅ No fuel waste anomalies detected today.")
else:
    f1, f2, f3 = st.columns(3)
    f1.metric("Anomalous Trucks",  len(fuel_df))
    f2.metric("Fleet Median",
              f"{fuel_df['fleet_median_fuel_per_100km'].iloc[0]:.2f} %/km"
              if "fleet_median_fuel_per_100km" in fuel_df else "—")
    f3.metric("Anomaly Threshold",
              f"{fuel_df['anomaly_threshold'].iloc[0]:.2f} %/km"
              if "anomaly_threshold" in fuel_df else "—")

    fuel_df["truck_label"] = fuel_df["truck_id"].apply(lambda x: f"T-{x:02d}")
    fuel_df = fuel_df.sort_values("waste_vs_median_pct", ascending=False)

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=fuel_df["truck_label"],
        y=fuel_df["fuel_per_100km"],
        name="Truck Consumption",
        marker_color="#ff4d4d",
        text=[f"{v:.1f}" for v in fuel_df["fuel_per_100km"]],
        textposition="outside",
    ))
    if "fleet_median_fuel_per_100km" in fuel_df:
        fig.add_hline(
            y=fuel_df["fleet_median_fuel_per_100km"].iloc[0],
            line_dash="dash", line_color="#00e676",
            annotation_text="Fleet Median",
        )
    if "anomaly_threshold" in fuel_df:
        fig.add_hline(
            y=fuel_df["anomaly_threshold"].iloc[0],
            line_dash="dot", line_color="#ff9500",
            annotation_text="Anomaly Threshold (1.5×)",
        )
    fig.update_layout(
        plot_bgcolor="#0d1421", paper_bgcolor="#0d1421",
        font_color="#c8d8e8", height=340,
        yaxis_title="%/km",
        margin=dict(l=10, r=10, t=10, b=40),
    )
    st.plotly_chart(fig, use_container_width=True)

    with st.expander("📋 Anomaly Details"):
        show_cols = [c for c in [
            "truck_label","total_distance_km","total_fuel_consumed_pct",
            "fuel_per_100km","waste_vs_median_pct","event_count"
        ] if c in fuel_df.columns or c == "truck_label"]
        st.dataframe(
            fuel_df[show_cols].rename(columns={
                "truck_label":"Truck","total_distance_km":"Distance (km)",
                "total_fuel_consumed_pct":"Fuel Used (%)",
                "fuel_per_100km":"Fuel/100km","waste_vs_median_pct":"% Above Median",
                "event_count":"Events",
            }),
            use_container_width=True, hide_index=True,
        )

st.divider()

# ── Section 2: Maintenance flags ───────────────────────────────────────────────
st.subheader("🔧 Maintenance Prediction")
st.caption("Trucks flagged based on engine temp, overheat alerts, odometer, and fuel inconsistency")

if maint_df.empty:
    st.success("✅ No maintenance flags today.")
else:
    high = maint_df[maint_df.get("priority", pd.Series()) == "HIGH"] if "priority" in maint_df else pd.DataFrame()
    med  = maint_df[maint_df.get("priority", pd.Series()) == "MEDIUM"] if "priority" in maint_df else pd.DataFrame()

    m1, m2, m3 = st.columns(3)
    m1.metric("Total Flagged",    len(maint_df))
    m2.metric("🔴 HIGH Priority", len(high))
    m3.metric("🟡 MEDIUM Priority", len(med))

    maint_df["truck_label"] = maint_df["truck_id"].apply(lambda x: f"T-{x:02d}")

    # Flag cards
    flag_cols_map = {
        "flag_high_temp":          ("🌡️ High Temp",        "#ff4d4d"),
        "flag_overheat_alerts":    ("🔥 Overheat Alerts",  "#ff6b35"),
        "flag_odometer_milestone": ("📍 Odometer 10k",     "#ff9500"),
        "flag_fuel_inconsistency": ("⚠️ Fuel Inconsistency","#ffdd00"),
    }

    for _, row in maint_df.iterrows():
        priority = row.get("priority", "MEDIUM")
        p_color  = "#ff4d4d" if priority == "HIGH" else "#ff9500"
        flags_active = [
            label for col, (label, _) in flag_cols_map.items()
            if col in row and row[col]
        ]
        flag_html = " ".join([
            f'<span style="background:{c}22;border:1px solid {c};color:{c};'
            f'font-size:9px;padding:2px 7px;border-radius:12px;font-weight:700">{lbl}</span>'
            for col, (lbl, c) in flag_cols_map.items()
            if col in row and row[col]
        ])

        st.markdown(
            f"""<div style="background:#0d1421;border:1px solid {p_color}44;
            border-left:4px solid {p_color};border-radius:8px;padding:12px 16px;margin-bottom:8px">
            <div style="display:flex;justify-content:space-between;align-items:center">
                <span style="font-family:monospace;font-size:14px;color:#c8d8e8;font-weight:700">
                    🚛 {row['truck_label']}
                </span>
                <span style="background:{p_color};color:#000;font-size:9px;font-weight:700;
                    padding:3px 10px;border-radius:12px">{priority}</span>
            </div>
            <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;
                margin:8px 0;font-size:11px;color:#c8d8e8">
                <span>🌡️ Avg {row.get('avg_engine_temp',0):.0f}°C</span>
                <span>🔥 {row.get('overheat_count',0)} overheats</span>
                <span>📍 {row.get('max_odometer_km',0):,.0f} km</span>
                <span>⚠️ Fuel σ {row.get('fuel_rate_stddev',0):.3f}</span>
            </div>
            <div style="display:flex;gap:6px;flex-wrap:wrap">{flag_html}</div>
            </div>""",
            unsafe_allow_html=True
        )