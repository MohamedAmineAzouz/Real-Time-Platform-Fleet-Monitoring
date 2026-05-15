"""Styled dataframe panels."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from components.status import render_empty_state


def render_dataframe_panel(
    title: str,
    frame: pd.DataFrame,
    caption: str | None = None,
    height: int = 320,
) -> None:
    st.markdown(
        f"""
        <div class="table-shell">
            <div class="table-title">{title}</div>
            <div class="table-caption">{caption or ""}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if frame.empty:
        render_empty_state("No rows available", "Adjust the filters or refresh the source data.")
        return

    st.dataframe(frame, use_container_width=True, hide_index=True, height=height)
