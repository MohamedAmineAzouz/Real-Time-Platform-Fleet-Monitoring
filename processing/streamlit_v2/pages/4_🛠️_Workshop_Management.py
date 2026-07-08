import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import uuid
import io

from utils.cassandra_client import query_df
from utils.styles import get_css, THEMES, hex_to_rgba

# ── Page Config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="FleetPulse | Workshop Management",
    page_icon="🛠️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Theme Management ─────────────────────────────────────────────────────────
if 'theme_mode' not in st.session_state:
    st.session_state.theme_mode = "Dark"

st.markdown(get_css(st.session_state.theme_mode), unsafe_allow_html=True)
current_theme = THEMES[st.session_state.theme_mode]

# ── Data Loading ─────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def get_workshop_data():
    try:
        df = query_df("SELECT * FROM maintenance_schedules")
        if df.empty:
            return pd.DataFrame()
            
        # Standardize timestamps
        df['start'] = pd.to_datetime(df['scheduled_start'])
        df['end'] = pd.to_datetime(df['scheduled_end'])
        
        # Calculate derived durations
        df['duration_h'] = (df['end'] - df['start']).dt.total_seconds() / 3600
        
        # Enforce numeric types
        df['cost'] = pd.to_numeric(df['cost'], errors='coerce').fillna(0)
        
        # Determine Status
        now = datetime.now()
        def get_status(row):
            if row['end'] < now:
                return "Completed"
            elif row['start'] <= now <= row['end']:
                return "Active"
            else:
                return "Scheduled"
        
        df['op_status'] = df.apply(get_status, axis=1)
        
        return df
    except Exception as e:
        st.error(f"Error loading workshop ledger: {e}")
        return pd.DataFrame()

