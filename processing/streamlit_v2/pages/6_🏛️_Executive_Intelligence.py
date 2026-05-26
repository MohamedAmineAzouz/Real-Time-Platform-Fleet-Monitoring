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
    page_title="FleetPulse | Executive Intelligence",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Theme Management ─────────────────────────────────────────────────────────
if 'theme_mode' not in st.session_state:
    st.session_state.theme_mode = "Dark"

st.markdown(get_css(st.session_state.theme_mode), unsafe_allow_html=True)
current_theme = THEMES[st.session_state.theme_mode]

# ── Data Loading ─────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600)
def get_weekly_summary():
    try:
        df = query_df("SELECT * FROM batch_weekly_summary")
        if df.empty: return pd.DataFrame()
        num_cols = ['total_distance_km', 'total_fuel_consumed_l', 'avg_fuel_per_100km', 'total_alerts', 'fleet_utilization_avg', 'wow_distance_pct', 'wow_fuel_pct', 'wow_alerts_pct']
        for col in num_cols:
            if col in df.columns: df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        return df.sort_values('week_id', ascending=False)
    except Exception as e:
        st.error(f"Error loading executive data: {e}")
        return pd.DataFrame()

# ── Helper Components ─────────────────────────────────────────────────────────
def render_executive_kpis(kpi_data):
    """Render all KPIs in a single responsive CSS grid with standard styling."""
    kpi_items = []
    for kpi in kpi_data:
        label = kpi.get("label", "")
        value = kpi.get("value", "")
        icon = kpi.get("icon", "📊")
        trend = kpi.get("trend")
        
        t_html = ""
        if trend is not None:
            is_up = trend >= 0
            t_clr = current_theme['danger'] if (("Alerts" in label or "Fuel" in label) and is_up) or (("Distance" in label or "Util" in label) and not is_up) else current_theme['success']
            t_html = f'<div class="trend-indicator" style="color:{t_clr}; margin-top:8px;">{"↑" if is_up else "↓"} {abs(trend)}% WoW</div>'
        
        l_col = "#000000" if st.session_state.theme_mode == 'Light' else current_theme['text_muted']
        
        card = (
            f'<div class="metric-card">'
            f'<div style="display:flex;justify-content:space-between;align-items:flex-start;">'
            f'<div class="metric-label" style="color:{l_col}">{label}</div>'
            f'<div style="font-size:1.2rem;opacity:0.8;">{icon}</div>'
            f'</div>'
            f'<div>'
            f'<div class="metric-value" style="font-size:1.8rem;margin:4px 0;">{value}</div>'
            f'{t_html}'
            f'</div>'
            f'</div>'
        )
        kpi_items.append(card)
    
    st.markdown(f'<div class="kpi-grid">{"".join(kpi_items)}</div>', unsafe_allow_html=True)

def render_ranking_card(title, items, icon="🏆"):
    """Render a ranking card using standard glass-card and ranking-row classes."""
    header_html = f'<div class="glass-card" style="margin-bottom:0;"><div class="card-header"><h4>{icon} {title}</h4></div><div class="card-body" style="padding: 12px 24px;">'
    
    row_items = []
    if items:
        for i, item in enumerate(items):
            if ":" in item:
                subject, val = item.split(":", 1)
                subject, val = subject.strip(), val.strip()
            else:
                subject, val = item.strip(), ""
            
            idx_bg = current_theme['primary'] if i == 0 else (current_theme['success'] if i < 3 else current_theme['secondary'])
            row = (
                f'<div class="ranking-row">'
                f'<div class="rank-index" style="background:{idx_bg};">{i+1}</div>'
                f'<div class="rank-subject">{subject}</div>'
                f'<div class="rank-value">{val}</div>'
                f'</div>'
            )
            row_items.append(row)
    else:
        row_items.append('<div style="color:#8892b0; font-size:0.85rem; padding:15px 0; text-align:center;">Awaiting operational data...</div>')
        
    full_card = header_html + "".join(row_items) + '</div></div>'
    return full_card

# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(f'<div style="text-align:left; padding:0.5rem 0;"><div class="sidebar-title">🏛️ Executive</div><div class="sidebar-subtitle">Weekly Intelligence</div></div>', unsafe_allow_html=True)
    
    st.markdown('<div class="sidebar-section-header">Executive Theme</div>', unsafe_allow_html=True)
    is_dark = st.toggle("Dark Mode", value=(st.session_state.theme_mode == "Dark"))
    if is_dark != (st.session_state.theme_mode == "Dark"):
        st.session_state.theme_mode = "Dark" if is_dark else "Light"
        st.rerun()
    
    st.divider()
    summary_df = get_weekly_summary()
    if not summary_df.empty:
        weeks = summary_df['week_id'].tolist()
        sel_week = st.selectbox("Reporting Period", weeks)
        week_data = summary_df[summary_df['week_id'] == sel_week].iloc[0]
    else:
        st.info("Awaiting strategic roll-up...")
        
    if st.button("🔄 Force Cluster Refresh", type="primary", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# ── Main Content ─────────────────────────────────────────────────────────────
if not summary_df.empty:
    # ── Executive Header ──────────────────────────────────────────────────────
    u_target, e_target = 75.0, 28.0
    u_score = min(100, (week_data['fleet_utilization_avg'] / u_target) * 100)
    e_score = min(100, (e_target / (week_data['avg_fuel_per_100km'] + 0.001)) * 100)
    s_score = max(0, 100 - (week_data['total_alerts'] / 100))
    f_score = (u_score * 0.4) + (e_score * 0.3) + (s_score * 0.3)
    
    col_t, col_s = st.columns([3, 1])
    with col_t:
        st.markdown(f'<h1 style="margin-bottom:0; color:{current_theme["text_main"]};">Weekly Fleet Intelligence</h1><p style="color:{current_theme["text_muted"]}; font-size:1.1rem;">Strategic Performance Summary: <b>Week {week_data["week_id"]}</b></p>', unsafe_allow_html=True)
    
    with col_s:
        status_color = current_theme['success'] if f_score > 80 else (current_theme['warning'] if f_score > 60 else current_theme['danger'])
        perf_txt = "PERFORMANCE IMPROVED" if week_data['wow_distance_pct'] >= 0 else "MAINTAINING SCALE"
        st.markdown(f'<div class="glass-card" style="padding:15px; text-align:center; border-color:{status_color}44;"><div style="color:{status_color}; font-weight:800; font-size:0.9rem;">🟢 {perf_txt}</div><div style="font-size:0.7rem; color:{current_theme["text_muted"]}; margin-top:5px;">STRATEGIC FLEET SCORE: {f_score:.1f}%</div></div>', unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── KPI Grid ───────────────────────────────────────────────────────
    kpi_data = [
        {"label": "Weekly Distance", "value": f"{week_data['total_distance_km']:,.0f} km", "trend": week_data['wow_distance_pct'], "icon": "🛣️"},
        {"label": "Fuel Consumed", "value": f"{week_data['total_fuel_consumed_l']:,.0f} L", "trend": week_data['wow_fuel_pct'], "icon": "⛽"},
        {"label": "Avg Efficiency", "value": f"{week_data['avg_fuel_per_100km']:.2f} L/100", "icon": "📉"},
        {"label": "Fleet Utilization", "value": f"{week_data['fleet_utilization_avg']:.1f}%", "icon": "🏗️"},
        {"label": "Total Alerts", "value": f"{week_data['total_alerts']}", "trend": week_data['wow_alerts_pct'], "icon": "🚨", "color": current_theme['danger']},
    ]
    render_executive_kpis(kpi_data)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Leaderboards ──────────────────────────────────────────────────────────
    st.markdown('<h3 style="margin-bottom:20px;">🏆 Fleet Excellence Leaderboards</h3>', unsafe_allow_html=True)
    
    l1 = render_ranking_card("Distance Leaders", week_data['top_trucks_distance'], "🚛")
    l2 = render_ranking_card("Efficiency Leaders", week_data['top_trucks_efficiency'], "📉")
    l3 = render_ranking_card("Driver Excellence", week_data['top_drivers_performance'], "🛡️")
    l4 = render_ranking_card("Strategic Corridors", week_data['top_routes'], "🛣️")
    
    st.markdown(f'<div class="kpi-grid">{l1}{l2}{l3}{l4}</div>', unsafe_allow_html=True)

    # ── Summary Footer ──
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(f"""
        <div class="glass-card" style="background:transparent; border-style:dashed; opacity:0.8;">
            <div class="card-body" style="text-align:center; padding:20px;">
                <p style="font-size:0.95rem; margin:0; line-height:1.6; color:{current_theme['text_muted']};">
                    In <b>Week {week_data['week_id']}</b>, the fleet achieved a strategic score of <b>{f_score:.1f}%</b>. 
                    Operational volume reached <b>{week_data['total_distance_km']:,.0f} km</b> with a 
                    <b>{abs(week_data['wow_alerts_pct'])}% {'improvement' if week_data['wow_alerts_pct'] < 0 else 'variance'}</b> in safety metrics.
                </p>
            </div>
        </div>
    """, unsafe_allow_html=True)

else:
    st.warning("⚠️ Executive Intelligence ledger not found.")
    st.markdown('<div style="text-align:center;padding:100px;"><div style="font-size:5rem;opacity:0.1;">🏛️</div><p style="margin-top:20px;color:#8892b0;">Consolidating weekly strategic metrics...</p></div>', unsafe_allow_html=True)
