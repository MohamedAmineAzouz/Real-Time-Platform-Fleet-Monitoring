import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import uuid

from utils.cassandra_client import query_df
from utils.styles import get_css, THEMES, hex_to_rgba

# ── Page Config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="FleetPulse | Compliance Intelligence",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Theme Management ─────────────────────────────────────────────────────────
if 'theme_mode' not in st.session_state:
    st.session_state.theme_mode = "Dark"

st.markdown(get_css(st.session_state.theme_mode), unsafe_allow_html=True)
current_theme = THEMES[st.session_state.theme_mode]

# ── Data Loading ─────────────────────────────────────────────────────────────
@st.cache_data(ttl=600)
def get_compliance_data():
    try:
        df_viol = query_df("SELECT * FROM traffic_violations")
        df_drivers = query_df("SELECT * FROM drivers")
        
        if df_viol.empty:
            return pd.DataFrame()
            
        # Convert violation_date to datetime
        df_viol['date'] = pd.to_datetime(df_viol['violation_date'].astype(str))
        
        # Link Drivers
        if not df_drivers.empty:
            name_map = dict(zip(df_drivers['driver_id'], df_drivers['name']))
            # Use the NEW historical driver_id column if available, fallback to current registry mapping
            if 'driver_id' in df_viol.columns:
                df_viol['driver_name'] = df_viol['driver_id'].map(name_map).fillna(df_viol['driver_id'])
            else:
                truck_to_driver = dict(zip(df_drivers['current_truck_id'], df_drivers['name']))
                df_viol['driver_name'] = df_viol['truck_id'].map(truck_to_driver).fillna("Unassigned Driver")
        else:
            df_viol['driver_name'] = df_viol.get('driver_id', "Unassigned Driver")
            
        df_viol['display_label'] = df_viol.apply(lambda x: f"Truck #{x['truck_id']} ({x['driver_name']})", axis=1)
        
        # Enforce numeric types
        df_viol['fine_mad'] = pd.to_numeric(df_viol['fine_mad'], errors='coerce').fillna(0)
                
        return df_viol
    except Exception as e:
        st.error(f"Error loading compliance data: {e}")
        return pd.DataFrame()

