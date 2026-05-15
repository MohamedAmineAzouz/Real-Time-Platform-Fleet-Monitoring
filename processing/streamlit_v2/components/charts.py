"""Reusable Plotly chart builders for the analytics platform."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from config.settings import get_settings
from utils.theme import get_palette, plotly_axis_style


settings = get_settings()


def _empty_figure(title: str, theme_mode: str, message: str = "No data available for the selected scope.") -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=message, showarrow=False, font={"size": 14})
    fig.update_layout(title=title)
    return finalize_figure(fig, theme_mode)


def finalize_figure(fig: go.Figure, theme_mode: str, height: int | None = None) -> go.Figure:
    axis_style = plotly_axis_style(theme_mode)
    fig.update_layout(
        paper_bgcolor=axis_style["paper_bgcolor"],
        plot_bgcolor=axis_style["plot_bgcolor"],
        font={"family": "Aptos, Segoe UI, sans-serif", "color": axis_style["font_color"], "size": 13},
        margin={"l": 24, "r": 24, "t": 60, "b": 24},
        height=height or settings.default_chart_height,
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1},
        hoverlabel={"font_size": 12},
    )
    fig.update_xaxes(showgrid=True, gridcolor=axis_style["gridcolor"], zerolinecolor=axis_style["zerolinecolor"])
    fig.update_yaxes(showgrid=True, gridcolor=axis_style["gridcolor"], zerolinecolor=axis_style["zerolinecolor"])
    return fig


def create_indicator_gauge(
    value: float,
    title: str,
    theme_mode: str,
    max_value: float,
    suffix: str,
    threshold: float,
) -> go.Figure:
    palette = get_palette(theme_mode)
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=value,
            number={"suffix": suffix},
            title={"text": title},
            gauge={
                "axis": {"range": [None, max_value]},
                "bar": {"color": palette["accent_alt"]},
                "steps": [
                    {"range": [0, threshold], "color": palette["card_alt"]},
                    {"range": [threshold, max_value], "color": "rgba(245, 158, 11, 0.35)"},
                ],
                "threshold": {"line": {"color": palette["danger"], "width": 4}, "value": threshold},
            },
        )
    )
    return finalize_figure(fig, theme_mode, height=310)


def create_status_donut(frame: pd.DataFrame, theme_mode: str, title: str) -> go.Figure:
    if frame.empty:
        return _empty_figure(title, theme_mode)

    palette = get_palette(theme_mode)
    color_map = {
        "Moving": palette["accent"],
        "Idle": palette["muted"],
        "Maintenance": palette["warning"],
        "Refueling": palette["accent_alt"],
        "Delayed": palette["danger"],
    }
    fig = px.pie(
        frame,
        names="status",
        values="truck_count",
        hole=0.62,
        color="status",
        color_discrete_map=color_map,
        title=title,
    )
    return finalize_figure(fig, theme_mode)


def create_alert_bar(frame: pd.DataFrame, theme_mode: str, title: str) -> go.Figure:
    if frame.empty:
        return _empty_figure(title, theme_mode)

    palette = get_palette(theme_mode)
    fig = px.bar(
        frame.sort_values("count"),
        x="count",
        y="alert_type",
        orientation="h",
        title=title,
        color_discrete_sequence=[palette["warning"]],
        text="count",
    )
    fig.update_traces(textposition="outside")
    return finalize_figure(fig, theme_mode)


def create_speed_temperature_scatter(frame: pd.DataFrame, theme_mode: str, title: str) -> go.Figure:
    if frame.empty:
        return _empty_figure(title, theme_mode)

    scoped = frame.copy()
    scoped["bubble_size"] = scoped["risk_score"].clip(lower=10)
    fig = px.scatter(
        scoped,
        x="speed",
        y="engine_temp",
        size="bubble_size",
        color="alert_type",
        hover_name="truck_label",
        hover_data={"start_city": True, "end_city": True, "fuel_level": ":.1f"},
        title=title,
    )
    return finalize_figure(fig, theme_mode)


def create_city_activity_bar(frame: pd.DataFrame, theme_mode: str, title: str) -> go.Figure:
    if frame.empty:
        return _empty_figure(title, theme_mode)

    palette = get_palette(theme_mode)
    fig = px.bar(
        frame.sort_values("truck_count"),
        x="truck_count",
        y="city",
        orientation="h",
        title=title,
        color_discrete_sequence=[palette["accent_alt"]],
        text="truck_count",
    )
    fig.update_traces(textposition="outside")
    return finalize_figure(fig, theme_mode)


def create_location_map(frame: pd.DataFrame, theme_mode: str, title: str) -> go.Figure:
    scoped = frame.dropna(subset=["latitude", "longitude"]).copy()
    if scoped.empty:
        return _empty_figure(title, theme_mode, "No geospatial coordinates are available.")

    settings = get_settings()
    scoped["map_size"] = scoped["risk_score"].clip(lower=10)
    fig = px.scatter_mapbox(
        scoped,
        lat="latitude",
        lon="longitude",
        color="status",
        size="map_size",
        hover_name="truck_label",
        hover_data={"speed": ":.1f", "fuel_level": ":.1f", "engine_temp": ":.1f", "status": True},
        zoom=4.2,
        title=title,
        height=settings.default_map_height,
    )
    fig.update_layout(
        mapbox_style=settings.map_style_dark if theme_mode == "dark" else settings.map_style_light,
        margin={"l": 10, "r": 10, "t": 60, "b": 10},
    )
    return finalize_figure(fig, theme_mode, height=settings.default_map_height)


def create_trend_combo(frame: pd.DataFrame, theme_mode: str, title: str) -> go.Figure:
    if frame.empty:
        return _empty_figure(title, theme_mode)

    palette = get_palette(theme_mode)
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Bar(
            x=frame["stat_date"],
            y=frame["total_distance_km"],
            name="Distance (km)",
            marker_color=palette["accent_alt"],
            opacity=0.65,
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=frame["stat_date"],
            y=frame["fuel_per_100km"],
            name="Fuel / 100km",
            mode="lines+markers",
            line={"color": palette["warning"], "width": 3},
        ),
        secondary_y=True,
    )
    fig.add_trace(
        go.Scatter(
            x=frame["stat_date"],
            y=frame["total_alerts"],
            name="Alerts",
            mode="lines+markers",
            line={"color": palette["danger"], "width": 2, "dash": "dot"},
        ),
        secondary_y=True,
    )
    fig.update_layout(title=title)
    fig.update_yaxes(title_text="Distance (km)", secondary_y=False)
    fig.update_yaxes(title_text="Efficiency / Alerts", secondary_y=True)
    return finalize_figure(fig, theme_mode, height=390)


def create_efficiency_scatter(frame: pd.DataFrame, theme_mode: str, title: str) -> go.Figure:
    if frame.empty:
        return _empty_figure(title, theme_mode)

    fig = px.scatter(
        frame,
        x="average_speed_kmh",
        y="fuel_per_100km",
        size="total_distance_km",
        color="mean_risk_score",
        hover_name="truck_label",
        hover_data={"alerts_per_100km": ":.2f", "total_alerts": True},
        color_continuous_scale="YlOrRd",
        title=title,
    )
    return finalize_figure(fig, theme_mode)


def create_top_risk_bar(frame: pd.DataFrame, theme_mode: str, title: str, top_n: int = 10) -> go.Figure:
    if frame.empty:
        return _empty_figure(title, theme_mode)

    scoped = frame.nlargest(top_n, "mean_risk_score").sort_values("mean_risk_score")
    fig = px.bar(
        scoped,
        x="mean_risk_score",
        y="truck_label",
        orientation="h",
        color="fuel_per_100km",
        color_continuous_scale="Sunsetdark",
        title=title,
        text="mean_risk_score",
    )
    fig.update_traces(texttemplate="%{text:.1f}", textposition="outside")
    return finalize_figure(fig, theme_mode)


def create_risk_heatmap(matrix: pd.DataFrame, theme_mode: str, title: str) -> go.Figure:
    if matrix.empty:
        return _empty_figure(title, theme_mode)

    fig = go.Figure(
        data=go.Heatmap(
            z=matrix.values,
            x=[str(value) for value in matrix.columns],
            y=matrix.index.tolist(),
            colorscale="YlOrRd",
            colorbar={"title": "Risk"},
        )
    )
    fig.update_layout(title=title)
    return finalize_figure(fig, theme_mode, height=420)


def create_maintenance_driver_chart(frame: pd.DataFrame, theme_mode: str, title: str, top_n: int = 10) -> go.Figure:
    if frame.empty:
        return _empty_figure(title, theme_mode)

    scoped = frame.nlargest(top_n, "maintenance_proxy_score").sort_values("maintenance_proxy_score")
    fig = go.Figure()
    fig.add_trace(go.Bar(x=scoped["truck_label"], y=scoped["overheat_count"], name="Overheat", marker_color="#f97316"))
    fig.add_trace(go.Bar(x=scoped["truck_label"], y=scoped["low_fuel_count"], name="Low Fuel", marker_color="#eab308"))
    fig.add_trace(go.Bar(x=scoped["truck_label"], y=scoped["hours_stopped"], name="Stopped Hours", marker_color="#38bdf8"))
    fig.update_layout(title=title, barmode="stack")
    return finalize_figure(fig, theme_mode)