# ── Helper Components ─────────────────────────────────────────────────────────
def render_op_kpis(kpi_data):
    """Render operational KPIs in a responsive grid."""
    kpi_items = []
    for kpi in kpi_data:
        label = kpi.get("label")
        value = kpi.get("value")
        icon = kpi.get("icon")
        color = kpi.get("color", current_theme['primary'])
        
        label_color = "#000000" if st.session_state.theme_mode == 'Light' else current_theme['text_muted']
        card_html = (
            f'<div class="metric-card" style="border-top: 3px solid {color};">'
            f'<div style="display: flex; justify-content: space-between; align-items: flex-start;">'
            f'<div class="metric-label" style="color: {label_color}">{label}</div>'
            f'<div style="font-size: 1.1rem; opacity: 0.7;">{icon}</div>'
            f'</div>'
            f'<div>'
            f'<div class="metric-value" style="font-size: 1.6rem; color: {color if st.session_state.theme_mode == "Dark" else "#000000"}">{value}</div>'
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
            <div class="sidebar-title">🛠️ Workshop</div>
            <div class="sidebar-subtitle">Fleet Service Management</div>
        </div>
    """, unsafe_allow_html=True)
    
    st.markdown('<div class="sidebar-section-header">Executive Theme</div>', unsafe_allow_html=True)
    is_dark = st.toggle("Dark Mode", value=(st.session_state.theme_mode == "Dark"))
    if is_dark != (st.session_state.theme_mode == "Dark"):
        st.session_state.theme_mode = "Dark" if is_dark else "Light"
        st.rerun()

    st.divider()
    st.markdown('<div class="sidebar-section-header">Workshop Filters</div>', unsafe_allow_html=True)
    
    raw_df = get_workshop_data()
    
    if not raw_df.empty:
        # Date Range
        min_date = raw_df['start'].min().date()
        max_date = raw_df['end'].max().date()
        date_range = st.date_input("Service Period", value=(min_date, max_date), min_value=min_date, max_value=max_date)
        
        # Maint Type
        m_types = ["All Types"] + sorted(raw_df['maintenance_type'].unique().tolist())
        sel_type = st.selectbox("Maintenance Category", m_types)
        
        # Mechanic
        mechanics = ["All Mechanics"] + sorted(raw_df['assigned_mechanic'].unique().tolist())
        sel_mech = st.selectbox("Technician Assignment", mechanics)
        
        # Assets
        trucks = ["All Trucks"] + sorted(raw_df['truck_id'].unique().tolist())
        sel_truck = st.selectbox("Asset Search", trucks)
        
        st.markdown('<div class="sidebar-section-header">View Settings</div>', unsafe_allow_html=True)
        truck_count_limit = st.slider("Trucks to Display", min_value=5, max_value=50, value=10, step=5)
        
        st.markdown('<div class="sidebar-section-header">Status & Urgency</div>', unsafe_allow_html=True)
        show_active = st.checkbox("Active Operations", value=True)
        show_overdue = st.checkbox("Overdue Tasks", value=True)
    else:
        st.info("Awaiting workshop ledger...")

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🔄 Force Operations Refresh", type="primary", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# ── Data Processing ──────────────────────────────────────────────────────────
if not raw_df.empty:
    # 1. First filter by date range
    processed_df = raw_df.copy()
    if isinstance(date_range, tuple) and len(date_range) == 2:
        processed_df = processed_df[(processed_df['start'].dt.date >= date_range[0]) & (processed_df['start'].dt.date <= date_range[1])]
    
    # 2. ENFORCE GLOBAL TRUCK SUBSET CONSISTENCY
    if sel_truck != "All Trucks":
        subset_truck_ids = [sel_truck]
    else:
        all_avail_trucks = sorted(processed_df['truck_id'].unique())
        subset_truck_ids = all_avail_trucks[:truck_count_limit]
        
    # Apply subset
    filtered_df = processed_df[processed_df['truck_id'].isin(subset_truck_ids)].copy()
    
    # 3. Apply other filters
    if sel_type != "All Types":
        filtered_df = filtered_df[filtered_df['maintenance_type'] == sel_type]
    if sel_mech != "All Mechanics":
        filtered_df = filtered_df[filtered_df['assigned_mechanic'] == sel_mech]
    
    now = datetime.now()
    overdue_df = filtered_df[(filtered_df['end'] < now) & (filtered_df['op_status'] != 'Completed')]
    active_df = filtered_df[filtered_df['op_status'] == 'Active']
    upcoming_df = filtered_df[filtered_df['start'] > now]

    # ── Executive Header ──────────────────────────────────────────────────────
    col_h1, col_h2 = st.columns([3, 1])
    with col_h1:
        st.markdown(f"""
            <h1 style="margin-bottom: 0;">Workshop Operations & Scheduling</h1>
            <p style="color: #94a3b8; font-size: 1.1rem;">Enterprise Asset Lifecycle & Maintenance Management</p>
        """, unsafe_allow_html=True)
    with col_h2:
        downtime_risk = min(100, (len(active_df) * 5) + (len(overdue_df) * 15))
        risk_label = "STABLE" if downtime_risk < 30 else ("CONGESTED" if downtime_risk < 60 else "CRITICAL")
        risk_color = current_theme['success'] if downtime_risk < 30 else (current_theme['warning'] if downtime_risk < 60 else current_theme['danger'])
        st.markdown(f"""
            <div class="glass-card" style="padding: 15px; text-align: center; border-color: {risk_color}44;">
                <div style="color: {risk_color}; font-weight: 800; font-size: 0.9rem;">🛠️ {risk_label} OPERATIONS</div>
                <div style="font-size: 0.7rem; color: #94a3b8; margin-top: 5px;">DOWNTIME RISK INDEX: {downtime_risk:.1f}%</div>
            </div>
        """, unsafe_allow_html=True)

    # ── Executive KPIs ────────────────────────────────────────────────────────
    total_cost = filtered_df['cost'].sum()
    avg_dur = filtered_df['duration_h'].mean()
    util_rate = min(100, (len(active_df) / 10) * 100) # Assuming 10 bay capacity
    
    kpis = [
        {"label": "Total Scheduled", "value": f"{len(filtered_df)}", "icon": "📅"},
        {"label": "Active Tasks", "value": f"{len(active_df)}", "icon": "🔧", "color": current_theme['primary']},
        {"label": "Overdue Items", "value": f"{len(overdue_df)}", "icon": "⚠️", "color": current_theme['danger']},
        {"label": "Upcoming", "value": f"{len(upcoming_df)}", "icon": "⏭️", "color": current_theme['success']},
        {"label": "Total Ops Cost", "value": f"{total_cost:,.0f} MAD", "icon": "💰"},
        {"label": "Avg Duration", "value": f"{avg_dur:.1f} h", "icon": "⏱️"},
        {"label": "Workshop Load", "value": f"{util_rate:.1f}%", "icon": "🏭"},
        {"label": "Downtime Hours", "value": f"{filtered_df['duration_h'].sum():,.0f}h", "icon": "🛑", "color": current_theme['warning']},
    ]
    render_op_kpis(kpis)

    st.markdown("<br>", unsafe_allow_html=True)
    chart_font_color = "#000000" if st.session_state.theme_mode == "Light" else "#ffffff"

    # ── MAINTENANCE CALENDAR & TIMELINE ───────────────────────────────────────
    st.markdown('<div class="glass-card"><div class="card-header"><h3>🗓️ Fleet Workshop Planning Board</h3></div><div class="card-body">', unsafe_allow_html=True)
    
    if not filtered_df.empty:
        # Construct Professional Planning Board
        timeline_df = filtered_df.copy()
        timeline_df['truck_label'] = timeline_df.apply(lambda x: f"Truck #{x['truck_id']}", axis=1)
        # Combined label for the bar text
        timeline_df['bar_text'] = timeline_df['maintenance_type'] + " | " + timeline_df['assigned_mechanic']
        
        fig_timeline = px.timeline(
            timeline_df, 
            x_start="start", x_end="end", 
            y="truck_label", color="maintenance_type",
            text="bar_text",
            hover_data=["description", "cost"],
            color_discrete_sequence=px.colors.qualitative.Prism
        )
        
        # Professional Industrial Styling
        fig_timeline.update_traces(
            textposition='inside', 
            insidetextanchor='middle',
            marker_line_width=1,
            marker_line_color="rgba(255,255,255,0.1)",
            opacity=0.9
        )
        
        now = datetime.now()
        fig_timeline.add_vline(x=now, line_width=2, line_dash="dash", line_color=current_theme['accent'])
        fig_timeline.add_annotation(x=now, y=1, yref="paper", text="CURRENT OPS", showarrow=False, font=dict(color=current_theme['accent'], size=10), bgcolor=current_theme['card_bg'], opacity=0.8)

        fig_timeline.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", 
            font_color=chart_font_color, height=500, margin=dict(t=10, b=0, l=0, r=0),
            xaxis_title="", yaxis_title="",
            legend=dict(orientation="h", yanchor="bottom", y=1.1, xanchor="left", x=0),
            showlegend=True
        )
        
        fig_timeline.update_yaxes(autorange="reversed", gridcolor=f"{current_theme['border']}")
        fig_timeline.update_xaxes(gridcolor=f"{current_theme['border']}", zeroline=False)
        
        st.plotly_chart(fig_timeline, use_container_width=True)
    else:
        st.info("No active or scheduled workshop events found.")
    
    st.markdown('</div></div>', unsafe_allow_html=True)

    # ── OPERATIONS & ANALYTICS GRID ──────────────────────────────────────────
    col_l, col_r = st.columns([1, 1])

    with col_l:
        # 1. Mechanic Workload
        st.markdown('<div class="glass-card"><div class="card-header"><h3>👨‍🔧 Mechanic Workload Analytics</h3></div><div class="card-body">', unsafe_allow_html=True)
        mech_work = filtered_df.groupby('assigned_mechanic').agg({'schedule_id': 'count', 'cost': 'sum'}).reset_index()
        mech_work.columns = ['Mechanic', 'Tasks', 'Total Cost Managed']
        
        fig_mech = px.bar(mech_work.sort_values('Tasks', ascending=True), 
                         y='Mechanic', x='Tasks', orientation='h',
                         title="Active Assignments per Technician",
                         color='Tasks', color_continuous_scale="Blues")
        fig_mech.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color=chart_font_color, height=350, margin=dict(t=30, b=0, l=0, r=0), yaxis={'type': 'category'})
        st.plotly_chart(fig_mech, use_container_width=True)
        st.markdown('</div></div>', unsafe_allow_html=True)

    with col_r:
        # 2. Cost TREEMAP
        st.markdown('<div class="glass-card"><div class="card-header"><h3>💰 Maintenance Cost treemap</h3></div><div class="card-body">', unsafe_allow_html=True)
        fig_tree = px.treemap(filtered_df, path=['maintenance_type', 'truck_id'], values='cost',
                             title="Cost Distribution by Service Type & Asset",
                             color='cost', color_continuous_scale='YlOrRd')
        fig_tree.update_layout(paper_bgcolor="rgba(0,0,0,0)", font_color=chart_font_color, height=350, margin=dict(t=30, b=0, l=0, r=0))
        st.plotly_chart(fig_tree, use_container_width=True)
        st.markdown('</div></div>', unsafe_allow_html=True)

    # ROW 2: Downtime & Distribution
    col_d1, col_d2 = st.columns(2)

    with col_d1:
        # 3. Duration by Truck
        st.markdown('<div class="glass-card"><div class="card-header"><h3>🛑 Downtime by Truck</h3></div><div class="card-body">', unsafe_allow_html=True)
        # Sum duration for the subset
        downtime_df = filtered_df.groupby('truck_id')['duration_h'].sum().reset_index()
        downtime_df['truck_label'] = downtime_df.apply(lambda x: f"Truck #{int(x['truck_id'])}", axis=1)
        
        fig_dur = px.bar(downtime_df.sort_values('duration_h', ascending=True), 
                        y='truck_label', x='duration_h', orientation='h',
                        title="Total Hours in Workshop",
                        color='duration_h', color_continuous_scale="Reds",
                        labels={'duration_h': 'Downtime (Hours)', 'truck_label': 'Vehicle'})
        fig_dur.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color=chart_font_color, height=350, margin=dict(t=30, b=0, l=0, r=0), yaxis={'type': 'category'})
        st.plotly_chart(fig_dur, use_container_width=True)
        st.markdown('</div></div>', unsafe_allow_html=True)

    with col_d2:
        # 4. Maintenance Type Count
        st.markdown('<div class="glass-card"><div class="card-header"><h3>⚙️ Service Type Distribution</h3></div><div class="card-body">', unsafe_allow_html=True)
        type_counts = filtered_df['maintenance_type'].value_counts().reset_index()
        type_counts.columns = ['Service Type', 'Count']
        
        fig_type = px.bar(type_counts.sort_values('Count', ascending=True), 
                         y='Service Type', x='Count', orientation='h',
                         title="Volume by Maintenance Category",
                         color='Count', color_continuous_scale="GnBu")
        fig_type.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color=chart_font_color, height=350, margin=dict(t=30, b=0, l=0, r=0), yaxis={'type': 'category'})
        st.plotly_chart(fig_type, use_container_width=True)
        st.markdown('</div></div>', unsafe_allow_html=True)

    # ── WORKSHOP LEDGER ───────────────────────────────────────────────────────
    st.markdown('<div class="glass-card"><div class="card-header"><h3>📋 Strategic Workshop Ledger</h3></div><div class="card-body">', unsafe_allow_html=True)
    
    ledger_cols = ['start', 'truck_id', 'maintenance_type', 'assigned_mechanic', 'cost', 'op_status', 'description']
    st.dataframe(
        filtered_df[ledger_cols].sort_values('start', ascending=False),
        column_config={
            "start": st.column_config.DatetimeColumn("Scheduled Start", format="DD/MM/YYYY HH:mm"),
            "truck_id": "Unit ID",
            "maintenance_type": "Service Type",
            "assigned_mechanic": "Technician",
            "cost": st.column_config.NumberColumn("Cost (MAD)", format="%d"),
            "op_status": "Status",
            "description": "Work Order Details"
        },
        hide_index=True,
        use_container_width=True
    )
    st.markdown('</div></div>', unsafe_allow_html=True)

else:
    st.warning("⚠️ No workshop operations data found. Ensure the 'maintenance_scheduler_dag' has completed its audit.")
    st.markdown("""
        <div style="text-align: center; padding: 100px;">
            <div style="font-size: 5rem; opacity: 0.1;">🛠️</div>
            <p style="margin-top: 20px; color: #8892b0;">Synchronizing workshop schedules and resource allocations...</p>
        </div>
    """, unsafe_allow_html=True)
