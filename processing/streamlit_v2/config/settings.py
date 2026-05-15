"""Typed settings for the fleet command center."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


APP_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_FILE = APP_ROOT / "config" / "app_config.yaml"

load_dotenv(APP_ROOT / ".env", override=False)


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _section(config: dict[str, Any], key: str) -> dict[str, Any]:
    value = config.get(key, {})
    return value if isinstance(value, dict) else {}


def _env(key: str, default: Any, cast: type = str) -> Any:
    raw = os.getenv(key)
    if raw is None or raw == "":
        return default
    if cast is bool:
        return raw.lower() in {"1", "true", "yes", "on"}
    if cast is int:
        return int(raw)
    if cast is float:
        return float(raw)
    return raw


@dataclass(frozen=True)
class AppSettings:
    app_title: str
    app_subtitle: str
    page_icon: str
    default_theme: str
    refresh_interval_seconds: int
    refresh_cache_ttl_seconds: int
    max_buffer_snapshots: int
    stale_after_seconds: int
    cassandra_host: str
    cassandra_port: int
    cassandra_keyspace: str
    cassandra_user: str
    cassandra_pass: str
    cassandra_retries: int
    cassandra_delay_seconds: int
    overspeed_kmh: float
    critical_speed_kmh: float
    low_fuel_pct: float
    critical_fuel_pct: float
    high_temp_c: float
    critical_temp_c: float
    suspicious_fuel_drop_pct: float
    gps_jump_speed_kmh: float
    no_movement_distance_km: float
    map_latitude: float
    map_longitude: float
    map_zoom: float
    map_pitch: int
    default_chart_height: int
    explorer_chart_height: int
    map_height: int
    log_level: str

    @property
    def logo_path(self) -> Path:
        return APP_ROOT / "assets" / "logo.svg"

    @property
    def css_path(self) -> Path:
        return APP_ROOT / "styles" / "theme.css"


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    raw = _read_yaml(Path(os.getenv("APP_CONFIG_FILE", DEFAULT_CONFIG_FILE)))
    app_cfg = _section(raw, "app")
    refresh_cfg = _section(raw, "refresh")
    map_cfg = _section(raw, "map")
    thresholds_cfg = _section(raw, "thresholds")
    charts_cfg = _section(raw, "charts")

    return AppSettings(
        app_title=_env("APP_TITLE", app_cfg.get("title", "Fleet Command Center")),
        app_subtitle=_env("APP_SUBTITLE", app_cfg.get("subtitle", "Speed Layer Streaming Command Center")),
        page_icon=_env("APP_PAGE_ICON", app_cfg.get("page_icon", ":truck:")),
        default_theme=_env("APP_THEME", app_cfg.get("theme", "dark")).lower(),
        refresh_interval_seconds=_env("REFRESH_INTERVAL_SECONDS", refresh_cfg.get("interval_seconds", 5), int),
        refresh_cache_ttl_seconds=_env("CACHE_TTL_SECONDS", refresh_cfg.get("cache_ttl_seconds", 5), int),
        max_buffer_snapshots=_env("MAX_BUFFER_SNAPSHOTS", refresh_cfg.get("buffer_snapshots", 72), int),
        stale_after_seconds=_env("STALE_AFTER_SECONDS", refresh_cfg.get("stale_after_seconds", 25), int),
        cassandra_host=_env("CASSANDRA_HOST", "cassandra"),
        cassandra_port=_env("CASSANDRA_PORT", 9042, int),
        cassandra_keyspace=_env("CASSANDRA_KEYSPACE", "fleet"),
        cassandra_user=_env("CASSANDRA_USER", ""),
        cassandra_pass=_env("CASSANDRA_PASS", ""),
        cassandra_retries=_env("CASSANDRA_CONNECT_RETRIES", 12, int),
        cassandra_delay_seconds=_env("CASSANDRA_CONNECT_DELAY_SECONDS", 3, int),
        overspeed_kmh=_env("OVERSPEED_KMH", thresholds_cfg.get("overspeed_kmh", 120), float),
        critical_speed_kmh=_env("CRITICAL_SPEED_KMH", thresholds_cfg.get("critical_speed_kmh", 145), float),
        low_fuel_pct=_env("LOW_FUEL_PCT", thresholds_cfg.get("low_fuel_pct", 20), float),
        critical_fuel_pct=_env("CRITICAL_FUEL_PCT", thresholds_cfg.get("critical_fuel_pct", 10), float),
        high_temp_c=_env("HIGH_TEMP_C", thresholds_cfg.get("high_temp_c", 100), float),
        critical_temp_c=_env("CRITICAL_TEMP_C", thresholds_cfg.get("critical_temp_c", 112), float),
        suspicious_fuel_drop_pct=_env(
            "SUSPICIOUS_FUEL_DROP_PCT",
            thresholds_cfg.get("suspicious_fuel_drop_pct", 6),
            float,
        ),
        gps_jump_speed_kmh=_env("GPS_JUMP_SPEED_KMH", thresholds_cfg.get("gps_jump_speed_kmh", 155), float),
        no_movement_distance_km=_env(
            "NO_MOVEMENT_DISTANCE_KM",
            thresholds_cfg.get("no_movement_distance_km", 0.05),
            float,
        ),
        map_latitude=_env("MAP_LATITUDE", map_cfg.get("latitude", 33.88), float),
        map_longitude=_env("MAP_LONGITUDE", map_cfg.get("longitude", -6.85), float),
        map_zoom=_env("MAP_ZOOM", map_cfg.get("zoom", 4.8), float),
        map_pitch=_env("MAP_PITCH", map_cfg.get("pitch", 38), int),
        default_chart_height=_env("DEFAULT_CHART_HEIGHT", charts_cfg.get("default_height", 330), int),
        explorer_chart_height=_env("EXPLORER_CHART_HEIGHT", charts_cfg.get("explorer_height", 360), int),
        map_height=_env("MAP_HEIGHT", charts_cfg.get("map_height", 520), int),
        log_level=_env("LOG_LEVEL", "INFO"),
    )
