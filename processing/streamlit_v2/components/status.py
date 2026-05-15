"""Status and state presentation helpers."""

from __future__ import annotations

import streamlit as st


def render_status_banner(message: str, tone: str = "info") -> None:
    st.markdown(
        f"""
        <div class="status-banner tone-{tone}">
            {message}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_empty_state(title: str, message: str) -> None:
    st.markdown(
        f"""
        <div class="empty-state">
            <div class="empty-state-title">{title}</div>
            <div class="empty-state-message">{message}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_exception(error: Exception) -> None:
    st.error("The dashboard could not load its dataset.")
    with st.expander("Technical details"):
        st.exception(error)
