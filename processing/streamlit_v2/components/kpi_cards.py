"""Reusable KPI card renderer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import streamlit as st


@dataclass(frozen=True)
class KpiCard:
    label: str
    value: str
    delta: str | None = None
    caption: str | None = None
    tone: str = "neutral"


def render_kpi_cards(cards: Sequence[KpiCard]) -> None:
    if not cards:
        return

    columns = st.columns(len(cards))
    for column, card in zip(columns, cards):
        delta_html = f"<div class='kpi-delta'>{card.delta}</div>" if card.delta else ""
        caption_html = f"<div class='kpi-caption'>{card.caption}</div>" if card.caption else ""
        with column:
            st.markdown(
                f"""
                <div class="kpi-card tone-{card.tone}">
                    <div class="kpi-label">{card.label}</div>
                    <div class="kpi-value">{card.value}</div>
                    {delta_html}
                    {caption_html}
                </div>
                """,
                unsafe_allow_html=True,
            )