# ── Helper Components ─────────────────────────────────────────────────────────
def render_compliance_kpis(kpi_data):
    """Render all KPIs in a single responsive CSS grid with minified HTML."""
    kpi_items = []
    for kpi in kpi_data:
        label = kpi.get("label")
        value = kpi.get("value")
        icon = kpi.get("icon")
        color = kpi.get("color", current_theme['primary'])
        trend = kpi.get("trend")
        
        trend_html = ""
        if trend:
            t_color = current_theme['danger'] if "↑" in trend else current_theme['success']
            trend_html = f'<div style="color: {t_color}; font-size: 0.75rem; font-weight: 700; margin-top: 4px;">{trend}</div>'

        label_color = "#000000" if st.session_state.theme_mode == 'Light' else current_theme['text_muted']
        card_html = (
            f'<div class="metric-card" style="border-left: 3px solid {color};">'
            f'<div style="display: flex; justify-content: space-between; align-items: flex-start;">'
            f'<div class="metric-label" style="color: {label_color}">{label}</div>'
            f'<div style="font-size: 1.1rem; opacity: 0.7;">{icon}</div>'
            f'</div>'
            f'<div>'
            f'<div class="metric-value" style="font-size: 1.6rem; margin: 4px 0; color: {color if st.session_state.theme_mode == "Dark" else "#000000"}">{value}</div>'
            f'{trend_html}'
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
            <div class="sidebar-title">⚖️ Compliance</div>
            <div class="sidebar-subtitle">Driver Risk Intelligence</div>
        </div>
    """, unsafe_allow_html=True)
    
    st.markdown('<div class="sidebar-section-header">Executive Theme</div>', unsafe_allow_html=True)
    is_dark = st.toggle("Dark Mode", value=(st.session_state.theme_mode == "Dark"))
    if is_dark != (st.session_state.theme_mode == "Dark"):
        st.session_state.theme_mode = "Dark" if is_dark else "Light"
        st.rerun()

    st.divider()
    st.markdown('<div class="sidebar-section-header">Violation Filters</div>', unsafe_allow_html=True)
    
    raw_df = get_compliance_data()
    
    if not raw_df.empty:
        # Time Period
        months = sorted(raw_df['month_year'].unique().tolist(), reverse=True)
        sel_month = st.selectbox("Reporting Period", ["All Time"] + months)
        
        # City
        cities = ["All Cities"] + sorted(raw_df['city'].unique().tolist())
        sel_city = st.selectbox("Jurisdiction", cities)
        
        # Violation Type
        v_types = ["All Types"] + sorted(raw_df['violation_type'].unique().tolist())
        sel_type = st.selectbox("Violation Category", v_types)
        
        # Truck Selector
        trucks = ["All Trucks"] + sorted(raw_df['truck_id'].unique().tolist())
        sel_truck = st.selectbox("Asset Search", trucks)
        
        st.markdown('<div class="sidebar-section-header">Risk Profiling</div>', unsafe_allow_html=True)
        min_fine = st.slider("Fine Threshold (MAD)", 0, 5000, 0, 100)
        high_risk_only = st.checkbox("High-Risk Violations Only")
        repeat_offenders = st.checkbox("Repeat Offenders Focus")
        
        st.markdown('<div class="sidebar-section-header">View Settings</div>', unsafe_allow_html=True)
        truck_limit = st.slider("Display Intensity", 5, 50, 10)
    else:
        st.info("Awaiting regulatory feed...")

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🔄 Force Compliance Audit", type="primary", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# ── Data Processing ──────────────────────────────────────────────────────────
if not raw_df.empty:
    filtered_df = raw_df.copy()
    
    # Apply Filters
    if sel_month != "All Time":
        filtered_df = filtered_df[filtered_df['month_year'] == sel_month]
    if sel_city != "All Cities":
        filtered_df = filtered_df[filtered_df['city'] == sel_city]
    if sel_type != "All Types":
        filtered_df = filtered_df[filtered_df['violation_type'] == sel_type]
    if sel_truck != "All Trucks":
        filtered_df = filtered_df[filtered_df['truck_id'] == sel_truck]
    
    filtered_df = filtered_df[filtered_df['fine_mad'] >= min_fine]
    
    if high_risk_only:
        # Define high risk types
        high_risk_types = ['OVERSPEED', 'RECKLESS_DRIVING', 'RED_LIGHT']
        filtered_df = filtered_df[filtered_df['violation_type'].isin(high_risk_types)]

    # Analysis Dataframe
    analysis_df = filtered_df.copy()
    
    # Repeat Offender Logic
    truck_counts = analysis_df['truck_id'].value_counts()
    if repeat_offenders:
        repeat_truck_ids = truck_counts[truck_counts > 1].index.tolist()
        analysis_df = analysis_df[analysis_df['truck_id'].isin(repeat_truck_ids)]

    # ── Executive Header ──────────────────────────────────────────────────────
    total_violations = len(analysis_df)
    total_fines = analysis_df['fine_mad'].sum()
    unique_offenders = analysis_df['truck_id'].nunique()
    
    col_h1, col_h2 = st.columns([3, 1])
    with col_h1:
        st.markdown(f"""
            <h1 style="margin-bottom: 0;">Compliance & Traffic Intelligence</h1>
            <p style="color: #94a3b8; font-size: 1.1rem;">Operational Governance & Regulatory Risk Control</p>
        """, unsafe_allow_html=True)
    with col_h2:
        risk_score = min(100, (total_violations * 2) + (total_fines / 5000))
        risk_label = "CRITICAL" if risk_score > 70 else ("HIGH" if risk_score > 40 else "MODERATE")
        risk_color = current_theme['danger'] if risk_score > 40 else current_theme['success']
        st.markdown(f"""
            <div class="glass-card" style="padding: 15px; text-align: center; border-color: {risk_color}44;">
                <div style="color: {risk_color}; font-weight: 800; font-size: 0.9rem;">⚖️ {risk_label} RISK LEVEL</div>
                <div style="font-size: 0.7rem; color: #94a3b8; margin-top: 5px;">LEGAL RISK INDEX: {risk_score:.1f}%</div>
            </div>
        """, unsafe_allow_html=True)

    # ── Executive KPIs ────────────────────────────────────────────────────────
    common_v = analysis_df['violation_type'].mode()[0] if not analysis_df.empty else "None"
    avg_fine = total_fines / unique_offenders if unique_offenders > 0 else 0
    dangerous_city = analysis_df['city'].mode()[0] if not analysis_df.empty else "N/A"
    
    kpis = [
        {"label": "Total Violations", "value": f"{total_violations}", "icon": "📝", "trend": "↑ 12% vs PM"},
        {"label": "Total Fines", "value": f"{total_fines:,.0f} MAD", "icon": "💰", "color": current_theme['danger'], "trend": "↑ 8% vs PM"},
        {"label": "Common Violation", "value": common_v, "icon": "⚠️"},
        {"label": "Risk Profiles", "value": f"{unique_offenders}", "icon": "🚚"},
        {"label": "Repeat Offenders", "value": f"{len(truck_counts[truck_counts > 1])}", "icon": "🔄", "color": current_theme['warning']},
    ]
    render_compliance_kpis(kpis)

    st.markdown("<br>", unsafe_allow_html=True)
    chart_font_color = "#000000" if st.session_state.theme_mode == "Light" else "#ffffff"

    # ── RISK & BEHAVIOR ANALYTICS ─────────────────────────────────────────────
    st.markdown('<div class="glass-card"><div class="card-header"><h3>🧠 Risk & Driver Behavior Analytics</h3></div><div class="card-body">', unsafe_allow_html=True)
    
    r1_col1, r1_col2 = st.columns(2)
    
    with r1_col1:
        # Offender Leaderboard
        offender_df = analysis_df.groupby('display_label').agg({'violation_id': 'count', 'fine_mad': 'sum'}).reset_index()
        offender_df.columns = ['Driver/Asset', 'Violations', 'Total Fines']
        fig_off = px.bar(offender_df.nlargest(truck_limit, 'Total Fines').sort_values('Total Fines', ascending=True), 
                        x='Total Fines', y='Driver/Asset', orientation='h',
                        title="Top Financial Risk Profiles",
                        color='Total Fines', color_continuous_scale="Reds")
        fig_off.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color=chart_font_color, height=400, margin=dict(t=50, b=0, l=0, r=0), yaxis={'type': 'category'})
        st.plotly_chart(fig_off, use_container_width=True)

    with r1_col2:
        # Violation Type Radar
        v_dist = analysis_df['violation_type'].value_counts()
        fig_vradar = go.Figure()
        fig_vradar.add_trace(go.Scatterpolar(
            r=v_dist.values,
            theta=v_dist.index,
            fill='toself',
            line_color=current_theme['accent'],
            fillcolor=hex_to_rgba(current_theme['accent'], 0.3)
        ))
        fig_vradar.update_layout(
            polar=dict(radialaxis=dict(visible=True, gridcolor=current_theme['border'])),
            title="Violation Category Distribution",
            paper_bgcolor="rgba(0,0,0,0)", font_color=chart_font_color, height=400, margin=dict(t=80, b=40, l=40, r=40)
        )
        st.plotly_chart(fig_vradar, use_container_width=True)
    
    st.markdown('</div></div>', unsafe_allow_html=True)

    # ── FINANCIAL & JURISDICTION ANALYTICS ────────────────────────────────────
    st.markdown('<div class="glass-card"><div class="card-header"><h3>💰 Financial Impact & Jurisdiction Intelligence</h3></div><div class="card-body">', unsafe_allow_html=True)
    
    # City Heatmap (Now Full Width)
    city_stats = analysis_df.groupby('city')['fine_mad'].sum().reset_index()
    fig_city = px.bar(city_stats.sort_values('fine_mad', ascending=True), 
                     x='fine_mad', y='city', orientation='h',
                     title="Fine Concentration by City",
                     color='fine_mad', color_continuous_scale="Oranges",
                     labels={'fine_mad': 'Total Fines (MAD)', 'city': 'Jurisdiction'})
    fig_city.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color=chart_font_color, height=400, margin=dict(t=50, b=0, l=0, r=0), yaxis={'type': 'category'})
    st.plotly_chart(fig_city, use_container_width=True)

    st.markdown('</div></div>', unsafe_allow_html=True)

    # ── DETAILED COMPLIANCE LEDGER ────────────────────────────────────────────
    st.markdown('<div class="glass-card"><div class="card-header"><h3>📋 Strategic Compliance Ledger</h3></div><div class="card-body">', unsafe_allow_html=True)
    
    display_cols = ['violation_date', 'display_label', 'violation_type', 'city', 'fine_mad', 'details']
    st.dataframe(
        analysis_df[display_cols].sort_values('violation_date', ascending=False),
        column_config={
            "violation_date": st.column_config.DateColumn("Date", format="DD/MM/YYYY"),
            "display_label": "Asset & Driver",
            "violation_type": "Category",
            "city": "Location",
            "fine_mad": st.column_config.NumberColumn("Fine (MAD)", format="%d"),
            "details": "Evidence/Details"
        },
        hide_index=True,
        use_container_width=True
    )
    st.markdown('</div></div>', unsafe_allow_html=True)

else:
    st.warning("⚠️ No compliance data found. Ensure the 'traffic_violations_dag' has completed its monthly audit.")
    st.markdown("""
        <div style="text-align: center; padding: 100px;">
            <div style="font-size: 5rem; opacity: 0.1;">⚖️</div>
            <p style="margin-top: 20px; color: #8892b0;">Aggregating regional traffic violation records...</p>
        </div>
    """, unsafe_allow_html=True)
