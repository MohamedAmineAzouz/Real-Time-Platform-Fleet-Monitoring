"""Theme palette, CSS injection, and Plotly tokens."""

from __future__ import annotations

from functools import lru_cache

import streamlit as st

from config.settings import get_settings


settings = get_settings()


DARK_PALETTE = {
    "app_bg": "#06111f",
    "bg_gradient_1": "rgba(45, 212, 191, 0.14)",
    "bg_gradient_2": "rgba(59, 130, 246, 0.08)",
    "glass": "rgba(9, 19, 35, 0.82)",
    "glass_soft": "rgba(16, 28, 48, 0.62)",
    "card_bg": "rgba(8, 19, 35, 0.78)",
    "card_bg_alt": "rgba(14, 28, 47, 0.84)",
    "sidebar_bg": "rgba(5, 14, 27, 0.92)",
    "border": "rgba(148, 163, 184, 0.18)",
    "text": "#f8fafc",
    "muted": "#94a3b8",
    "primary": "#38bdf8",
    "accent": "#2dd4bf",
    "accent_alt": "#60a5fa",
    "success": "#22c55e",
    "warning": "#f59e0b",
    "danger": "#f43f5e",
    "shadow": "0 24px 64px rgba(2, 8, 23, 0.42)",
    "card_glow": "0 0 0 1px rgba(56, 189, 248, 0.08), 0 24px 64px rgba(2, 8, 23, 0.48)",
    "grid": "rgba(148, 163, 184, 0.14)",
    "plot_bg": "rgba(10, 22, 39, 0.96)",
}

LIGHT_PALETTE = {
    "app_bg": "#edf3fb",
    "bg_gradient_1": "rgba(45, 212, 191, 0.12)",
    "bg_gradient_2": "rgba(59, 130, 246, 0.10)",
    "glass": "rgba(255, 255, 255, 0.82)",
    "glass_soft": "rgba(241, 245, 249, 0.82)",
    "card_bg": "rgba(255, 255, 255, 0.88)",
    "card_bg_alt": "rgba(248, 250, 252, 0.94)",
    "sidebar_bg": "rgba(245, 248, 252, 0.96)",
    "border": "rgba(100, 116, 139, 0.16)",
    "text": "#08111c",
    "muted": "#475569",
    "primary": "#0284c7",
    "accent": "#0f766e",
    "accent_alt": "#2563eb",
    "success": "#15803d",
    "warning": "#b45309",
    "danger": "#be123c",
    "shadow": "0 20px 48px rgba(15, 23, 42, 0.10)",
    "card_glow": "0 0 0 1px rgba(37, 99, 235, 0.04), 0 20px 48px rgba(15, 23, 42, 0.10)",
    "grid": "rgba(100, 116, 139, 0.12)",
    "plot_bg": "rgba(255, 255, 255, 0.98)",
}


@lru_cache(maxsize=1)
def _css_template() -> str:
    return settings.css_path.read_text(encoding="utf-8")


def apply_theme(theme_mode: str) -> None:
    css = _css_template()
    for key, value in get_palette(theme_mode).items():
        css = css.replace(f"__{key.upper()}__", value)
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def get_palette(theme_mode: str | None = None) -> dict[str, str]:
    mode = (theme_mode or st.session_state.get("theme_mode") or settings.default_theme).lower()
    return (LIGHT_PALETTE if mode == "light" else DARK_PALETTE).copy()


def get_plotly_tokens(theme_mode: str | None = None) -> dict[str, str]:
    palette = get_palette(theme_mode)
    return {
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": palette["plot_bg"],
        "font_color": palette["text"],
        "gridcolor": palette["grid"],
        "linecolor": palette["border"],
    }
