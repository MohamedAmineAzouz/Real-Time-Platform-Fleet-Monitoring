"""Session state bootstrap helpers."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from config.settings import get_settings


def initialize_session_state() -> None:
    settings = get_settings()
    defaults = {
        "theme_mode": settings.default_theme,
        "auto_refresh_enabled": True,
        "force_refresh": False,
        "selected_view": "Command Center",
        "live_snapshot_buffer": pd.DataFrame(),
        "live_snapshot_hash": "",
        "live_snapshot_sequence": 0,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)
