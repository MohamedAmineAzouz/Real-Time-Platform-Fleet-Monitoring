"""Dynamic CSS and plot styling for professional analytics themes."""

from __future__ import annotations

from functools import lru_cache

import streamlit as st

from config.settings import get_settings


PALETTES = {
    "dark": {
        "app_bg": "#0b1220",
        "card_bg": "#111b2e",
        "card_alt": "#0f1727",
        "border": "#24324b",
        "text": "#edf2f7",
        "muted": "#94a3b8",
        "accent": "#22c55e",
        "accent_alt": "#38bdf8",
        "warning": "#f59e0b",
        "danger": "#ef4444",
        "shadow": "0 24px 60px rgba(2, 6, 23, 0.35)",
        "plot_bg": "#111827",
        "grid": "rgba(148, 163, 184, 0.14)",
    },
    "light": {
        "app_bg": "#f4f7fb",
        "card_bg": "#ffffff",
        "card_alt": "#eef4fb",
        "border": "#d5deea",
        "text": "#142235",
        "muted": "#55657a",
        "accent": "#0f9d58",
        "accent_alt": "#0284c7",
        "warning": "#d97706",
        "danger": "#dc2626",
        "shadow": "0 18px 50px rgba(15, 23, 42, 0.08)",
        "plot_bg": "#ffffff",
        "grid": "rgba(51, 65, 85, 0.12)",
    },
}


@lru_cache(maxsize=1)
def _css_template() -> str:
    settings = get_settings()
    return settings.css_path.read_text(encoding="utf-8")


def get_palette(mode: str) -> dict[str, str]:
    return PALETTES.get(mode, PALETTES["dark"])


def apply_theme(mode: str) -> dict[str, str]:
    palette = get_palette(mode)
    css = _css_template()
    for key, value in palette.items():
        css = css.replace(f"__{key.upper()}__", value)
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
    return palette


def plotly_axis_style(mode: str) -> dict[str, str]:
    palette = get_palette(mode)
    return {
        "paper_bgcolor": palette["card_bg"],
        "plot_bgcolor": palette["plot_bg"],
        "font_color": palette["text"],
        "gridcolor": palette["grid"],
        "zerolinecolor": palette["grid"],
    }
