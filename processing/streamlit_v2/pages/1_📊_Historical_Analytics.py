import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import time

from utils.cassandra_client import query_df
from utils.styles import get_css, THEMES, ALERT_COLORS, ALERT_ICONS, get_alert_style, hex_to_rgba

# ── Page Config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="FleetPulse | Historical Intelligence",
    page_icon="📊",
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
@st.cache_data(ttl=600) # Longer TTL for batch data
def get_batch_data():
    try:
        # Load batch stats
        df_batch = query_df("SELECT * FROM batch_daily_truck_stats")
        # Load drivers for mapping
        df_drivers = query_df("SELECT * FROM drivers")
        
        if df_batch.empty:
            return pd.DataFrame(), pd.DataFrame()
        
        # Convert stat_date (text) to datetime
        df_batch['date'] = pd.to_datetime(df_batch['stat_date'])
        
        # LINK DRIVERS USING THE NEW HISTORICAL driver_id COLUMN
        if not df_drivers.empty:
            # Create a simple ID -> Name mapping from the registry
            name_mapping = dict(zip(df_drivers['driver_id'], df_drivers['name']))
            # Apply mapping to the historical batch data
            df_batch['driver_name'] = df_batch['driver_id'].map(name_mapping).fillna(df_batch['driver_id']).fillna("Unknown Driver")
        else:
            df_batch['driver_name'] = df_batch['driver_id'].fillna("Unknown Driver")
        
        # ENFORCE NUMERIC TYPES
        numeric_cols = [
            'total_distance_km', 'total_fuel_consumed_l', 'fuel_per_100km', 
            'avg_speed_kmh', 'max_speed_kmh', 'total_alerts', 
            'overspeed_count', 'overheat_count', 'fuel_theft_count', 
            'low_fuel_count', 'event_count', 'hours_driven', 'hours_stopped'
        ]
        for col in numeric_cols:
            if col in df_batch.columns:
                df_batch[col] = pd.to_numeric(df_batch[col], errors='coerce').fillna(0)
            
        return df_batch, df_drivers
    except Exception as e:
        st.error(f"Error loading batch data: {e}")
        return pd.DataFrame(), pd.DataFrame()

# ── Helper Components ─────────────────────────────────────────────────────────
def render_executive_kpis(kpi_data):
    """Render all KPIs in a single responsive CSS grid."""
    kpi_items = []
    
    for kpi in kpi_data:
        label = kpi.get("label", "")
        value = kpi.get("value", "")
        sub_value = kpi.get("sub_value", "")
        icon = kpi.get("icon", "📊")
        trend = kpi.get("trend")
        
        trend_html = ""
        if trend is not None:
            trend_class = "trend-up" if trend >= 0 else "trend-down"
            trend_icon = "↑" if trend >= 0 else "↓"
            trend_html = f'<div class="trend-indicator {trend_class}" style="font-size: 0.8rem; margin-top: 8px;">{trend_icon} {abs(trend)}% vs prev</div>'
        
        sub_val_html = f'<div style="color: {current_theme["text_muted"]}; font-size: 0.8rem; margin-top: 4px;">{sub_value}</div>' if sub_value else ""
        label_color = "#000000" if st.session_state.theme_mode == 'Light' else current_theme['text_muted']

        # Construct single card without leading spaces to avoid markdown code blocks
        card_html = (
            f'<div class="metric-card">'
            f'<div style="display: flex; justify-content: space-between; align-items: flex-start;">'
            f'<div class="metric-label" style="color: {label_color}">{label}</div>'
            f'<div style="font-size: 1.2rem; opacity: 0.8;">{icon}</div>'
            f'</div>'
            f'<div>'
            f'<div class="metric-value" style="font-size: 1.8rem; margin: 4px 0;">{value}</div>'
            f'{trend_html}'
            f'{sub_val_html}'
            f'</div>'
            f'</div>'
        )
        kpi_items.append(card_html)
    
    # Wrap all items in grid
    full_html = f'<div class="kpi-grid">{"".join(kpi_items)}</div>'
    st.markdown(full_html, unsafe_allow_html=True)

# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"""
        <div style="text-align: left; padding: 0.5rem 0;">
            <div class="sidebar-title">📊 FleetPulse</div>
            <div class="sidebar-subtitle">Historical Intelligence</div>
        </div>
    """, unsafe_allow_html=True)
    
    st.markdown('<div class="sidebar-section-header">Executive Theme</div>', unsafe_allow_html=True)
    
    # Theme Toggle
    is_dark = st.toggle("Dark Mode", value=(st.session_state.theme_mode == "Dark"), help="Switch between Enterprise Dark and Professional Light themes.")
    new_mode = "Dark" if is_dark else "Light"
    
    if new_mode != st.session_state.theme_mode:
        st.session_state.theme_mode = new_mode
        st.rerun()

    st.divider()
    st.markdown('<div class="sidebar-section-header">Analytics Filters</div>', unsafe_allow_html=True)
    
    batch_df, drivers_df = get_batch_data()
    
    if not batch_df.empty:
        # 1. Single Day Selector
        available_days = sorted(batch_df['date'].dt.date.unique(), reverse=True)
        selected_day = st.selectbox("Analysis Day", available_days)
        
        # 2. Exclusive Scope Selector
        filter_mode = st.radio(
            "Analysis Scope",
            ["Full Fleet", "Specific Truck", "Specific Driver"],
            index=0
        )
        
        selected_truck = None
        selected_driver = None
        
        if filter_mode == "Specific Truck":
            truck_list = sorted(batch_df[batch_df['date'].dt.date == selected_day]['truck_id'].unique().tolist())
            selected_truck = st.selectbox("Select Truck ID", truck_list)
        
        elif filter_mode == "Specific Driver":
            driver_list = sorted(batch_df[batch_df['date'].dt.date == selected_day]['driver_name'].unique().tolist())
            selected_driver = st.selectbox("Select Driver", driver_list)
            
        st.markdown('<div class="sidebar-section-header">View Settings</div>', unsafe_allow_html=True)
        truck_count_limit = st.slider("Trucks to Display", min_value=5, max_value=50, value=10, step=5)
        show_anomalies = st.toggle("Highlight Inefficiencies", value=True)
        
    else:
        st.info("No historical data found in cluster.")

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🔄 Refresh Data Warehouse", type="primary", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# ── Data Processing ──────────────────────────────────────────────────────────
if not batch_df.empty:
    # 1. Filter by selected day
    day_df = batch_df[batch_df['date'].dt.date == selected_day].copy()
    
    # 2. Create combined display label for all vehicle axes
    day_df['display_label'] = day_df.apply(lambda x: f"Truck #{x['truck_id']} ({x['driver_name']})", axis=1)
    
    # 3. Determine the GLOBAL SUBSET based on Filter Mode and Display Limit
    if filter_mode == "Specific Truck" and selected_truck:
        # Just this one truck
        filtered_df = day_df[day_df['truck_id'] == selected_truck]
        associated_driver = filtered_df['driver_name'].iloc[0] if not filtered_df.empty else "Unknown"
        scope_label = f"Truck #{selected_truck} (Driver: {associated_driver})"
    
    elif filter_mode == "Specific Driver" and selected_driver:
        # Just this one driver (might be multiple trucks if they switched, but usually 1)
        filtered_df = day_df[day_df['driver_name'] == selected_driver]
        scope_label = f"Driver: {selected_driver}"
    
    else:
        # Full Fleet mode: Order by Truck ID and apply Display Limit globally
        all_truck_ids = sorted(day_df['truck_id'].unique())
        subset_truck_ids = all_truck_ids[:truck_count_limit]
        filtered_df = day_df[day_df['truck_id'].isin(subset_truck_ids)].sort_values('truck_id')
        scope_label = f"Full Fleet (Limited to {len(subset_truck_ids)} vehicles)"

    # All visualizations will now use 'filtered_df' for total consistency
    global_subset_df = filtered_df 

    # ── Header ──────────────────────────────────────────────────────────────────
    st.markdown(f"""
        <h1 style="margin-bottom: 0; color: {current_theme['text_main']};">Executive Fleet Intelligence</h1>
        <p style="color: {current_theme['text_muted']}; font-size: 1.1rem;">Analysis for <b>{selected_day}</b> | Scope: <b>{scope_label}</b></p>
    """, unsafe_allow_html=True)
    
    # ── Executive KPI Section ───────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    
    total_dist = filtered_df['total_distance_km'].sum()
    total_fuel = filtered_df['total_fuel_consumed_l'].sum()
    avg_eff = filtered_df['fuel_per_100km'].mean()
    total_alerts = filtered_df['total_alerts'].sum()
    total_overspeed = filtered_df['overspeed_count'].sum()
    total_theft = filtered_df['fuel_theft_count'].sum()
    avg_speed = filtered_df['avg_speed_kmh'].mean()
    total_hours = filtered_df['hours_driven'].sum()
    total_stop_hours = filtered_df['hours_stopped'].sum()

    kpi_data = [
        {"label": "Total Distance", "value": f"{total_dist:,.0f} km", "icon": "🛣️", "trend": 5},
        {"label": "Fuel Consumed", "value": f"{total_fuel:,.0f} L", "icon": "⛽", "trend": -2},
        {"label": "Avg Efficiency", "value": f"{avg_eff:.1f} L/100km", "icon": "📉", "trend": 1},
        {"label": "Total Incidents", "value": f"{total_alerts:,.0f}", "icon": "🚨", "trend": -12},
        {"label": "Overspeed Events", "value": f"{total_overspeed:,.0f}", "icon": "⚡", "trend": -8},
        {"label": "Fuel Loss Detects", "value": f"{total_theft:,.0f}", "icon": "🕵️", "trend": 0},
        {"label": "Avg Fleet Speed", "value": f"{avg_speed:.1f} km/h", "icon": "🚀", "trend": 2},
        {"label": "Operational Hours", "value": f"{total_hours:,.0f}h / {total_stop_hours:,.0f}h", "icon": "⏱️", "sub_value": "Driven / Idle Ratio"},
    ]
    
    render_executive_kpis(kpi_data)

    st.markdown("<br><br>", unsafe_allow_html=True)

    # ── Main Analytics Grid ─────────────────────────────────────────────────────
    chart_font_color = "#000000" if st.session_state.theme_mode == "Light" else current_theme["text_main"]
    
    # PERFORMANCE ROW 1: Distance & Speed
    p_row1_col1, p_row1_col2 = st.columns(2)
    
    with p_row1_col1:
        # 1. Distance Analytics
        st.markdown(f"""
            <div class="glass-card">
                <div class="card-header">
                    <h3 style="color: {current_theme['text_main']};">🛣️ Fleet Distance by Truck</h3>
                </div>
                <div class="card-body">
        """, unsafe_allow_html=True)
        # Using GLOBAL SUBSET ordered by Distance for this specific chart's leaderboard
        fig_dist_truck = px.bar(global_subset_df.sort_values('total_distance_km', ascending=True), 
                               y='display_label', x='total_distance_km',
                               orientation='h',
                               title=f"Distance Performance (Fleet Subset)",
                               color='total_distance_km', color_continuous_scale="Purples",
                               labels={'display_label': 'Vehicle & Driver', 'total_distance_km': 'Distance (km)'})
        fig_dist_truck.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color=chart_font_color, height=350, margin=dict(t=50, b=0, l=0, r=0), yaxis={'type': 'category'})
        st.plotly_chart(fig_dist_truck, use_container_width=True)
        st.markdown("</div></div>", unsafe_allow_html=True)

    with p_row1_col2:
        # 2. Average Speed Analytics
        st.markdown(f"""
            <div class="glass-card">
                <div class="card-header">
                    <h3 style="color: {current_theme['text_main']};">🚀 Average Speed by Truck</h3>
                </div>
                <div class="card-body">
        """, unsafe_allow_html=True)
        # Using GLOBAL SUBSET ordered by Speed
        fig_speed_truck = px.bar(global_subset_df.sort_values('avg_speed_kmh', ascending=True), 
                                y='display_label', x='avg_speed_kmh',
                                orientation='h',
                                title=f"Speed Rating (Fleet Subset)",
                                color='avg_speed_kmh', color_continuous_scale="Blues",
                                labels={'display_label': 'Vehicle & Driver', 'avg_speed_kmh': 'Avg Speed (km/h)'})
        fig_speed_truck.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color=chart_font_color, height=350, margin=dict(t=50, b=0, l=0, r=0), yaxis={'type': 'category'})
        st.plotly_chart(fig_speed_truck, use_container_width=True)
        st.markdown("</div></div>", unsafe_allow_html=True)

    # PERFORMANCE ROW 2: Activity & Utilization
    p_row2_col1, p_row2_col2 = st.columns(2)
    
    with p_row2_col1:
        # 3. Operational Activity
        st.markdown(f"""
            <div class="glass-card">
                <div class="card-header">
                    <h3 style="color: {current_theme['text_main']};">🕹️ Total Operational Activity</h3>
                </div>
                <div class="card-body">
        """, unsafe_allow_html=True)
        activity_col = 'event_count'
        if global_subset_df['event_count'].sum() == 0:
            activity_col = 'total_alerts'
            st.caption("ℹ️ Displaying Activity via Alerts (Raw Events data unavailable)")
            
        # Using GLOBAL SUBSET
        fig_act = px.bar(global_subset_df.sort_values(activity_col, ascending=True), 
                        y='display_label', x=activity_col,
                        orientation='h',
                        title=f"Activity Volume (Fleet Subset)",
                        color=activity_col, color_continuous_scale="GnBu",
                        labels={'display_label': 'Vehicle & Driver', activity_col: 'Volume'})
        fig_act.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color=chart_font_color, height=350, margin=dict(t=50, b=0, l=0, r=0), yaxis={'type': 'category'})
        st.plotly_chart(fig_act, use_container_width=True)
        st.markdown("</div></div>", unsafe_allow_html=True)

    with p_row2_col2:
        # 4. Utilization Detail
        st.markdown(f"""
            <div class="glass-card">
                <div class="card-header">
                    <h3 style="color: {current_theme['text_main']};">⏱️ Driving vs Stopped Hours</h3>
                </div>
                <div class="card-body">
        """, unsafe_allow_html=True)
        # Using GLOBAL SUBSET
        util_melted = global_subset_df.sort_values('hours_driven', ascending=True).melt(
            id_vars='display_label', value_vars=['hours_driven', 'hours_stopped'], 
            var_name='Status', value_name='Hours'
        )
        
        fig_util_detail = px.bar(util_melted, y='display_label', x='Hours', color='Status', 
                                title=f"Time Allocation (Fleet Subset)",
                                orientation='h',
                                barmode='stack',
                                color_discrete_map={'hours_driven': current_theme['success'], 'hours_stopped': current_theme['text_muted']},
                                labels={'display_label': 'Vehicle & Driver'})
        fig_util_detail.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color=chart_font_color, height=350, margin=dict(t=50, b=0, l=0, r=0), yaxis={'type': 'category'})
        st.plotly_chart(fig_util_detail, use_container_width=True)
        st.markdown("</div></div>", unsafe_allow_html=True)

    # ── FUEL ANALYTICS CENTER ─────────────────────────────────────────────────
    st.markdown(f"""
        <div class="glass-card">
            <div class="card-header">
                <h3 style="color: {current_theme['text_main']};">⛽ FUEL ANALYTICS CENTER</h3>
            </div>
            <div class="card-body">
    """, unsafe_allow_html=True)
    
    f_row1_col1, f_row1_col2 = st.columns(2)
    
    with f_row1_col1:
        # 1. Total Consumption (Using GLOBAL SUBSET)
        fig_cons = px.bar(global_subset_df.sort_values('total_fuel_consumed_l', ascending=True), 
                         x='total_fuel_consumed_l', y='display_label', orientation='h',
                         title="Fuel Consumed (Liters)",
                         color='total_fuel_consumed_l', color_continuous_scale="YlOrRd",
                         labels={'display_label': 'Vehicle', 'total_fuel_consumed_l': 'Liters'})
        fig_cons.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color=chart_font_color, height=350, margin=dict(t=50, b=0, l=0, r=0), yaxis={'type': 'category'})
        st.plotly_chart(fig_cons, use_container_width=True)

    with f_row1_col2:
        # 2. Fuel Efficiency (L/100km) (Using GLOBAL SUBSET)
        fig_eff_all = px.bar(global_subset_df.sort_values('fuel_per_100km', ascending=False), 
                            x='fuel_per_100km', y='display_label', orientation='h',
                            title="Fuel Efficiency Ranking (L/100km)",
                            color='fuel_per_100km', color_continuous_scale="RdYlGn_r",
                            labels={'display_label': 'Vehicle', 'fuel_per_100km': 'Efficiency'})
        fig_eff_all.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color=chart_font_color, height=350, margin=dict(t=50, b=0, l=0, r=0), yaxis={'type': 'category'})
        st.plotly_chart(fig_eff_all, use_container_width=True)

    st.divider()
    f_row2_col1, f_row2_col2 = st.columns(2)

    with f_row2_col1:
        # 3. Fuel Theft Analysis (Using GLOBAL SUBSET)
        fig_theft = px.bar(global_subset_df.sort_values('fuel_theft_count', ascending=True), 
                          x='fuel_theft_count', y='display_label', orientation='h',
                          title="Fuel Theft / Leak Incidents",
                          color='fuel_theft_count', color_continuous_scale="Reds",
                          labels={'display_label': 'Vehicle', 'fuel_theft_count': 'Incidents'})
        fig_theft.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color=chart_font_color, height=350, margin=dict(t=50, b=0, l=0, r=0), yaxis={'type': 'category'})
        st.plotly_chart(fig_theft, use_container_width=True)

    with f_row2_col2:
        # 4. Low Fuel Analysis (Using GLOBAL SUBSET)
        fig_low = px.bar(global_subset_df.sort_values('low_fuel_count', ascending=True), 
                        x='low_fuel_count', y='display_label', orientation='h',
                        title="Critical Low Fuel Events",
                        color='low_fuel_count', color_continuous_scale="Oranges",
                        labels={'display_label': 'Vehicle', 'low_fuel_count': 'Alerts'})
        fig_low.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color=chart_font_color, height=350, margin=dict(t=50, b=0, l=0, r=0), yaxis={'type': 'category'})
        st.plotly_chart(fig_low, use_container_width=True)

    st.markdown("</div></div>", unsafe_allow_html=True)

    # ── Secondary Grid (Risk & Alerts) ────────────────────────────────────────
    col_left, col_right = st.columns([2, 1])

    with col_left:
        st.markdown(f"""
            <div class="glass-card">
                <div class="card-header">
                    <h3 style="color: {current_theme['text_main']};">🚨 Incident Intelligence</h3>
                </div>
                <div class="card-body">
        """, unsafe_allow_html=True)
        
        behavior_metrics = ['overspeed_count', 'overheat_count', 'fuel_theft_count', 'low_fuel_count']
        # Using GLOBAL SUBSET for the Incident Breakdown
        incident_dist = global_subset_df.melt(id_vars='display_label', value_vars=behavior_metrics, 
                                            var_name='Alert Type', value_name='Count')
        
        fig_inc_all = px.bar(incident_dist, x='Count', y='display_label', color='Alert Type',
                            title="Total Incident Breakdown (Fleet Subset)",
                            barmode='group',
                            color_discrete_sequence=px.colors.qualitative.Pastel)
        fig_inc_all.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color=chart_font_color, height=450, margin=dict(t=50, b=0, l=0, r=0), yaxis={'type': 'category'})
        st.plotly_chart(fig_inc_all, use_container_width=True)
        st.markdown("</div></div>", unsafe_allow_html=True)

    with col_right:
        # Risk Ranking
        st.markdown(f"""
            <div class="glass-card">
                <div class="card-header">
                    <h4 style="color: {current_theme['text_main']};">🚩 High-Risk Profiles</h4>
                </div>
                <div class="card-body">
        """, unsafe_allow_html=True)
        risk_df = filtered_df.sort_values('total_alerts', ascending=False).head(5)
        for _, row in risk_df.iterrows():
            st.markdown(f"""
                <div style="display: flex; justify-content: space-between; padding: 12px 0; border-bottom: 1px solid {current_theme['border']};">
                    <div>
                        <div style="font-weight: 600;">Truck #{row['truck_id']}</div>
                        <div style="font-size: 0.75rem; color: {current_theme['text_muted']};">{row['driver_name']}</div>
                    </div>
                    <div style="text-align: right;">
                        <span style="color: {current_theme['danger']}; font-weight: 700;">{row['total_alerts']} Alerts</span>
                        <div style="font-size: 0.7rem; color: {current_theme['text_muted']};">{row['overspeed_count']} Overspeeds</div>
                    </div>
                </div>
            """, unsafe_allow_html=True)
        st.markdown("</div></div>", unsafe_allow_html=True)

        # Incident Trends (Distribution for the day)
        st.markdown(f"""
            <div class="glass-card">
                <div class="card-header">
                    <h4 style="color: {current_theme['text_main']};">🥯 Alert Mix</h4>
                </div>
                <div class="card-body">
        """, unsafe_allow_html=True)
        
        behavior_sums = filtered_df[behavior_metrics].sum()
        fig_pie = px.pie(
            values=behavior_sums.values, 
            names=['Overspeed', 'Overheat', 'Theft', 'Low Fuel'],
            hole=0.6,
            color_discrete_sequence=px.colors.sequential.Tealgrn_r
        )
        fig_pie.update_layout(showlegend=False, margin=dict(t=0, b=0, l=0, r=0), height=250, paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig_pie, use_container_width=True)
        st.markdown("</div></div>", unsafe_allow_html=True)

else:
    st.warning("⚠️ No historical batch data found. Please run the analytics layer or ensure the Cassandra migrations V4/V5 are applied.")
    st.markdown("""
        <div style="text-align: center; padding: 50px;">
            <div style="font-size: 4rem; opacity: 0.2;">📂</div>
            <p style="margin-top: 20px; color: #8892b0;">Waiting for data warehouse population...</p>
        </div>
    """, unsafe_allow_html=True)
