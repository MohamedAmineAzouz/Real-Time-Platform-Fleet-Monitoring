"""
utils/styles.py
─────────────────────────────────────────────────────────────────────────────
Shared color palette and formatting helpers.
─────────────────────────────────────────────────────────────────────────────
"""

# ── Alert colors (matches Angular frontend) ────────────────────────────────────
ALERT_COLORS = {
    "OVERSPEED":  "#ff9500",
    "OVERHEAT":   "#ff4d4d",
    "FUEL_THEFT": "#ff4d4d",
    "FUEL_LEAK":  "#ffdd00",
    "LOW_FUEL":   "#ff9500",
    "NORMAL":     "#00e676",
}

ALERT_ICONS = {
    "OVERSPEED":  "⚡",
    "OVERHEAT":   "🌡️",
    "FUEL_THEFT": "🚨",
    "FUEL_LEAK":  "💧",
    "LOW_FUEL":   "⛽",
    "NORMAL":     "✅",
}


def alert_color(alert_type: str) -> str:
    return ALERT_COLORS.get(alert_type, "#00e676")


def fmt_pct(val, decimals=1) -> str:
    if val is None:
        return "—"
    return f"{val:.{decimals}f}%"


def fmt_km(val, decimals=0) -> str:
    if val is None:
        return "—"
    return f"{val:,.{decimals}f} km"


def fmt_speed(val) -> str:
    if val is None:
        return "—"
    return f"{val:.1f} km/h"


def fmt_temp(val) -> str:
    if val is None:
        return "—"
    return f"{val:.1f} °C"


def score_color(score: float) -> str:
    """Return a color based on performance score 0-100."""
    if score >= 80:
        return "#00e676"
    if score >= 60:
        return "#ff9500"
    return "#ff4d4d"


CSS = """
<style>
    /* ── Global dark theme overrides ── */
    [data-testid="stMetricValue"]   { font-size: 2rem; font-weight: 700; }
    [data-testid="stMetricLabel"]   { font-size: 0.75rem; letter-spacing: 2px; text-transform: uppercase; }
    [data-testid="stMetricDelta"]   { font-size: 0.85rem; }

    div[data-testid="metric-container"] {
        background: #0d1421;
        border: 1px solid rgba(0, 180, 255, 0.12);
        border-radius: 8px;
        padding: 16px 20px;
    }

    /* ── Sidebar ── */
    [data-testid="stSidebar"] {
        background: #0d1421;
        border-right: 1px solid rgba(0, 180, 255, 0.12);
    }

    /* ── Tables ── */
    [data-testid="stDataFrame"] { border-radius: 8px; }

    /* ── Alert pill ── */
    .alert-pill {
        display: inline-block;
        padding: 2px 10px;
        border-radius: 20px;
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 1px;
        color: #000;
    }
</style>
"""