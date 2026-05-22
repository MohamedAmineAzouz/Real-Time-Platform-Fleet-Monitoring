import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import time
import io

from utils.cassandra_client import query_df
from utils.styles import get_css, THEMES, hex_to_rgba

# ── Page Config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="FleetPulse | Route Intelligence",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Theme Management ─────────────────────────────────────────────────────────
if 'theme_mode' not in st.session_state:
    st.session_state.theme_mode = "Dark"

st.markdown(get_css(st.session_state.theme_mode), unsafe_allow_html=True)
current_theme = THEMES[st.session_state.theme_mode]

# ── City Geodata Mapping ──────────────────────────────────────────────────────
# Coordinates for mapping visualizations based on simulator settings
CITY_COORDS = {
    "Casablanca": {"lat": 33.5731, "lon": -7.5898},
    "Tangier": {"lat": 35.7595, "lon": -5.8144},
    "Marrakech": {"lat": 31.6295, "lon": -7.9811},
    "Agadir": {"lat": 30.4278, "lon": -9.5982},
    "Fes": {"lat": 34.0181, "lon": -5.0078},
    "Meknes": {"lat": 33.8935, "lon": -5.5473},
    "Rabat": {"lat": 34.0209, "lon": -6.8416},
    "Oujda": {"lat": 34.6805, "lon": -1.9078},
    "Tetouan": {"lat": 35.5889, "lon": -5.3683},
    "Kenitra": {"lat": 34.2610, "lon": -6.5890},
    "Beni Mellal": {"lat": 32.3373, "lon": -6.3498},
    "Safi": {"lat": 32.2994, "lon": -9.2372},
}

# ── Data Loading ─────────────────────────────────────────────────────────────
@st.cache_data(ttl=600)
def get_route_data():
    try:
        df_route = query_df("SELECT * FROM batch_route_efficiency")
        df_drivers = query_df("SELECT * FROM drivers")
        
        if df_route.empty:
            return pd.DataFrame()
            
        df_route['date'] = pd.to_datetime(df_route['stat_date'])
        
        # Link Drivers
        if not df_drivers.empty:
            name_map = dict(zip(df_drivers['driver_id'], df_drivers['name']))
            df_route['driver_name'] = df_route['driver_id'].map(name_map).fillna(df_route['driver_id'])
        else:
            df_route['driver_name'] = df_route['driver_id']
            
        df_route['display_label'] = df_route.apply(lambda x: f"T#{x['truck_id']} ({x['driver_name']})", axis=1)
        df_route['route_name'] = df_route['start_city'] + " ➔ " + df_route['end_city']
        
        # Enforce numeric types
        num_cols = [
            'total_trips', 'total_distance_km', 'target_distance_km', 'total_fuel_consumed_l',
            'avg_fuel_per_100km', 'avg_speed_kmh', 'total_duration_h', 'avg_alerts_per_trip'
        ]
        for col in num_cols:
            if col in df_route.columns:
                df_route[col] = pd.to_numeric(df_route[col], errors='coerce').fillna(0)
                
        return df_route
    except Exception as e:
        st.error(f"Error loading route intelligence data: {e}")
        return pd.DataFrame()

# ── Helper Components ─────────────────────────────────────────────────────────
def render_route_kpis(kpi_data):
    kpi_items = []
    for kpi in kpi_data:
        label, value, icon, color = kpi.get("label"), kpi.get("value"), kpi.get("icon"), kpi.get("color", current_theme['primary'])
        card_html = (
            f'<div class="metric-card">'
            f'<div style="display: flex; justify-content: space-between; align-items: flex-start;">'
            f'<div class="metric-label" style="color: {st.session_state.theme_mode == "Light" and "#000000" or current_theme["text_muted"]}">{label}</div>'
            f'<div style="font-size: 1.1rem; opacity: 0.7;">{icon}</div>'
            f'</div>'
            f'<div><div class="metric-value" style="font-size: 1.6rem; color: {color if st.session_state.theme_mode == "Dark" else "#000000"}">{value}</div></div>'
            f'</div>'
        )
        kpi_items.append(card_html)
    st.markdown(f'<div class="kpi-grid">{"".join(kpi_items)}</div>', unsafe_allow_html=True)

# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"""
        <div style="text-align: left; padding: 0.5rem 0;">
            <div class="sidebar-title">🧭 Logistics</div>
            <div class="sidebar-subtitle">Transportation Intelligence</div>
        </div>
    """, unsafe_allow_html=True)
    
    st.markdown('<div class="sidebar-section-header">Executive Theme</div>', unsafe_allow_html=True)
    is_dark = st.toggle("Dark Mode", value=(st.session_state.theme_mode == "Dark"))
    new_mode = "Dark" if is_dark else "Light"
    if new_mode != st.session_state.theme_mode:
        st.session_state.theme_mode = new_mode
        st.rerun()

    st.divider()
    st.markdown('<div class="sidebar-section-header">Route Filters</div>', unsafe_allow_html=True)
    
    raw_df = get_route_data()
    
    if not raw_df.empty:
        # Date Filter
        min_d, max_d = raw_df['date'].min(), raw_df['date'].max()
        sel_dates = st.date_input("Analysis Period", value=(min_d, max_d), min_value=min_d, max_value=max_d)
        
        # Status Filter
        sel_status = st.multiselect("Trip Status", ["finished", "unfinished"], default=["finished", "unfinished"])
        
        # City Filters
        start_cities = ["All Cities"] + sorted(raw_df['start_city'].unique().tolist())
        sel_start = st.selectbox("Origin City", start_cities)
        
        end_cities = ["All Cities"] + sorted(raw_df['end_city'].unique().tolist())
        sel_end = st.selectbox("Destination City", end_cities)
        
        # Assets
        trucks = ["All Trucks"] + sorted(raw_df['truck_id'].unique().tolist())
        sel_truck = st.selectbox("Asset Search", trucks)
        
        st.markdown('<div class="sidebar-section-header">Optimization Constraints</div>', unsafe_allow_html=True)
        min_trips = st.number_input("Minimum Trips per Route", min_value=0, value=0)
    else:
        st.info("Awaiting logistics ledger...")

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🔄 Force Cluster Refresh", type="primary", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# ── Data Processing ──────────────────────────────────────────────────────────
if not raw_df.empty:
    filtered_df = raw_df.copy()
    
    # Apply Filters
    if isinstance(sel_dates, tuple) and len(sel_dates) == 2:
        filtered_df = filtered_df[(filtered_df['date'].dt.date >= sel_dates[0]) & (filtered_df['date'].dt.date <= sel_dates[1])]
    
    if sel_status:
        filtered_df = filtered_df[filtered_df['status'].isin(sel_status)]
        
    if sel_start != "All Cities":
        filtered_df = filtered_df[filtered_df['start_city'] == sel_start]
    if sel_end != "All Cities":
        filtered_df = filtered_df[filtered_df['end_city'] == sel_end]
    if sel_truck != "All Trucks":
        filtered_df = filtered_df[filtered_df['truck_id'] == sel_truck]
    
    filtered_df = filtered_df[filtered_df['total_trips'] >= min_trips]

    # Calculate Route Aggregates
    route_agg = filtered_df.groupby(['start_city', 'end_city', 'route_name']).agg({
        'total_trips': 'sum',
        'total_distance_km': 'sum',
        'total_fuel_consumed_l': 'sum',
        'avg_fuel_per_100km': 'mean',
        'avg_speed_kmh': 'mean',
        'total_duration_h': 'sum',
        'avg_alerts_per_trip': 'mean'
    }).reset_index()

    # Derived KPIs
    completed_trips = filtered_df[filtered_df['status'] == 'finished']['total_trips'].sum()
    total_active_routes = len(route_agg)
    total_km = route_agg['total_distance_km'].sum()
    total_l = route_agg['total_fuel_consumed_l'].sum()
    
    # ── Header ──────────────────────────────────────────────────────────────────
    col_h1, col_h2 = st.columns([3, 1])
    with col_h1:
        st.markdown("""
            <h1 style="margin-bottom: 0;">Transportation & Route Optimization</h1>
            <p style="color: #94a3b8; font-size: 1.1rem;">Logistics Intelligence Control Tower</p>
        """, unsafe_allow_html=True)
    with col_h2:
        st.markdown(f"""
            <div class="glass-card" style="padding: 15px; text-align: center; border-color: {current_theme['success']}44;">
                <div style="color: {current_theme['success']}; font-weight: 800; font-size: 0.9rem;">🟢 OPTIMIZATION ACTIVE</div>
                <div style="font-size: 0.7rem; color: #94a3b8; margin-top: 5px;">ANALYZING {completed_trips} COMPLETED JOURNEYS</div>
            </div>
        """, unsafe_allow_html=True)

    # ── Executive KPIs ────────────────────────────────────────────────────────
    kpis = [
        {"label": "Completed Trips", "value": f"{completed_trips:,.0f}", "icon": "✅"},
        {"label": "Active Routes", "value": f"{total_active_routes}", "icon": "🚚"},
        {"label": "Fleet Distance", "value": f"{total_km:,.0f} km", "icon": "🛣️"},
        {"label": "Fuel Usage", "value": f"{total_l:,.0f} L", "icon": "⛽"},
    ]
    render_route_kpis(kpis)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── ANALYTICS GRID ────────────────────────────────────────────────────────
    chart_font_color = "#000000" if st.session_state.theme_mode == "Light" else "#ffffff"

    # ROW 1: Efficiency and Usage
    r1_col1, r1_col2 = st.columns(2)

    with r1_col1:
        # 1. Efficiency Ranking
        st.markdown(f"""
            <div class="glass-card">
                <div class="card-header"><h3>📈 Strategic Efficiency Ranking</h3></div>
                <div class="card-body">
        """, unsafe_allow_html=True)
        fig_eff = px.bar(route_agg.sort_values('avg_fuel_per_100km', ascending=True).head(10), 
                        x='avg_fuel_per_100km', y='route_name', orientation='h',
                        color='avg_fuel_per_100km', color_continuous_scale="RdYlGn_r",
                        title="Top 10 Most Efficient Corridors",
                        labels={'avg_fuel_per_100km': 'L/100km', 'route_name': 'Route Corridor'})
        fig_eff.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color=chart_font_color, height=400, margin=dict(t=30, b=0, l=0, r=0), yaxis={'type': 'category'})
        st.plotly_chart(fig_eff, use_container_width=True)
        st.markdown("</div></div>", unsafe_allow_html=True)

    with r1_col2:
        # 2. Usage Volume
        st.markdown(f"""
            <div class="glass-card">
                <div class="card-header"><h3>📊 Strategic Usage Volume</h3></div>
                <div class="card-body">
        """, unsafe_allow_html=True)
        fig_use = px.bar(route_agg.sort_values('total_trips', ascending=False).head(10), 
                        x='total_trips', y='route_name', orientation='h',
                        color='total_trips', color_continuous_scale="Viridis",
                        title="Most Traversed Route Corridors",
                        labels={'total_trips': 'Trip Count', 'route_name': 'Route Corridor'})
        fig_use.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color=chart_font_color, height=400, margin=dict(t=30, b=0, l=0, r=0), yaxis={'type': 'category'})
        st.plotly_chart(fig_use, use_container_width=True)
        st.markdown("</div></div>", unsafe_allow_html=True)

    # ROW 2: Risk Analytics
    st.markdown(f"""
        <div class="glass-card">
            <div class="card-header"><h3>🚨 Route Risk Intelligence</h3></div>
            <div class="card-body">
    """, unsafe_allow_html=True)
    
    fig_risk = px.scatter(route_agg, x='avg_speed_kmh', y='avg_alerts_per_trip', 
                         size='total_trips', color='avg_alerts_per_trip',
                         color_continuous_scale="Reds",
                         title="Risk Analysis: Speed vs Incident Rate per Route",
                         labels={'avg_speed_kmh': 'Avg Speed (km/h)', 'avg_alerts_per_trip': 'Alerts per Trip'})
    fig_risk.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color=chart_font_color, height=450, margin=dict(t=30, b=0, l=0, r=0))
    st.plotly_chart(fig_risk, use_container_width=True)
    st.markdown("</div></div>", unsafe_allow_html=True)

    # ── Executive Reporting Row ───────────────────────────────────────────────
    st.markdown(f"""
        <div class="glass-card">
            <div class="card-header"><h3>📊 Executive Logistics Reporting</h3></div>
            <div class="card-body">
    """, unsafe_allow_html=True)
    
    rep_col1, rep_col2, rep_col3 = st.columns(3)
    with rep_col1:
        st.markdown("#### 📥 Data Export")
        csv = filtered_df.to_csv(index=False).encode('utf-8')
        st.download_button("Export Detailed Route Ledger (CSV)", data=csv, file_name="route_intelligence_report.csv", mime="text/csv", use_container_width=True)
    
    with rep_col2:
        st.markdown("#### 💡 AI Recommendations")
        if not route_agg.empty:
            expensive = route_agg.loc[route_agg['avg_fuel_per_100km'].idxmax()]
            st.warning(f"Optimization Required: Route **{expensive['route_name']}** has high fuel consumption. Consider vehicle swaps or speed capping.")
        else:
            st.info("Insufficient data for AI recommendations.")

    with rep_col3:
        st.markdown("#### 📅 Operations Summary")
        st.success(f"Logistics operations processed **{completed_trips}** completed trips across **{total_active_routes}** active corridors.")
    
    st.markdown("</div></div>", unsafe_allow_html=True)

else:
    st.warning("⚠️ No logistics optimization data found. Please ensure 'route_efficiency_dag' has populated the data warehouse.")
    st.markdown("""
        <div style="text-align: center; padding: 100px;">
            <div style="font-size: 5rem; opacity: 0.1;">🧭</div>
            <p style="margin-top: 20px; color: #8892b0;">Aggregating city-to-city transportation metrics...</p>
        </div>
    """, unsafe_allow_html=True)
