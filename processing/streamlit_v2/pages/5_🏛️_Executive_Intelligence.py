import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import time
import os

from utils.cassandra_client import query_df
from utils.styles import get_css, THEMES, hex_to_rgba
from utils.rag_retriever import retrieve_all_context

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

    st.markdown('<div class="sidebar-section-header">🤖 Local GenAI (Ollama)</div>', unsafe_allow_html=True)
    default_ollama_host = os.getenv("OLLAMA_HOST", "http://ollama:11434")
    default_ollama_model = os.getenv("OLLAMA_MODEL", "llama3.2")

    st.caption(f"**Host**: `{default_ollama_host}`")
    st.caption(f"**Model**: `{default_ollama_model}`")

    st.session_state.ollama_url = default_ollama_host
    st.session_state.ollama_model = default_ollama_model

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

    # ── Floating Bottom-Right Chatbot Widget ─────────────────────────────────
    # Built on plain keyed containers (not st.popover) — see prior notes:
    # st.popover uses JS-driven floating/portal positioning that fights any
    # CSS override, whereas a container with `key=` gets a stable class
    # (`st-key-<key>`) and renders as a normal in-flow div, so plain
    # `position: fixed` on it is reliable.
    if "fp_chat_open" not in st.session_state:
        st.session_state.fp_chat_open = False
    if "fp_pending" not in st.session_state:
        st.session_state.fp_pending = False
    if "fp_pending_prompt" not in st.session_state:
        st.session_state.fp_pending_prompt = None

    st.markdown("""
    <style>
    :root {
        --fp-bg: #0f172a;
        --fp-surface: #131c2e;
        --fp-border: rgba(255,255,255,0.08);
        --fp-text: #e2e8f0;
        --fp-text-muted: #94a3b8;
        --fp-accent: #2563EB;
        --fp-ai-bubble: #1e293b;
    }

    /* ── Floating trigger button ── */
    .st-key-fp_toggle_btn {
        position: fixed !important;
        bottom: 24px !important;
        right: 24px !important;
        z-index: 999999 !important;
        width: 52px !important;
        height: 52px !important;
    }
    .st-key-fp_toggle_btn button {
        width: 52px !important;
        height: 52px !important;
        min-width: 52px !important;
        border-radius: 50% !important;
        padding: 0 !important;
        margin: 0 !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        background: linear-gradient(135deg, #2563EB 0%, #4f46e5 100%) !important;
        color: #ffffff !important;
        border: none !important;
        font-size: 1.25rem !important;
        line-height: 1 !important;
        box-shadow: 0 8px 22px rgba(37, 99, 235, 0.45) !important;
        transition: transform 0.2s ease, box-shadow 0.2s ease !important;
    }
    .st-key-fp_toggle_btn button:hover {
        transform: scale(1.07) !important;
        box-shadow: 0 10px 28px rgba(37, 99, 235, 0.6) !important;
    }

    /* ── Modal panel ── */
    .st-key-fp_panel {
        position: fixed !important;
        bottom: 86px !important;
        right: 24px !important;
        width: 400px !important;
        max-width: 92vw !important;
        height: 540px !important;
        max-height: 80vh !important;
        background: var(--fp-bg) !important;
        border: 1px solid var(--fp-border) !important;
        border-radius: 16px !important;
        box-shadow: 0 20px 60px rgba(0, 0, 0, 0.6) !important;
        padding: 14px !important;
        overflow: hidden !important;
        z-index: 999998 !important;
        font-size: 0.85rem !important;
        animation: fpSlideUp 0.2s ease-out !important;
        justify-content: space-around !important;
    }
    @keyframes fpSlideUp {
        from { opacity: 0; transform: translateY(14px); }
        to   { opacity: 1; transform: translateY(0); }
    }

    /* Header row */
    .st-key-fp_header { margin-bottom: 8px !important; }
    .fp-header-left { display: flex; align-items: center; gap: 10px; }
    .fp-avatar {
        width: 34px; height: 34px; border-radius: 50%;
        background: linear-gradient(135deg, #2563EB, #4f46e5);
        display: flex; align-items: center; justify-content: center; font-size: 1rem;
        flex-shrink: 0;
    }
    .fp-title { font-weight: 700; font-size: 0.95rem; color: #f8fafc; line-height: 1.25; }
    .fp-status { font-size: 0.7rem; color: #10b981; margin-top: 2px; }

    .st-key-fp_close_btn button {
        background: transparent !important;
        border: none !important;
        color: var(--fp-text-muted) !important;
        font-size: 0.95rem !important;
        padding: 2px 8px !important;
        min-height: unset !important;
        height: auto !important;
        box-shadow: none !important;
    }
    .st-key-fp_close_btn button:hover { color: #f8fafc !important; }

    /* ── Scrollable message container ── */
    .st-key-fp_messages {
        height: 380px !important;
        overflow-y: auto !important;
        padding-right: 4px !important;
    }

    /* Clean, non-overlapping message bubbles */
    .st-key-fp_messages div[data-testid="stChatMessage"] {
        padding: 10px 10px 20px 5px !important;
        border-radius: 12px !important;
        margin-bottom: 10px !important;
        width: 100% !important;
        box-sizing: border-box !important;
        background: var(--fp-surface) !important;
        border: 1px solid var(--fp-border) !important;
    }

    /* User Message Bubble */
    .st-key-fp_messages div[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
        background: rgba(37, 99, 235, 0.2) !important;
        border-color: rgba(37, 99, 235, 0.4) !important;
    }

    /* Assistant Message Bubble */
    .st-key-fp_messages div[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) {
        background: rgba(30, 41, 59, 0.8) !important;
        border-color: rgba(255, 255, 255, 0.08) !important;
    }

    .st-key-fp_messages div[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] p {
        font-size: 0.83rem !important;
        line-height: 1.45 !important;
        font-weight: 400 !important;
        margin-bottom: 0 !important;
        padding-bottom: 0 !important;
        color: var(--fp-text) !important;
    }

    /* Typing indicator */
    .fp-typing { display: flex; align-items: center; gap: 4px; padding: 6px 0; }
    .fp-typing span {
        width: 6px; height: 6px; border-radius: 50%;
        background: var(--fp-text-muted);
        animation: fpBounce 1.2s infinite ease-in-out;
    }
    .fp-typing span:nth-child(2) { animation-delay: 0.15s; }
    .fp-typing span:nth-child(3) { animation-delay: 0.3s; }
    @keyframes fpBounce {
        0%, 60%, 100% { transform: translateY(0); opacity: 0.5; }
        30% { transform: translateY(-4px); opacity: 1; }
    }

    /* Input area */
    .st-key-fp_panel div[data-testid="stChatInput"] {
        margin-top: 8px !important;
        width: 100% !important;
        box-sizing: border-box !important;
    }
    .st-key-fp_panel div[data-testid="stChatInput"] textarea,
    .st-key-fp_panel div[data-testid="stChatInput"] input {
        width: 100% !important;
        box-sizing: border-box !important;
        font-size: 0.83rem !important;
        border-radius: 14px !important;
        background: #171c28 !important;
        border: 1px solid var(--fp-border) !important;
        color: var(--fp-text) !important;
        padding: 8px 12px !important;
        padding-left: 1.3rem;
        margin-left: -5%;

    }
    .st-key-fp_panel div[data-testid="stChatInput"] button {
        background: var(--fp-accent) !important;
        border-radius: 50% !important;
    }
    </style>
    </style>
    """, unsafe_allow_html=True)

    # Floating toggle button — always visible, fixed bottom-right
    if st.button("✕" if st.session_state.fp_chat_open else "💬", key="fp_toggle_btn"):
        st.session_state.fp_chat_open = not st.session_state.fp_chat_open
        st.rerun()

    if st.session_state.fp_chat_open:
        with st.container(key="fp_panel"):
            # Header
            with st.container(key="fp_header"):
                hcol1, hcol2 = st.columns([5, 1])
                with hcol1:
                    st.markdown("""
                        <div class="fp-header-left">
                            <div class="fp-avatar">🤖</div>
                            <div>
                                <div class="fp-title">Fleet Pulse AI</div>
                                <div class="fp-status">🟢 Online</div>
                            </div>
                        </div>
                    """, unsafe_allow_html=True)
                with hcol2:
                    if st.button("✕", key="fp_close_btn"):
                        st.session_state.fp_chat_open = False
                        st.rerun()

            if "chat_messages" not in st.session_state:
                st.session_state.chat_messages = [
                    {"role": "assistant", "content": "Hello! I'm your FleetPulse AI assistant. Ask me anything about fleet metrics, fuel anomalies, or maintenance priorities!"}
                ]

            # Scrollable message area. When a reply is pending, an animated
            # "typing" bubble renders here immediately (this Streamlit run
            # streams it to the browser right away), and a second rerun
            # swaps it out for the real answer once it's ready.
            with st.container(key="fp_messages", height=300):
                for msg in st.session_state.chat_messages:
                    with st.chat_message(msg["role"]):
                        st.markdown(msg["content"])
                if st.session_state.fp_pending:
                    with st.chat_message("assistant"):
                        st.markdown(
                            '<div class="fp-typing"><span></span><span></span><span></span></div>',
                            unsafe_allow_html=True,
                        )

            prompt_to_run = st.chat_input("Write a message...", disabled=st.session_state.fp_pending)

            # Step 1: a new prompt arrived — record it, show it immediately,
            # flip to "pending", and rerun so the typing bubble paints
            # before the (potentially slow) model call below even starts.
            if prompt_to_run and not st.session_state.fp_pending:
                st.session_state.chat_messages.append({"role": "user", "content": prompt_to_run})
                st.session_state.fp_pending = True
                st.session_state.fp_pending_prompt = prompt_to_run
                st.rerun()

            # Step 2: a reply is pending — actually generate it now, append
            # it, clear the pending flag, and rerun once more so the typing
            # bubble disappears and the final answer is what's shown.
            if st.session_state.fp_pending:
                pending_prompt = st.session_state.fp_pending_prompt

                SYSTEM_PROMPT = """You are FleetPulse Executive AI, a professional GenAI Strategic Fleet Analyst.
You are helping executives analyze the performance, efficiency, safety, and maintenance of their truck fleet in Morocco.

You have access to the latest batch analytics summaries from the Cassandra data warehouse:
{context}

Guidelines:
1. Provide highly professional, structured, and quantitative answers. Focus on concrete data points: mention specific weeks, corridors (e.g. Martil ➔ Settat), average speeds, alerts, fuel consumed (L), and truck IDs where relevant.
2. If the user asks about a specific corridor like 'Martil ➔ Settat', look at 'ROUTE/CORRIDOR OPERATIONAL EFFICIENCY' and identify any abnormal fuel consumption or high average fuel/100km.
3. Cross-reference with 'DAILY TRUCK STATISTICS' or 'FUEL WASTE AND ANOMALOUS CONSUMPTION' to find specific trucks (e.g. ID 10, 15, 22) that caused the variance due to overspeed alerts or fuel anomalies on those routes.
4. If you mention external factors like "heavy storm conditions" or "traffic delays", state them as reasonable hypotheses based on speed/alert data, and clearly ground them in the database stats.
5. If the database does not contain information to answer the question, state that the metrics are not available in the current batch rollup, but propose what to monitor.
6. Keep your answers concise, clear, and action-oriented for executives.
"""

                ollama_url = st.session_state.get("ollama_url", "http://ollama:11434")
                ollama_model = st.session_state.get("ollama_model", "llama3.2")

                try:
                    try:
                        from langchain_ollama import ChatOllama
                    except ImportError:
                        from langchain_community.chat_models import ChatOllama
                    from langchain.schema import SystemMessage, HumanMessage

                    context_data = retrieve_all_context()
                    system_instructions = SYSTEM_PROMPT.format(context=context_data)

                    llm = ChatOllama(
                        base_url=ollama_url,
                        model=ollama_model,
                        temperature=0.2
                    )

                    messages_for_llm = [SystemMessage(content=system_instructions)]
                    for old_msg in st.session_state.chat_messages[-6:]:
                        if old_msg["role"] == "user":
                            messages_for_llm.append(HumanMessage(content=old_msg["content"]))
                        elif old_msg["role"] == "assistant":
                            messages_for_llm.append(HumanMessage(content=old_msg["content"]))

                    response_text = ""
                    for chunk in llm.stream(messages_for_llm):
                        response_text += chunk.content

                    st.session_state.chat_messages.append({"role": "assistant", "content": response_text})
                except Exception as e:
                    response_text = f"⚠️ **LLM Error:** Could not connect to Ollama. Please make sure the Ollama service is running.\n\n`{e}`"
                    st.session_state.chat_messages.append({"role": "assistant", "content": response_text})

                st.session_state.fp_pending = False
                st.session_state.fp_pending_prompt = None
                st.rerun()

else:
    st.warning("⚠️ Executive Intelligence ledger not found.")
    st.markdown('<div style="text-align:center;padding:100px;"><div style="font-size:5rem;opacity:0.1;">🏛️</div><p style="margin-top:20px;color:#8892b0;">Consolidating weekly strategic metrics...</p></div>', unsafe_allow_html=True)