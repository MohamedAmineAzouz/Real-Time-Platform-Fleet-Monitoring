import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import time

from utils.cassandra_client import query_df
from utils.styles import get_css, THEMES, ALERT_COLORS, ALERT_ICONS, get_alert_style, hex_to_rgba

# ── Page Config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="FleetPulse | Real-Time Fleet Control Tower",
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Theme Management ─────────────────────────────────────────────────────────
if 'theme_mode' not in st.session_state:
    st.session_state.theme_mode = "Dark"

# Apply Custom CSS based on selected theme
st.markdown(get_css(st.session_state.theme_mode), unsafe_allow_html=True)
current_theme = THEMES[st.session_state.theme_mode]

# ── Data Loading ─────────────────────────────────────────────────────────────
@st.cache_data(ttl=5)
def get_live_data():
    try:
        df_trucks = query_df("SELECT * FROM truck_latest")
        df_drivers = query_df("SELECT * FROM drivers")
        
        if df_trucks.empty:
            return pd.DataFrame(), pd.DataFrame()
            
        # Join in memory (Cassandra doesn't support joins well)
        if not df_drivers.empty:
            df = df_trucks.merge(df_drivers[['driver_id', 'name']], on='driver_id', how='left')
            df['driver_name'] = df['name'].fillna(df['driver_id'])
        else:
            df = df_trucks
            df['driver_name'] = df['driver_id']
            
        return df, df_drivers
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return pd.DataFrame(), pd.DataFrame()

# ── Helper Components ─────────────────────────────────────────────────────────
def kpi_card(label, value, trend=None, icon="📊", color=None):
    if color is None:
        color = current_theme["primary"]
        
    trend_html = ""
    if trend is not None:
        trend_class = "trend-up" if trend >= 0 else "trend-down"
        trend_icon = "↑" if trend >= 0 else "↓"
        trend_html = f'<div class="trend-indicator {trend_class}">{trend_icon} {abs(trend)}%</div>'
    
    st.markdown(f"""
        <div class="metric-card">
            <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                <div class="metric-label">{label}</div>
                <div style="font-size: 1.5rem;">{icon}</div>
            </div>
            <div class="metric-value">{value}</div>
            {trend_html}
        </div>
    """, unsafe_allow_html=True)

# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"""
        <div style="text-align: left; padding: 0.5rem 0;">
            <div class="sidebar-title">🛰️ FleetPulse</div>
            <div class="sidebar-subtitle">V2 Enterprise Stack</div>
        </div>
    """, unsafe_allow_html=True)
    
    st.markdown('<div class="sidebar-section-header">Executive Theme</div>', unsafe_allow_html=True)
    
    # Theme Toggle as a single component
    is_dark = st.toggle("Dark Mode", value=(st.session_state.theme_mode == "Dark"), help="Switch between Enterprise Dark and Professional Light themes.")
    new_mode = "Dark" if is_dark else "Light"
    
    if new_mode != st.session_state.theme_mode:
        st.session_state.theme_mode = new_mode
        st.rerun()

    st.markdown('<div class="sidebar-section-header">Live System Health</div>', unsafe_allow_html=True)
    
    # System Status
    st.markdown(f"""
        <div class="system-status-container">
            <div class="system-status-text">
                <span class="live-dot"></span> OPERATIONAL
            </div>
            <div style="color: {current_theme['text_muted']}; font-size: 0.7rem; margin-top: 8px; line-height: 1.4;">
                <b>CLUSTER:</b> Connected<br>
                <b>LATENCY:</b> 42ms<br>
                <b>STREAM:</b> Active
            </div>
        </div>
    """, unsafe_allow_html=True)

    # Load data for filters
    live_df, drivers_df = get_live_data()
    
    st.markdown('<div class="sidebar-section-header">Fleet Filters</div>', unsafe_allow_html=True)
    
    if not live_df.empty:
        truck_list = ["All Trucks"] + sorted(live_df['truck_id'].unique().tolist())
        selected_truck = st.selectbox("Search Truck ID", truck_list)
        
        driver_list = ["All Drivers"] + sorted(live_df['driver_name'].unique().tolist())
        selected_driver = st.selectbox("Search Driver", driver_list)

        st.markdown('<div class="sidebar-section-header">View Settings</div>', unsafe_allow_html=True)
        truck_count_limit = st.slider("Display Intensity", min_value=5, max_value=50, value=10, step=5)
    else:
        st.info("Awaiting Telemetry...")

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🔄 Force Cluster Refresh", type="primary", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# ── Header ──────────────────────────────────────────────────────────────────
col_title, col_status = st.columns([3, 1])

with col_title:
    st.markdown(f"""
        <h1 style="margin-bottom: 0; color: {current_theme['text_main']};">Real-Time Fleet Intelligence</h1>
        <p style="color: {current_theme['text_muted']}; font-size: 1.1rem;">Command & Control Operations Center</p>
    """, unsafe_allow_html=True)

with col_status:
    now = datetime.now().strftime("%H:%M:%S")
    st.markdown(f"""
        <div class="glass-card" style="padding: 15px; text-align: right; margin-bottom: 0;">
            <div style="color: {current_theme['success']}; font-weight: 700; font-size: 0.9rem;">
                <span class="live-dot"></span> LIVE STREAM ACTIVE
            </div>
            <div style="color: {current_theme['text_muted']}; font-size: 0.8rem; margin-top: 5px;">
                Last Refresh: {now}
            </div>
            <div style="color: {current_theme['primary']}; font-size: 0.7rem; font-weight: 600; margin-top: 2px;">
                REFRESH RATE: 5s
            </div>
        </div>
    """, unsafe_allow_html=True)

# ── Filter Data ─────────────────────────────────────────────────────────────
if not live_df.empty:
    filtered_df = live_df.copy()
    if selected_truck != "All Trucks":
        filtered_df = filtered_df[filtered_df['truck_id'] == selected_truck]
    if selected_driver != "All Drivers":
        filtered_df = filtered_df[filtered_df['driver_name'] == selected_driver]

    # ── KPI Section ─────────────────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    kpi1, kpi2, kpi3, kpi4, kpi5, kpi6 = st.columns(6)
    
    active_trucks = len(filtered_df)
    active_alerts = len(filtered_df[filtered_df['is_alert'] == True])
    in_maintenance = len(filtered_df[filtered_df['in_maintenance'] == True])
    avg_speed = filtered_df['speed'].mean()
    avg_fuel = filtered_df['fuel_level'].mean()
    avg_temp = filtered_df['engine_temp'].mean()

    with kpi1: kpi_card("Active Trucks", active_trucks, trend=2, icon="🚛")
    with kpi2: kpi_card("Active Alerts", active_alerts, trend=-5 if active_alerts > 0 else 0, icon="🚨", color=current_theme["danger"])
    with kpi3: kpi_card("In Maintenance", in_maintenance, trend=0, icon="🛠️", color=current_theme["warning"])
    with kpi4: kpi_card("Avg Speed", f"{avg_speed:.1f} km/h", trend=1, icon="⚡")
    with kpi5: kpi_card("Avg Fuel", f"{avg_fuel:.1f}%", trend=-1, icon="⛽")
    with kpi6: kpi_card("Avg Engine Temp", f"{avg_temp:.1f}°C", trend=3, icon="🌡️")


    st.markdown("<br><br>", unsafe_allow_html=True)

    # ── Main Content ──────────────────────────────────────────────────────────
    col_left, col_right = st.columns([2, 1])

    with col_left:
        # Alert Monitoring Center
        st.markdown(f"""
            <div class="glass-card">
                <div class="card-header">
                    <h3 style="color: {current_theme['text_main']};">🚨 REAL-TIME ALERT MONITORING</h3>
                </div>
                <div class="card-body">
        """, unsafe_allow_html=True)
        
        alerts_only = filtered_df[filtered_df['is_alert'] == True].sort_values('event_time', ascending=False)
        
        if alerts_only.empty:
            st.success("No active critical alerts detected in the fleet.")
        else:
            for _, alert in alerts_only.iterrows():
                color, icon = get_alert_style(alert['alert_type'])
                st.markdown(f"""
                    <div class="alert-item" style="border-color: {color};">
                        <div style="display: flex; justify-content: space-between;">
                            <span style="font-weight: 700; color: {color};">{icon} {alert['alert_type']} - TRUCK #{alert['truck_id']}</span>
                            <span style="color: {current_theme['text_muted']}; font-size: 0.8rem;">{alert['event_time'].strftime('%H:%M:%S')}</span>
                        </div>
                        <div style="font-size: 0.85rem; margin-top: 5px; color: {current_theme['text_main']};">
                            Driver: <b>{alert['driver_name']}</b> | 
                            Speed: <b>{alert['speed']:.1f} km/h</b> | 
                            Fuel: <b>{alert['fuel_level']:.1f}%</b> | 
                            Temp: <b>{alert['engine_temp']:.1f}°C</b>
                        </div>
                    </div>
                """, unsafe_allow_html=True)
        st.markdown("</div></div>", unsafe_allow_html=True)

        # Speed & Telemetry Analytics
        st.markdown(f"""
            <div class="glass-card">
                <div class="card-header">
                    <h3 style="color: {current_theme['text_main']};">⚡ Speed & Telemetry Analytics</h3>
                </div>
                <div class="card-body">
        """, unsafe_allow_html=True)
        top_n_speed = filtered_df.nlargest(truck_count_limit, 'speed').sort_values('speed', ascending=False)
        chart_font_color = "#000000" if st.session_state.theme_mode == "Light" else current_theme["text_main"]
        
        fig_speed = px.bar(
            top_n_speed, 
            x='truck_id', y='speed', 
            color='speed',
            color_continuous_scale="Blues" if st.session_state.theme_mode == "Dark" else "Viridis",
            title=f"Top {truck_count_limit} Fastest Trucks (Real-time)",
            labels={'speed': 'Speed (km/h)', 'truck_id': 'Truck ID'}
        )
        fig_speed.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", 
            plot_bgcolor="rgba(0,0,0,0)",
            font_color=chart_font_color,
            title_font_color=chart_font_color,
            height=300,
            margin=dict(t=50, b=0, l=0, r=0),
            xaxis={'type': 'category', 'tickfont': {'color': chart_font_color}},
            yaxis={'tickfont': {'color': chart_font_color}},
            coloraxis_colorbar={'tickfont': {'color': chart_font_color}}
        )
        st.plotly_chart(fig_speed, use_container_width=True)
        st.markdown("</div></div>", unsafe_allow_html=True)

        # Fuel Efficiency Analytics
        st.markdown(f"""
            <div class="glass-card">
                <div class="card-header">
                    <h3 style="color: {current_theme['text_main']};">⛽ Fuel Efficiency Analytics</h3>
                </div>
                <div class="card-body">
        """, unsafe_allow_html=True)
        # For fuel, we show the same top N speed trucks for cross-telemetry comparison
        fig_fuel = px.area(
            top_n_speed, 
            x='truck_id', y='fuel_level',
            title=f"Fuel Levels for Top {truck_count_limit} Speed Trucks",
            labels={'fuel_level': 'Fuel %', 'truck_id': 'Truck ID'}
        )
        fig_fuel.update_traces(
            fillcolor=hex_to_rgba(current_theme['primary'], 0.2), 
            line_color=current_theme["primary"]
        )
        fig_fuel.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", 
            plot_bgcolor="rgba(0,0,0,0)",
            font_color=chart_font_color,
            title_font_color=chart_font_color,
            height=300,
            margin=dict(t=50, b=0, l=0, r=0),
            xaxis={'type': 'category', 'tickfont': {'color': chart_font_color}},
            yaxis={'tickfont': {'color': chart_font_color}}
        )
        st.plotly_chart(fig_fuel, use_container_width=True)
        st.markdown("</div></div>", unsafe_allow_html=True)

        # Engine Health Analytics
        st.markdown(f"""
            <div class="glass-card">
                <div class="card-header">
                    <h3 style="color: {current_theme['text_main']};">🌡️ Engine Health Analytics</h3>
                </div>
                <div class="card-body">
        """, unsafe_allow_html=True)
        top_n_temp = filtered_df.nlargest(truck_count_limit, 'engine_temp').sort_values('engine_temp', ascending=False)
        fig_temp = px.bar(
            top_n_temp, 
            x='truck_id', y='engine_temp', 
            color='engine_temp',
            color_continuous_scale="Reds",
            title=f"Top {truck_count_limit} Highest Engine Temperatures",
            labels={'engine_temp': 'Temperature (°C)', 'truck_id': 'Truck ID'}
        )
        fig_temp.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", 
            plot_bgcolor="rgba(0,0,0,0)",
            font_color=chart_font_color,
            title_font_color=chart_font_color,
            height=300,
            margin=dict(t=50, b=0, l=0, r=0),
            xaxis={'type': 'category', 'tickfont': {'color': chart_font_color}},
            yaxis={'tickfont': {'color': chart_font_color}},
            coloraxis_colorbar={'tickfont': {'color': chart_font_color}}
        )
        st.plotly_chart(fig_temp, use_container_width=True)
        st.markdown("</div></div>", unsafe_allow_html=True)

        # Live Telemetry Stream Table
        st.markdown(f"""
            <div class="glass-card">
                <div class="card-header">
                    <h3 style="color: {current_theme['text_main']};">🛰️ Live Telemetry Stream</h3>
                </div>
                <div class="card-body">
        """, unsafe_allow_html=True)
        
        display_cols = ['truck_id', 'driver_name', 'speed', 'fuel_level', 'engine_temp', 'event_time', 'alert_type']
        st.dataframe(
            filtered_df[display_cols].sort_values('event_time', ascending=False),
            column_config={
                "truck_id": "Truck ID",
                "driver_name": "Driver",
                "speed": st.column_config.NumberColumn("Speed (km/h)", format="%.1f"),
                "fuel_level": st.column_config.ProgressColumn("Fuel %", min_value=0, max_value=100, format="%.1f%%"),
                "engine_temp": st.column_config.NumberColumn("Temp (°C)", format="%.1f"),
                "event_time": st.column_config.DatetimeColumn("Event Time", format="HH:mm:ss"),
                "alert_type": "Alert Status"
            },
            hide_index=True,
            use_container_width=True
        )
        st.markdown("</div></div>", unsafe_allow_html=True)

    with col_right:
        # Alert Distribution
        st.markdown(f"""
            <div class="glass-card">
                <div class="card-header">
                    <h4 style="color: {current_theme['text_main']};">🥯 Alert Distribution</h4>
                </div>
                <div class="card-body">
        """, unsafe_allow_html=True)
        
        if not filtered_df[filtered_df['is_alert']].empty:
            alert_counts = filtered_df[filtered_df['is_alert']]['alert_type'].value_counts().reset_index()
            alert_counts.columns = ['type', 'count']
            
            fig_pie = px.pie(
                alert_counts, 
                values='count', names='type',
                hole=0.6,
                color='type',
                color_discrete_map=ALERT_COLORS
            )
            fig_pie.update_layout(
                showlegend=False,
                margin=dict(t=0, b=0, l=0, r=0),
                height=250,
                paper_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig_pie, use_container_width=True)
        else:
            st.info("No alerts to visualize.")
        st.markdown("</div></div>", unsafe_allow_html=True)

        # Maintenance Status
        st.markdown(f"""
            <div class="glass-card">
                <div class="card-header">
                    <h4 style="color: {current_theme['text_main']};">🛠️ Maintenance Center</h4>
                </div>
                <div class="card-body">
        """, unsafe_allow_html=True)
        
        maint_df = filtered_df[filtered_df['in_maintenance'] == True]
        if maint_df.empty:
            st.success("All trucks in this selection are operational.")
        else:
            st.warning(f"{len(maint_df)} trucks currently in maintenance.")
            for _, row in maint_df.iterrows():
                st.markdown(f"""
                    <div style="font-size: 0.85rem; padding: 8px; border-bottom: 1px solid {current_theme['border']}; color: {current_theme['text_main']};">
                        <b>Truck #{row['truck_id']}</b>: {row['maintenance_type'] or 'Routine Check'}<br>
                        <span style="color: {current_theme['text_muted']}; font-size: 0.75rem;">Status: Service in progress</span>
                    </div>
                """, unsafe_allow_html=True)
        st.markdown("</div></div>", unsafe_allow_html=True)

else:
    st.warning("🚀 Waiting for live telemetry stream... Ensure the simulators and speed layer are running.")
    st.markdown(f"""
        <div style="text-align: center; padding: 50px;">
            <div class="live-dot" style="height: 50px; width: 50px;"></div>
            <p style="margin-top: 20px; color: {current_theme['text_muted']};">Connecting to fleet mesh network...</p>
        </div>
    """, unsafe_allow_html=True)

# ── Auto-Refresh Logic ────────────────────────────────────────────────────────
time.sleep(5)
st.rerun()
