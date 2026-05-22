import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import time

from utils.cassandra_client import query_df
from utils.styles import get_css, THEMES, hex_to_rgba

# ── Page Config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="FleetPulse | Maintenance Intelligence",
    page_icon="🔧",
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
@st.cache_data(ttl=600)
def get_maintenance_data():
    try:
        # Load maintenance flags
        df_maint = query_df("SELECT * FROM batch_maintenance_flags")
        # Load drivers for mapping
        df_drivers = query_df("SELECT * FROM drivers")
        
        if df_maint.empty:
            return pd.DataFrame()
            
        df_maint['date'] = pd.to_datetime(df_maint['stat_date'])
        
        # Link drivers
        if not df_drivers.empty:
            name_mapping = dict(zip(df_drivers['driver_id'], df_drivers['name']))
            df_maint['driver_name'] = df_maint['driver_id'].map(name_mapping).fillna(df_maint['driver_id']).fillna("Unknown Driver")
        else:
            df_maint['driver_name'] = df_maint['driver_id'].fillna("Unknown Driver")
            
        # Create combined display label
        df_maint['display_label'] = df_maint.apply(lambda x: f"Truck #{x['truck_id']} ({x['driver_name']})", axis=1)

        # Enforce numeric types
        num_cols = [
            'avg_engine_temp', 'max_engine_temp', 'max_odometer_km',
            'avg_fuel_rate', 'fuel_rate_stddev', 'overheat_count',
            'theft_count', 'event_count'
        ]
        for col in num_cols:
            if col in df_maint.columns:
                df_maint[col] = pd.to_numeric(df_maint[col], errors='coerce').fillna(0)
                
        return df_maint
    except Exception as e:
        st.error(f"Error loading maintenance data: {e}")
        return pd.DataFrame()

# ── Helper Components ─────────────────────────────────────────────────────────
def render_ai_kpis(kpi_data):
    """Render high-tech maintenance KPIs."""
    kpi_items = []
    for kpi in kpi_data:
        label = kpi.get("label", "")
        value = kpi.get("value", "")
        status_color = kpi.get("color", current_theme['primary'])
        icon = kpi.get("icon", "🤖")
        
        card_html = (
            f'<div class="metric-card" style="border-top: 3px solid {status_color};">'
            f'<div style="display: flex; justify-content: space-between; align-items: flex-start;">'
            f'<div class="metric-label" style="color: {st.session_state.theme_mode == "Light" and "#000000" or current_theme["text_muted"]}">{label}</div>'
            f'<div style="font-size: 1.2rem; filter: drop-shadow(0 0 5px {status_color}55);">{icon}</div>'
            f'</div>'
            f'<div>'
            f'<div class="metric-value" style="font-size: 1.8rem; margin: 4px 0; color: {status_color if st.session_state.theme_mode == "Dark" else "#000000"}">{value}</div>'
            f'</div>'
            f'</div>'
        )
        kpi_items.append(card_html)
    
    full_html = f'<div class="kpi-grid">{"".join(kpi_items)}</div>'
    st.markdown(full_html, unsafe_allow_html=True)

# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"""
        <div style="text-align: left; padding: 0.5rem 0;">
            <div class="sidebar-title">🔧 Maintenance</div>
            <div class="sidebar-subtitle">Intelligence Center</div>
        </div>
    """, unsafe_allow_html=True)
    
    st.markdown('<div class="sidebar-section-header">Executive Theme</div>', unsafe_allow_html=True)
    is_dark = st.toggle("Dark Mode", value=(st.session_state.theme_mode == "Dark"))
    new_mode = "Dark" if is_dark else "Light"
    if new_mode != st.session_state.theme_mode:
        st.session_state.theme_mode = new_mode
        st.rerun()

    st.divider()
    st.markdown('<div class="sidebar-section-header">Health Filters</div>', unsafe_allow_html=True)
    
    raw_df = get_maintenance_data()
    
    if not raw_df.empty:
        available_days = sorted(raw_df['date'].dt.date.unique(), reverse=True)
        selected_day = st.selectbox("Analysis Epoch", available_days)
        
        day_df = raw_df[raw_df['date'].dt.date == selected_day].copy()
        
        truck_list = ["Full Fleet View"] + sorted(day_df['truck_id'].unique().tolist())
        selected_truck = st.selectbox("Select Truck ID", truck_list)
        
        st.markdown('<div class="sidebar-section-header">View Settings</div>', unsafe_allow_html=True)
        truck_count_limit = st.slider("Trucks to Display", min_value=5, max_value=50, value=10, step=5)
    else:
        st.info("Awaiting maintenance audit logs...")

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🔄 Force Audit Refresh", type="primary", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# ── Data Processing ──────────────────────────────────────────────────────────
if not raw_df.empty:
    # 1. Scope Filtering
    if selected_truck == "Full Fleet View":
        # Apply Display Limit globally for Full Fleet
        all_truck_ids = sorted(day_df['truck_id'].unique())
        subset_truck_ids = all_truck_ids[:truck_count_limit]
        filtered_df = day_df[day_df['truck_id'].isin(subset_truck_ids)].sort_values('truck_id')
        scope_title = f"Fleet Health Matrix (Limited to {len(subset_truck_ids)} units)"
    else:
        filtered_df = day_df[day_df['truck_id'] == selected_truck]
        scope_title = f"Diagnostic: Truck #{selected_truck}"

    # Calculate Aggregates (using only the filtered subset)
    needing_maint = filtered_df[filtered_df['maintenance_needed'] == True]
    high_priority = filtered_df[filtered_df['priority'] == 'HIGH']
    avg_temp = filtered_df['avg_engine_temp'].mean()
    total_overheats = filtered_df['overheat_count'].sum()
    fuel_anomalies = filtered_df[filtered_df['flag_fuel_inconsistency'] == True]
    odometer_milestones = filtered_df[filtered_df['flag_odometer_milestone'] == True]
    
    # AI Health Score (Simplified inverse of risk)
    maint_ratio = len(needing_maint) / len(filtered_df) if len(filtered_df) > 0 else 0
    health_score = max(0, 100 - (maint_ratio * 100) - (len(high_priority) * 5))
    
    # ── Executive Header ──────────────────────────────────────────────────────
    col_t, col_s = st.columns([3, 1])
    with col_t:
        st.markdown(f"""
            <h1 style="margin-bottom: 0;">Predictive Maintenance Intelligence</h1>
            <p style="color: {current_theme['text_muted']}; font-size: 1.1rem;">AI-Driven Risk Detection & Fleet Health Analysis</p>
        """, unsafe_allow_html=True)
    
    with col_s:
        status_color = current_theme['success'] if health_score > 85 else (current_theme['warning'] if health_score > 60 else current_theme['danger'])
        st.markdown(f"""
            <div class="glass-card" style="padding: 15px; text-align: center; margin-bottom: 0;">
                <div style="color: {status_color}; font-weight: 800; font-size: 1rem; letter-spacing: 1px;">
                    {'🟢 FLEET OPTIMAL' if health_score > 85 else ('🟠 RISK DETECTED' if health_score > 60 else '🔴 CRITICAL FAILURE RISK')}
                </div>
                <div style="font-size: 0.7rem; color: {current_theme['text_muted']}; margin-top: 5px;">
                    HEALTH SCORE: {health_score:.1f}%
                </div>
            </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    
    # ── KPI Section ───────────────────────────────────────────────────────────
    kpis = [
        {"label": "Maintenance Needed", "value": len(needing_maint), "icon": "🛠️", "color": current_theme['warning']},
        {"label": "High Priority", "value": len(high_priority), "icon": "⚠️", "color": current_theme['danger']},
        {"label": "Avg Fleet Temp", "value": f"{avg_temp:.1f}°C", "icon": "🌡️"},
        {"label": "Overheat Alerts", "value": int(total_overheats), "icon": "🔥"},
        {"label": "Fuel Inconsistencies", "value": len(fuel_anomalies), "icon": "⛽"},
    ]
    render_ai_kpis(kpis)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Main Content Grid ─────────────────────────────────────────────────────
    col_left, col_right = st.columns([2, 1])

    with col_left:
        # 1. Thermal & Event Diagnostics Grid
        diag_row1_col1, diag_row1_col2 = st.columns(2)
        
        chart_font_color = "#000000" if st.session_state.theme_mode == "Light" else "#ffffff"

        with diag_row1_col1:
            st.markdown(f"""
                <div class="glass-card">
                    <div class="card-header"><h3>🌡️ Avg Engine Temp by Truck</h3></div>
                    <div class="card-body">
            """, unsafe_allow_html=True)
            df_avg_temp = filtered_df.sort_values('avg_engine_temp', ascending=True)
            fig_avg = px.bar(df_avg_temp, x='avg_engine_temp', y='display_label', orientation='h',
                            title="Avg Temperature Profile",
                            color='avg_engine_temp', color_continuous_scale="Reds",
                            labels={'display_label': 'Vehicle & Driver', 'avg_engine_temp': 'Avg Temp (°C)'})
            fig_avg.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color=chart_font_color, height=300, margin=dict(t=30, b=0, l=0, r=0), yaxis={'type': 'category'})
            st.plotly_chart(fig_avg, use_container_width=True)
            st.markdown("</div></div>", unsafe_allow_html=True)

        with diag_row1_col2:
            st.markdown(f"""
                <div class="glass-card">
                    <div class="card-header"><h3>🔥 Max Engine Temp by Truck</h3></div>
                    <div class="card-body">
            """, unsafe_allow_html=True)
            df_max_temp = filtered_df.sort_values('max_engine_temp', ascending=True)
            fig_max = px.bar(df_max_temp, x='max_engine_temp', y='display_label', orientation='h',
                            title="Max Temperature Reached",
                            color='max_engine_temp', color_continuous_scale="OrRd",
                            labels={'display_label': 'Vehicle & Driver', 'max_engine_temp': 'Max Temp (°C)'})
            fig_max.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color=chart_font_color, height=300, margin=dict(t=30, b=0, l=0, r=0), yaxis={'type': 'category'})
            st.plotly_chart(fig_max, use_container_width=True)
            st.markdown("</div></div>", unsafe_allow_html=True)

        diag_row2_col1, diag_row2_col2 = st.columns(2)

        with diag_row2_col1:
            st.markdown(f"""
                <div class="glass-card">
                    <div class="card-header"><h3>⚠️ Overheat Alerts by Truck</h3></div>
                    <div class="card-body">
            """, unsafe_allow_html=True)
            df_overheat = filtered_df.sort_values('overheat_count', ascending=True)
            fig_ovr = px.bar(df_overheat, x='overheat_count', y='display_label', orientation='h',
                            title="Critical Overheat Frequency",
                            color='overheat_count', color_continuous_scale="YlOrBr",
                            labels={'display_label': 'Vehicle & Driver', 'overheat_count': 'Alerts'})
            fig_ovr.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color=chart_font_color, height=300, margin=dict(t=30, b=0, l=0, r=0), yaxis={'type': 'category'})
            st.plotly_chart(fig_ovr, use_container_width=True)
            st.markdown("</div></div>", unsafe_allow_html=True)

        with diag_row2_col2:
            st.markdown(f"""
                <div class="glass-card">
                    <div class="card-header"><h3>🛠️ Maintenance Priority Matrix</h3></div>
                    <div class="card-body">
            """, unsafe_allow_html=True)
            # Map priority to numeric values for robust chart rendering
            prio_map = {'HIGH': 3, 'MEDIUM': 2, 'NORMAL': 1}
            df_priority = filtered_df.copy()
            df_priority['prio_weight'] = df_priority['priority'].map(prio_map)
            df_priority = df_priority.sort_values('prio_weight', ascending=True)
            
            fig_prio = px.bar(df_priority, x='prio_weight', y='display_label', orientation='h',
                             title="Priority Classification",
                             color='priority',
                             color_discrete_map={'HIGH': current_theme['danger'], 'MEDIUM': current_theme['warning'], 'NORMAL': current_theme['success']},
                             labels={'display_label': 'Vehicle & Driver', 'prio_weight': 'Severity'})
            
            fig_prio.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color=chart_font_color, 
                height=300, margin=dict(t=30, b=0, l=0, r=0), 
                yaxis={'type': 'category'},
                xaxis={'tickmode': 'array', 'tickvals': [1, 2, 3], 'ticktext': ['NORMAL', 'MEDIUM', 'HIGH']}
            )
            st.plotly_chart(fig_prio, use_container_width=True)
            st.markdown("</div></div>", unsafe_allow_html=True)

        # 2. Detailed Diagnostic Table
        st.markdown(f"""
            <div class="glass-card">
                <div class="card-header"><h3>📋 Critical Diagnostic Logs</h3></div>
                <div class="card-body">
        """, unsafe_allow_html=True)
        
        display_df = filtered_df.copy()
        display_df['priority_val'] = display_df['priority'].map({'HIGH': 3, 'MEDIUM': 2, 'NORMAL': 1})
        display_df = display_df.sort_values('priority_val', ascending=False)
        
        cols = ['truck_id', 'driver_name', 'priority', 'avg_engine_temp', 'max_odometer_km', 'fuel_rate_stddev']
        st.dataframe(
            display_df[cols],
            column_config={
                "truck_id": "Unit ID",
                "driver_name": "Driver",
                "priority": "Maintenance Priority",
                "avg_engine_temp": st.column_config.NumberColumn("Avg Temp", format="%.1f°C"),
                "max_odometer_km": st.column_config.NumberColumn("Odometer", format="%d km"),
                "fuel_rate_stddev": st.column_config.NumberColumn("Fuel Volatility", format="%.2f")
            },
            hide_index=True,
            use_container_width=True
        )
        st.markdown("</div></div>", unsafe_allow_html=True)

    with col_right:
        # 3. High Risk Units
        st.markdown(f"""
            <div class="glass-card">
                <div class="card-header"><h4>🚩 High-Risk Units</h4></div>
                <div class="card-body">
        """, unsafe_allow_html=True)
        
        if not high_priority.empty:
            for _, row in high_priority.head(5).iterrows():
                st.markdown(f"""
                    <div style="background: {current_theme['danger']}11; border: 1px solid {current_theme['danger']}33; border-radius: 8px; padding: 12px; margin-bottom: 10px;">
                        <div style="display: flex; justify-content: space-between; font-weight: 700;">
                            <span style="color: {current_theme['danger']};">TRUCK #{row['truck_id']}</span>
                            <span style="font-size: 0.7rem; opacity: 0.8;">{row['driver_name']}</span>
                        </div>
                        <div style="font-size: 0.75rem; margin-top: 5px; line-height: 1.4;">
                            • Temp: <b>{row['avg_engine_temp']:.1f}°C</b><br>
                            • Overheats: <b>{row['overheat_count']}</b><br>
                            • Odometer: <b>{row['max_odometer_km']:.0f} km</b>
                        </div>
                    </div>
                """, unsafe_allow_html=True)
        else:
            st.success("No units identified as HIGH risk for this period.")
        st.markdown("</div></div>", unsafe_allow_html=True)

        # 4. Maintenance Distribution
        st.markdown(f"""
            <div class="glass-card">
                <div class="card-header"><h4>📊 Priority Distribution</h4></div>
                <div class="card-body">
        """, unsafe_allow_html=True)
        
        p_counts = day_df['priority'].value_counts()
        fig_dist = px.pie(
            names=p_counts.index, 
            values=p_counts.values,
            hole=0.7,
            color=p_counts.index,
            color_discrete_map={'HIGH': current_theme['danger'], 'MEDIUM': current_theme['warning'], 'NORMAL': current_theme['success']}
        )
        fig_dist.update_layout(showlegend=False, height=200, margin=dict(t=0, b=0, l=0, r=0), paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig_dist, use_container_width=True)
        st.markdown("</div></div>", unsafe_allow_html=True)

else:
    st.warning("⚠️ No maintenance intelligence data found. Ensure the 'maintenance_prediction_dag' has been executed.")
    st.markdown("""
        <div style="text-align: center; padding: 50px;">
            <div style="font-size: 5rem; opacity: 0.1;">🔧</div>
            <p style="margin-top: 20px; color: #8892b0;">Scanning fleet for wear and tear signatures...</p>
        </div>
    """, unsafe_allow_html=True)
