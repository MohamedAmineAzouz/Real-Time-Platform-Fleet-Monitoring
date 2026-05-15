"""Advanced Plotly visualizations for the fleet command center."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from config.settings import get_settings
from utils.theme import get_palette, get_plotly_tokens


settings = get_settings()


def _empty_figure(title: str, theme_mode: str, message: str = "No data available for the selected scope.") -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(
        text=message,
        showarrow=False,
        x=0.5,
        y=0.5,
        xref="paper",
        yref="paper",
        font={"size": 14},
    )
    fig.update_layout(title=title)
    return _style_figure(fig, theme_mode)


def _style_figure(fig: go.Figure, theme_mode: str, height: int | None = None) -> go.Figure:
    tokens = get_plotly_tokens(theme_mode)
    fig.update_layout(
        paper_bgcolor=tokens["paper_bgcolor"],
        plot_bgcolor=tokens["plot_bgcolor"],
        font={"family": "IBM Plex Sans, Segoe UI, sans-serif", "color": tokens["font_color"], "size": 13},
        margin={"l": 18, "r": 18, "t": 54, "b": 18},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1},
        hoverlabel={"font_size": 12},
        height=height or settings.default_chart_height,
    )
    fig.update_xaxes(showgrid=True, gridcolor=tokens["gridcolor"], linecolor=tokens["linecolor"])
    fig.update_yaxes(showgrid=True, gridcolor=tokens["gridcolor"], linecolor=tokens["linecolor"])
    return fig


def speed_distribution_chart(snapshot: pd.DataFrame, theme_mode: str) -> go.Figure:
    if snapshot.empty:
        return _empty_figure("Speed Distribution", theme_mode)
    palette = get_palette(theme_mode)
    fig = px.histogram(
        snapshot,
        x="speed",
        color="severity",
        nbins=18,
        marginal="box",
        title="Live Speed Distribution and Severity Spread",
        color_discrete_map={
            "Normal": palette["accent"],
            "Medium": palette["warning"],
            "High": palette["accent_alt"],
            "Critical": palette["danger"],
        },
    )
    fig.update_layout(bargap=0.08)
    return _style_figure(fig, theme_mode)


def speed_timeline_chart(truck_timeline: pd.DataFrame, theme_mode: str) -> go.Figure:
    if truck_timeline.empty:
        return _empty_figure("Speed Timeline", theme_mode)
    scoped = truck_timeline.copy()
    scoped["buffer_captured_at"] = pd.to_datetime(scoped["buffer_captured_at"], errors="coerce")
    order = (
        scoped.sort_values("buffer_captured_at")
        .groupby("truck_id")
        .tail(1)
        .sort_values("speed", ascending=False)["truck_id"]
        .head(6)
        .tolist()
    )
    scoped = scoped[scoped["truck_id"].isin(order)] if order else scoped
    fig = px.line(
        scoped,
        x="buffer_captured_at",
        y="speed",
        color="truck_label",
        markers=True,
        title="Live Speed Trend by Truck",
        hover_data={"fuel_level": ":.1f", "engine_temp": ":.1f"},
    )
    return _style_figure(fig, theme_mode, height=settings.explorer_chart_height)


def top_fastest_trucks_chart(snapshot: pd.DataFrame, theme_mode: str) -> go.Figure:
    if snapshot.empty:
        return _empty_figure("Top Fastest Trucks", theme_mode)
    palette = get_palette(theme_mode)
    scoped = snapshot.nlargest(10, "speed").sort_values("speed")
    fig = px.bar(
        scoped,
        x="speed",
        y="truck_label",
        orientation="h",
        text="speed",
        color="speed",
        color_continuous_scale=[palette["accent"], palette["accent_alt"], palette["danger"]],
        title="Top Fastest Trucks",
    )
    fig.update_traces(texttemplate="%{text:.1f} km/h", textposition="outside")
    return _style_figure(fig, theme_mode)


def fuel_level_distribution_chart(snapshot: pd.DataFrame, theme_mode: str) -> go.Figure:
    if snapshot.empty:
        return _empty_figure("Fuel Distribution", theme_mode)
    palette = get_palette(theme_mode)
    scoped = snapshot.copy()
    scoped["fuel_band"] = pd.cut(
        scoped["fuel_level"],
        bins=[-1, settings.critical_fuel_pct, settings.low_fuel_pct, 60, 100],
        labels=["Critical", "Low", "Operational", "Healthy"],
    ).astype(str)
    fig = px.histogram(
        scoped,
        x="fuel_level",
        color="fuel_band",
        nbins=16,
        title="Fuel Level Distribution",
        color_discrete_map={
            "Critical": palette["danger"],
            "Low": palette["warning"],
            "Operational": palette["accent_alt"],
            "Healthy": palette["accent"],
        },
    )
    return _style_figure(fig, theme_mode)


def fuel_consumption_ranking_chart(snapshot: pd.DataFrame, theme_mode: str) -> go.Figure:
    if snapshot.empty:
        return _empty_figure("Fuel Consumption Ranking", theme_mode)
    scoped = snapshot.nlargest(10, "fuel_consumption_rate").sort_values("fuel_consumption_rate")
    fig = px.bar(
        scoped,
        x="fuel_consumption_rate",
        y="truck_label",
        orientation="h",
        text="fuel_consumption_rate",
        color="high_consumption_live",
        color_discrete_map={True: "#f59e0b", False: "#38bdf8"},
        title="Fuel Consumption Ranking",
    )
    fig.update_traces(texttemplate="%{text:.1f} L/100km", textposition="outside")
    return _style_figure(fig, theme_mode)


def fuel_efficiency_bubble_chart(snapshot: pd.DataFrame, theme_mode: str) -> go.Figure:
    if snapshot.empty:
        return _empty_figure("Fuel Efficiency Analytics", theme_mode)
    fig = px.scatter(
        snapshot,
        x="speed",
        y="fuel_consumption_rate",
        size="fuel_used",
        color="fuel_efficiency_score",
        hover_name="truck_label",
        hover_data={"driver_id": True, "fuel_level": ":.1f", "engine_temp": ":.1f"},
        color_continuous_scale="Tealgrn",
        title="Fuel Efficiency Analytics",
    )
    return _style_figure(fig, theme_mode)


def refueling_donut_chart(snapshot: pd.DataFrame, theme_mode: str) -> go.Figure:
    if snapshot.empty:
        return _empty_figure("Refueling Overview", theme_mode)
    palette = get_palette(theme_mode)
    scoped = snapshot.copy()
    scoped["fuel_state"] = "Nominal"
    scoped.loc[scoped["fuel_level"] <= settings.low_fuel_pct, "fuel_state"] = "Low Fuel"
    scoped.loc[scoped["refueling"], "fuel_state"] = "Refueling"
    scoped = scoped.groupby("fuel_state", as_index=False).size().rename(columns={"size": "count"})
    fig = px.pie(
        scoped,
        names="fuel_state",
        values="count",
        hole=0.64,
        title="Refueling and Low Fuel Status",
        color="fuel_state",
        color_discrete_map={
            "Nominal": palette["accent"],
            "Low Fuel": palette["warning"],
            "Refueling": palette["accent_alt"],
        },
    )
    return _style_figure(fig, theme_mode)


def engine_temperature_chart(snapshot: pd.DataFrame, theme_mode: str) -> go.Figure:
    if snapshot.empty:
        return _empty_figure("Engine Thermal Analytics", theme_mode)
    palette = get_palette(theme_mode)
    fig = px.scatter(
        snapshot,
        x="speed",
        y="engine_temp",
        size="fuel_level",
        color="severity",
        hover_name="truck_label",
        hover_data={"route_label": True, "fuel_consumption_rate": ":.1f"},
        title="Engine Thermal Analytics",
        color_discrete_map={
            "Normal": palette["accent"],
            "Medium": palette["warning"],
            "High": palette["accent_alt"],
            "Critical": palette["danger"],
        },
    )
    fig.add_hline(y=settings.high_temp_c, line_dash="dot", line_color=palette["warning"])
    fig.add_hline(y=settings.critical_temp_c, line_dash="dash", line_color=palette["danger"])
    return _style_figure(fig, theme_mode)


def engine_health_gauge(snapshot: pd.DataFrame, theme_mode: str) -> go.Figure:
    if snapshot.empty:
        return _empty_figure("Engine Health Score", theme_mode)
    palette = get_palette(theme_mode)
    score = (
        100
        - max(float(snapshot["engine_temp"].mean()) - 72, 0) * 1.2
        - int((snapshot["engine_temp"] >= settings.high_temp_c).sum()) * 4
    )
    score = max(0.0, min(100.0, score))
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=score,
            title={"text": "Engine Health Score"},
            gauge={
                "axis": {"range": [0, 100]},
                "bar": {"color": palette["accent_alt"]},
                "steps": [
                    {"range": [0, 55], "color": "rgba(244, 63, 94, 0.18)"},
                    {"range": [55, 80], "color": "rgba(245, 158, 11, 0.18)"},
                    {"range": [80, 100], "color": "rgba(45, 212, 191, 0.18)"},
                ],
                "threshold": {"line": {"color": palette["danger"], "width": 4}, "value": 55},
            },
        )
    )
    return _style_figure(fig, theme_mode, height=300)


def alert_distribution_chart(alerts: pd.DataFrame, theme_mode: str) -> go.Figure:
    if alerts.empty:
        return _empty_figure("Alert Distribution", theme_mode)
    scoped = alerts.groupby(["title", "severity"], as_index=False).size().rename(columns={"size": "count"})
    palette = get_palette(theme_mode)
    fig = px.bar(
        scoped.sort_values("count"),
        x="count",
        y="title",
        color="severity",
        orientation="h",
        title="Alert Distribution",
        color_discrete_map={
            "Critical": palette["danger"],
            "High": palette["warning"],
            "Medium": palette["accent_alt"],
            "Normal": palette["accent"],
        },
    )
    return _style_figure(fig, theme_mode)


def alert_timeline_chart(alerts: pd.DataFrame, anomalies: pd.DataFrame, theme_mode: str) -> go.Figure:
    frames: list[pd.DataFrame] = []
    if not alerts.empty:
        alert_frame = alerts.copy()
        alert_frame["timestamp"] = pd.to_datetime(alert_frame["timestamp"], errors="coerce").dt.floor("min")
        frames.append(alert_frame[["timestamp", "severity"]])
    if not anomalies.empty:
        anomaly_frame = anomalies.copy()
        anomaly_frame["timestamp"] = pd.to_datetime(anomaly_frame["occurred_at"], errors="coerce").dt.floor("min")
        frames.append(anomaly_frame.rename(columns={"severity": "severity"})[["timestamp", "severity"]])
    if not frames:
        return _empty_figure("Alert Timeline", theme_mode)

    timeline = pd.concat(frames, ignore_index=True)
    timeline = timeline.groupby(["timestamp", "severity"], as_index=False).size().rename(columns={"size": "count"})
    palette = get_palette(theme_mode)
    fig = px.area(
        timeline,
        x="timestamp",
        y="count",
        color="severity",
        title="Alert and Anomaly Timeline",
        color_discrete_map={
            "Critical": palette["danger"],
            "High": palette["warning"],
            "Medium": palette["accent_alt"],
            "Normal": palette["accent"],
        },
    )
    return _style_figure(fig, theme_mode, height=settings.explorer_chart_height)


def anomaly_category_chart(anomalies: pd.DataFrame, theme_mode: str) -> go.Figure:
    if anomalies.empty:
        return _empty_figure("Anomaly Categories", theme_mode)
    scoped = anomalies.groupby("category", as_index=False).size().rename(columns={"size": "count"})
    fig = px.treemap(
        scoped,
        path=["category"],
        values="count",
        color="count",
        color_continuous_scale="Sunsetdark",
        title="AI Anomaly Category Mix",
    )
    return _style_figure(fig, theme_mode)


def problem_truck_score_chart(problem_trucks: pd.DataFrame, theme_mode: str) -> go.Figure:
    if problem_trucks.empty:
        return _empty_figure("Problematic Trucks", theme_mode)
    scoped = problem_trucks.nlargest(10, "anomaly_score").sort_values("anomaly_score")
    fig = px.bar(
        scoped,
        x="anomaly_score",
        y="truck_label",
        orientation="h",
        color="severity",
        text="anomaly_score",
        title="Most Problematic Trucks",
    )
    fig.update_traces(texttemplate="%{text:.0f}", textposition="outside")
    return _style_figure(fig, theme_mode)


def maintenance_type_chart(maintenance_view: pd.DataFrame, theme_mode: str) -> go.Figure:
    if maintenance_view.empty:
        return _empty_figure("Maintenance Types", theme_mode)
    scoped = maintenance_view.copy()
    scoped["maintenance_label"] = scoped["maintenance_type"].replace("", "Observation")
    scoped = scoped.groupby("maintenance_label", as_index=False).size().rename(columns={"size": "count"})
    fig = px.pie(
        scoped,
        names="maintenance_label",
        values="count",
        hole=0.62,
        title="Maintenance Type Distribution",
    )
    return _style_figure(fig, theme_mode)


def predicted_failure_chart(maintenance_view: pd.DataFrame, theme_mode: str) -> go.Figure:
    if maintenance_view.empty:
        return _empty_figure("Predicted Failures", theme_mode)
    scoped = (
        maintenance_view.groupby("predicted_failure_band", as_index=False)
        .size()
        .rename(columns={"size": "truck_count"})
    )
    palette = get_palette(theme_mode)
    fig = px.bar(
        scoped,
        x="predicted_failure_band",
        y="truck_count",
        color="predicted_failure_band",
        title="Predicted Failure Bands",
        color_discrete_map={
            "Stable": palette["accent"],
            "Watch": palette["warning"],
            "Critical": palette["danger"],
        },
    )
    return _style_figure(fig, theme_mode)


def maintenance_timeline_chart(maintenance_timeline: pd.DataFrame, theme_mode: str) -> go.Figure:
    if maintenance_timeline.empty:
        return _empty_figure("Maintenance Timeline", theme_mode)
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Scatter(
            x=maintenance_timeline["timestamp"],
            y=maintenance_timeline["maintenance_trucks"],
            mode="lines+markers",
            name="Maintenance Trucks",
            line={"width": 3},
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=maintenance_timeline["timestamp"],
            y=maintenance_timeline["average_engine_temp"],
            mode="lines+markers",
            name="Avg Engine Temp",
            line={"width": 2, "dash": "dot"},
        ),
        secondary_y=True,
    )
    fig.update_layout(title="Maintenance Load and Thermal Pressure Timeline")
    fig.update_yaxes(title_text="Maintenance Trucks", secondary_y=False)
    fig.update_yaxes(title_text="Avg Engine Temp (C)", secondary_y=True)
    return _style_figure(fig, theme_mode, height=settings.explorer_chart_height)


def streaming_volume_chart(metric_history: pd.DataFrame, theme_mode: str) -> go.Figure:
    if metric_history.empty:
        return _empty_figure("Streaming Throughput", theme_mode)
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Bar(
            x=metric_history["buffer_captured_at"],
            y=metric_history["streaming_events"],
            name="Streaming Events",
            opacity=0.58,
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=metric_history["buffer_captured_at"],
            y=metric_history["active_alerts"],
            name="Active Alerts",
            mode="lines+markers",
        ),
        secondary_y=True,
    )
    fig.add_trace(
        go.Scatter(
            x=metric_history["buffer_captured_at"],
            y=metric_history["average_speed"],
            name="Average Speed",
            mode="lines",
        ),
        secondary_y=True,
    )
    fig.update_layout(title="Streaming Throughput and Alert Pressure")
    fig.update_yaxes(title_text="Events per refresh", secondary_y=False)
    fig.update_yaxes(title_text="Alerts / Speed", secondary_y=True)
    return _style_figure(fig, theme_mode, height=settings.explorer_chart_height)


def engine_temperature_timeline_chart(truck_timeline: pd.DataFrame, theme_mode: str) -> go.Figure:
    if truck_timeline.empty:
        return _empty_figure("Engine Temperature Trend", theme_mode)
    scoped = truck_timeline.copy()
    scoped["buffer_captured_at"] = pd.to_datetime(scoped["buffer_captured_at"], errors="coerce")
    order = (
        scoped.sort_values("buffer_captured_at")
        .groupby("truck_id")
        .tail(1)
        .sort_values("engine_temp", ascending=False)["truck_id"]
        .head(6)
        .tolist()
    )
    scoped = scoped[scoped["truck_id"].isin(order)] if order else scoped
    fig = px.line(
        scoped,
        x="buffer_captured_at",
        y="engine_temp",
        color="truck_label",
        markers=True,
        title="Engine Temperature Trend",
    )
    fig.add_hline(y=settings.high_temp_c, line_dash="dot")
    return _style_figure(fig, theme_mode, height=settings.explorer_chart_height)
