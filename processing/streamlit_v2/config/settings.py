"""Typed application settings with environment and YAML support."""

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


def _section(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key, {})
    return value if isinstance(value, dict) else {}


def _env(key: str, default: Any, cast: type = str) -> Any:
    raw_value = os.getenv(key)
    if raw_value is None or raw_value == "":
        return default

    if cast is bool:
        return raw_value.lower() in {"1", "true", "yes", "on"}
    if cast is int:
        return int(raw_value)
    if cast is float:
        return float(raw_value)
    return raw_value


@dataclass(frozen=True)
class AppSettings:
    app_env: str
    app_title: str
    app_icon: str
    default_theme: str
    default_page_size: int
    default_chart_height: int
    default_map_height: int

    cassandra_host: str
    cassandra_port: int
    cassandra_keyspace: str
    cassandra_user: str
    cassandra_pass: str
    cassandra_connect_retries: int
    cassandra_connect_delay_seconds: int

    realtime_cache_ttl_seconds: int
    realtime_refresh_interval_seconds: int
    realtime_default_lookback_minutes: int
    realtime_stale_after_minutes: int

    batch_cache_ttl_seconds: int
    batch_default_range_days: int
    batch_max_range_days: int
    batch_latest_search_days: int

    low_fuel_pct: float
    high_temp_c: float
    overspeed_kmh: float

    map_style_dark: str
    map_style_light: str
    log_level: str

    @property
    def css_path(self) -> Path:
        return APP_ROOT / "assets" / "styles" / "theme.css"


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    config_path = Path(os.getenv("APP_CONFIG_FILE", DEFAULT_CONFIG_FILE))
    raw = _read_yaml(config_path)

    app_cfg = _section(raw, "app")
    realtime_cfg = _section(raw, "realtime")
    batch_cfg = _section(raw, "batch")
    charts_cfg = _section(raw, "charts")
    thresholds_cfg = _section(raw, "thresholds")

    return AppSettings(
        app_env=_env("APP_ENV", "development"),
        app_title=_env("APP_TITLE", app_cfg.get("title", "Fleet Command Center")),
        app_icon=_env("APP_ICON", app_cfg.get("icon", "FC")),
        default_theme=_env("DEFAULT_THEME", app_cfg.get("default_theme", "dark")).lower(),
        default_page_size=_env("DEFAULT_PAGE_SIZE", app_cfg.get("default_page_size", 25), int),
        default_chart_height=_env("DEFAULT_CHART_HEIGHT", charts_cfg.get("default_height", 360), int),
        default_map_height=_env("DEFAULT_MAP_HEIGHT", charts_cfg.get("map_height", 460), int),
        cassandra_host=_env("CASSANDRA_HOST", "cassandra"),
        cassandra_port=_env("CASSANDRA_PORT", 9042, int),
        cassandra_keyspace=_env("CASSANDRA_KEYSPACE", "fleet"),
        cassandra_user=_env("CASSANDRA_USER", ""),
        cassandra_pass=_env("CASSANDRA_PASS", ""),
        cassandra_connect_retries=_env("CASSANDRA_CONNECT_RETRIES", 10, int),
        cassandra_connect_delay_seconds=_env("CASSANDRA_CONNECT_DELAY_SECONDS", 3, int),
        realtime_cache_ttl_seconds=_env(
            "REALTIME_CACHE_TTL_SECONDS",
            realtime_cfg.get("cache_ttl_seconds", 15),
            int,
        ),
        realtime_refresh_interval_seconds=_env(
            "REALTIME_REFRESH_INTERVAL_SECONDS",
            realtime_cfg.get("refresh_interval_seconds", 10),
            int,
        ),
        realtime_default_lookback_minutes=_env(
            "REALTIME_DEFAULT_LOOKBACK_MINUTES",
            realtime_cfg.get("default_lookback_minutes", 30),
            int,
        ),
        realtime_stale_after_minutes=_env(
            "REALTIME_STALE_AFTER_MINUTES",
            realtime_cfg.get("stale_after_minutes", 5),
            int,
        ),
        batch_cache_ttl_seconds=_env(
            "BATCH_CACHE_TTL_SECONDS",
            batch_cfg.get("cache_ttl_seconds", 300),
            int,
        ),
        batch_default_range_days=_env(
            "BATCH_DEFAULT_RANGE_DAYS",
            batch_cfg.get("default_range_days", 7),
            int,
        ),
        batch_max_range_days=_env(
            "BATCH_MAX_RANGE_DAYS",
            batch_cfg.get("max_range_days", 31),
            int,
        ),
        batch_latest_search_days=_env(
            "BATCH_LATEST_SEARCH_DAYS",
            batch_cfg.get("latest_search_days", 30),
            int,
        ),
        low_fuel_pct=_env("LOW_FUEL_PCT", thresholds_cfg.get("low_fuel_pct", 20), float),
        high_temp_c=_env("HIGH_TEMP_C", thresholds_cfg.get("high_temp_c", 100), float),
        overspeed_kmh=_env("OVERSPEED_KMH", thresholds_cfg.get("overspeed_kmh", 120), float),
        map_style_dark=_env("MAP_STYLE_DARK", "carto-darkmatter"),
        map_style_light=_env("MAP_STYLE_LIGHT", "carto-positron"),
        log_level=_env("LOG_LEVEL", "INFO"),
    )
