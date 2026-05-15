"""Session state helpers."""

from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

from config.settings import get_settings


def init_app_state() -> None:
    settings = get_settings()
    defaults = {
        "theme_mode": settings.default_theme,
        "realtime_auto_refresh": True,
        "realtime_refresh_interval": settings.realtime_refresh_interval_seconds,
        "realtime_lookback_minutes": settings.realtime_default_lookback_minutes,
        "batch_start_date": date.today() - timedelta(days=settings.batch_default_range_days - 1),
        "batch_end_date": date.today(),
    }

    for key, value in defaults.items():
        st.session_state.setdefault(key, value)
