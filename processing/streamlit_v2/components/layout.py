"""Layout primitives for a production-style Streamlit experience."""

from __future__ import annotations

from typing import Iterable

import streamlit as st

from config.settings import get_settings


settings = get_settings()


def configure_page(page_title: str) -> None:
    st.set_page_config(
        page_title=f"{page_title} | {settings.app_title}",
        page_icon=":bar_chart:",
        layout="wide",
        initial_sidebar_state="expanded",
        menu_items={
            "About": f"{settings.app_title} delivers enterprise fleet analytics for speed and batch layers.",
        },
    )


def render_sidebar_shell(page_name: str, data_source: str, allow_refresh: bool) -> dict[str, object]:
    with st.sidebar:
        st.markdown(
            f"""
            <div class="brand-shell">
                <div class="brand-badge">{settings.app_icon}</div>
                <div>
                    <div class="brand-eyebrow">Enterprise Analytics</div>
                    <div class="brand-title">{settings.app_title}</div>
                    <div class="brand-subtitle">{page_name}</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        theme_mode = st.selectbox(
            "Theme",
            options=["dark", "light"],
            index=0 if st.session_state.get("theme_mode", settings.default_theme) == "dark" else 1,
            key="theme_mode",
        )

        auto_refresh = False
        refresh_interval = settings.realtime_refresh_interval_seconds
        if allow_refresh:
            auto_refresh = st.toggle(
                "Auto refresh live data",
                value=st.session_state.get("realtime_auto_refresh", True),
                key="realtime_auto_refresh",
            )
            refresh_interval = int(
                st.select_slider(
                    "Refresh cadence (seconds)",
                    options=[5, 10, 15, 30, 60],
                    value=int(st.session_state.get("realtime_refresh_interval", settings.realtime_refresh_interval_seconds)),
                    key="realtime_refresh_interval",
                )
            )

        st.markdown(
            f"""
            <div class="sidebar-card">
                <div class="sidebar-card-title">Data Source</div>
                <div class="sidebar-card-value">{data_source}</div>
                <div class="sidebar-card-subtitle">Environment: {settings.app_env}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.caption("Use page-level filters below to refine the operational scope.")

    return {
        "theme_mode": theme_mode,
        "auto_refresh": auto_refresh,
        "refresh_interval": refresh_interval,
    }


def render_page_header(title: str, subtitle: str, tags: Iterable[str] | None = None) -> None:
    tag_html = "".join(f"<span class='tag-chip'>{tag}</span>" for tag in (tags or []))
    st.markdown(
        f"""
        <div class="page-hero">
            <div class="page-hero-copy">
                <div class="page-overline">Analytics Platform</div>
                <h1>{title}</h1>
                <p>{subtitle}</p>
            </div>
            <div class="page-hero-tags">{tag_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_section_heading(title: str, caption: str | None = None) -> None:
    caption_html = f"<div class='section-caption'>{caption}</div>" if caption else ""
    st.markdown(
        f"""
        <div class="section-heading">
            <div class="section-title">{title}</div>
            {caption_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_footer() -> None:
    st.markdown(
        """
        <div class="footer-shell">
            Fleet Command Center v2 · Streamlit enterprise analytics interface
        </div>
        """,
        unsafe_allow_html=True,
    )
