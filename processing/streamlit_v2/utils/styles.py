"""
utils/styles.py
─────────────────────────────────────────────────────────────────────────────
Premium CSS and UI constants for the FleetPulse v2 Dashboard.
─────────────────────────────────────────────────────────────────────────────
"""

# Executive Color Palettes
THEMES = {
    "Dark": {
        "primary": "#38bdf8",     # Sky Blue
        "secondary": "#1e293b",   # Slate 800
        "background": "#0f172a",  # Slate 900
        "card_bg": "#1e293b",     # Slate 800
        "accent": "#f43f5e",      # Rose 500
        "success": "#10b981",     # Emerald 500
        "warning": "#f59e0b",     # Amber 500
        "danger": "#ef4444",      # Red 500
        "text_main": "#f1f5f9",   # Slate 100
        "text_muted": "#94a3b8",  # Slate 400
        "border": "rgba(255, 255, 255, 0.08)",
        "gradient": "linear-gradient(180deg, #0f172a 0%, #1e293b 100%)",
        "shadow": "0 4px 6px -1px rgba(0, 0, 0, 0.3), 0 2px 4px -1px rgba(0, 0, 0, 0.2)"
    },
    "Light": {
        "primary": "#0284c7",     # Sky 700
        "secondary": "#e2e8f0",   # Slate 200
        "background": "#f8fafc",  # Slate 50
        "card_bg": "#ffffff",     # White
        "accent": "#e11d48",      # Rose 600
        "success": "#059669",     # Emerald 600
        "warning": "#d97706",     # Amber 600
        "danger": "#dc2626",      # Red 600
        "text_main": "#000000",   # Pure Black
        "text_muted": "#475569",  # Slate 600
        "border": "rgba(0, 0, 0, 0.12)",
        "gradient": "linear-gradient(180deg, #f8fafc 0%, #f1f5f9 100%)",
        "shadow": "0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06)"
    }
}

ALERT_COLORS = {
    "OVERSPEED":  "#f59e0b",
    "OVERHEAT":   "#ef4444",
    "FUEL_THEFT": "#f43f5e",
    "FUEL_LEAK":  "#8b5cf6",
    "LOW_FUEL":   "#f97316",
    "NORMAL":     "#10b981",
}

ALERT_ICONS = {
    "OVERSPEED":  "⚡",
    "OVERHEAT":   "🌡️",
    "FUEL_THEFT": "🚨",
    "FUEL_LEAK":  "💧",
    "LOW_FUEL":   "⛽",
    "NORMAL":     "✅",
}

