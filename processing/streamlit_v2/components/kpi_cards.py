"""Custom KPI cards with inline sparklines and trend styling."""

from __future__ import annotations

import html
from typing import Sequence

import streamlit as st

from utils.formatters import format_delta, format_metric


TONE_CLASS = {
    "primary": "tone-primary",
    "warning": "tone-warning",
    "danger": "tone-danger",
}


def _sparkline_svg(points: Sequence[float]) -> str:
    values = [float(value) for value in points] if points else [0.0]
    if len(values) == 1:
        values = values * 2
    minimum, maximum = min(values), max(values)
    span = maximum - minimum or 1.0
    coordinates = []
    for index, value in enumerate(values):
        x = index / max(len(values) - 1, 1) * 100
        y = 28 - (((value - minimum) / span) * 24)
        coordinates.append(f"{x:.2f},{y:.2f}")
    return (
        "<svg viewBox='0 0 100 28' preserveAspectRatio='none' class='sparkline-svg'>"
        f"<polyline fill='none' stroke='currentColor' stroke-width='2.5' points='{' '.join(coordinates)}'></polyline>"
        "</svg>"
    )


def render_kpi_cards(kpis: Sequence[dict[str, object]]) -> None:
    """Render KPI cards in a responsive 5-column grid."""
    if not kpis:
        return

    for row_start in range(0, len(kpis), 5):
        row = kpis[row_start : row_start + 5]
        columns = st.columns(len(row))
        for column, kpi in zip(columns, row):
            delta_pct = float(kpi.get("delta_pct", 0.0))
            delta_class = "delta-up" if delta_pct >= 0 else "delta-down"
            tone_class = TONE_CLASS.get(str(kpi.get("tone", "primary")), "tone-primary")
            value = kpi.get("value", 0)
            suffix = str(kpi.get("suffix", ""))
            display_value = value if isinstance(value, str) else format_metric(value, suffix=suffix)
            if isinstance(value, str) and suffix and not str(value).endswith(suffix):
                display_value = f"{value}{suffix}"
            with column:
                st.markdown(
                    f"""
                    <div class="kpi-card {tone_class}">
                        <div class="kpi-card-top">
                            <div class="kpi-icon">{html.escape(str(kpi.get("icon", "KPI")))}</div>
                            <div class="kpi-trend {delta_class}">
                                <span>{'▲' if delta_pct >= 0 else '▼'}</span>
                                <span>{format_delta(delta_pct)}</span>
                            </div>
                        </div>
                        <div class="kpi-label">{html.escape(str(kpi.get("label", "")))}</div>
                        <div class="kpi-value">{html.escape(str(display_value))}</div>
                        <div class="kpi-sparkline">{_sparkline_svg(kpi.get('sparkline', [0.0]))}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