def get_css(mode="Dark"):
    theme = THEMES[mode]
    return f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    * {{
        font-family: 'Inter', sans-serif;
    }}

    .stApp {{
        background: {theme['gradient']};
        background-attachment: fixed;
    }}

    /* Premium Container */
    .glass-card {{
        background: {theme['card_bg']};
        border: 1px solid {theme['border']};
        border-radius: 12px;
        padding: 0px; /* Reset padding for internal headers */
        box-shadow: {theme['shadow']};
        margin-bottom: 24px;
        color: {theme['text_main']};
        overflow: hidden;
    }}

    .card-header {{
        padding: 16px 24px;
        border-bottom: 1px solid {theme['border']};
        background: {theme['text_muted']}05;
    }}

    .card-header h3, .card-header h4 {{
        margin: 0 !important;
        font-weight: 600 !important;
        letter-spacing: -0.02em !important;
    }}

    .card-body {{
        padding: 24px;
    }}

    /* Responsive KPI Grid */
    .kpi-grid {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
        gap: 20px;
        margin-bottom: 24px;
    }}

    /* Metric Card Refinement */
    .metric-card {{
        background: {theme['card_bg']};
        border-radius: 12px;
        padding: 20px;
        border: 1px solid {theme['border']};
        box-shadow: {theme['shadow']};
        transition: all 0.2s ease-in-out;
        color: {theme['text_main']};
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        min-height: 140px;
    }}

    .metric-card:hover {{
        transform: translateY(-2px);
        border-color: {theme['primary']}88;
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
    }}

    .metric-value {{
        font-size: 2rem;
        font-weight: 700;
        margin: 8px 0;
        color: {theme['text_main']};
        letter-spacing: -0.5px;
    }}

    .metric-label {{
        color: {mode == 'Light' and '#000000' or theme['text_muted']};
        font-size: 0.75rem;
        text-transform: uppercase;
        letter-spacing: 1.2px;
        font-weight: 600;
    }}

    .trend-indicator {{
        font-size: 0.85rem;
        font-weight: 600;
        display: flex;
        align-items: center;
        gap: 4px;
    }}

    .trend-up {{ color: {theme['success']}; }}
    .trend-down {{ color: {theme['danger']}; }}

    /* Pulsing Live Indicator */
    @keyframes pulse {{
        0% {{ transform: scale(0.95); opacity: 0.8; }}
        50% {{ transform: scale(1.1); opacity: 1; }}
        100% {{ transform: scale(0.95); opacity: 0.8; }}
    }}

    .live-dot {{
        height: 8px;
        width: 8px;
        background-color: {theme['success']};
        border-radius: 50%;
        display: inline-block;
        margin-right: 8px;
        animation: pulse 2s ease-in-out infinite;
        box-shadow: 0 0 12px {theme['success']}55;
    }}

    /* Sidebar Professional Styling */
    section[data-testid="stSidebar"] {{
        background-color: {theme['background']};
        border-right: 1px solid {theme['border']};
    }}

    section[data-testid="stSidebar"] .block-container {{
        padding-top: 1.5rem;
    }}

    .sidebar-title {{
        font-size: 1.4rem;
        font-weight: 700;
        letter-spacing: -0.5px;
        color: {theme['primary']};
        margin-bottom: 0px;
    }}

    .sidebar-subtitle {{
        font-size: 0.7rem;
        font-weight: 600;
        letter-spacing: 2px;
        color: {theme['text_muted']};
        text-transform: uppercase;
        margin-bottom: 20px;
    }}

    .sidebar-section-header {{
        font-size: 0.75rem;
        font-weight: 700;
        color: {theme['text_muted']};
        text-transform: uppercase;
        letter-spacing: 1px;
        margin: 20px 0 10px 0;
    }}

    /* System Status Block */
    .system-status-container {{
        background: {theme['text_muted']}08;
        border: 1px solid {theme['border']};
        border-radius: 10px;
        padding: 12px;
        margin-bottom: 20px;
    }}

    .system-status-text {{
        font-size: 0.75rem;
        font-weight: 600;
        color: {theme['success']};
        display: flex;
        align-items: center;
    }}

    /* Alert Items */
    .alert-item {{
        border-left: 3px solid;
        padding: 16px;
        margin-bottom: 12px;
        background: {theme['text_muted']}08;
        border-radius: 0 8px 8px 0;
        color: {theme['text_main']};
        transition: background 0.2s;
    }}
    
    .alert-item:hover {{
        background: {theme['text_muted']}15;
    }}

    /* Streamlit Overrides */
    footer {{visibility: hidden;}}
    #MainMenu {{visibility: hidden;}}
    
    /* Ensure sidebar controls are visible */
    [data-testid="stSidebarCollapsedControl"] {{
        background-color: {theme['primary']}22;
        border-radius: 0 8px 8px 0;
    }}
    
    div.stButton > button:first-child {{
        background-color: {theme['secondary']};
        color: {theme['text_main']};
        border-radius: 8px;
        border: 1px solid {theme['border']};
        padding: 0.5rem 1rem;
        font-weight: 500;
        font-size: 0.85rem;
        transition: all 0.2s;
    }}
    
    div.stButton > button:first-child:hover {{
        background-color: {theme['primary']};
        color: white;
        border-color: {theme['primary']};
        transform: translateY(-1px);
    }}
    
    h1, h2, h3, h4, h5, h6 {{
        color: {theme['text_main']};
        font-weight: 700;
        letter-spacing: -0.5px;
    }}
    
    p, span, label, .stMarkdown {{
        color: {theme['text_main']};
    }}

    /* Tabs Styling */
    .stTabs [data-baseweb="tab-list"] {{
        gap: 24px;
        background-color: transparent;
    }}

    .stTabs [data-baseweb="tab"] {{
        height: 40px;
        padding: 0 10px;
        background-color: transparent;
        border: none;
        color: {theme['text_muted']};
        font-weight: 500;
    }}

    .stTabs [aria-selected="true"] {{
        color: {theme['primary']} !important;
        border-bottom: 2px solid {theme['primary']} !important;
    }}
</style>
"""

def get_alert_style(alert_type):
    color = ALERT_COLORS.get(alert_type, "#00ff88")
    icon = ALERT_ICONS.get(alert_type, "✅")
    return color, icon

def hex_to_rgba(hex_color, opacity=1.0):
    hex_color = hex_color.lstrip('#')
    lv = len(hex_color)
    rgb = tuple(int(hex_color[i:i + lv // 3], 16) for i in range(0, lv, lv // 3))
    return f'rgba({rgb[0]}, {rgb[1]}, {rgb[2]}, {opacity})'
