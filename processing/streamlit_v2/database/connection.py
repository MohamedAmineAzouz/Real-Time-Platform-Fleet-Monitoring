"""Cached Cassandra session lifecycle for Streamlit."""

from __future__ import annotations

import time
from typing import Any

import pandas as pd
import streamlit as st
from cassandra.auth import PlainTextAuthProvider
from cassandra.cluster import Cluster, Session

from config.settings import get_settings
from utils.logging_utils import get_logger


logger = get_logger(__name__)


@st.cache_resource(show_spinner="Connecting to Cassandra cluster...")
def get_session() -> Session:
    settings = get_settings()
    auth_provider = (
        PlainTextAuthProvider(settings.cassandra_user, settings.cassandra_pass)
        if settings.cassandra_user
        else None
    )

    last_error: Exception | None = None
    for attempt in range(1, settings.cassandra_connect_retries + 1):
        try:
            cluster = Cluster(
                [settings.cassandra_host],
                port=settings.cassandra_port,
                auth_provider=auth_provider,
                connect_timeout=10,
            )
            session = cluster.connect(settings.cassandra_keyspace)
            logger.info(
                "Connected to Cassandra host=%s port=%s keyspace=%s",
                settings.cassandra_host,
                settings.cassandra_port,
                settings.cassandra_keyspace,
            )
            return session
        except Exception as exc:
            last_error = exc
            logger.warning("Cassandra not ready (%s/%s): %s", attempt, settings.cassandra_connect_retries, exc)
            time.sleep(settings.cassandra_connect_delay_seconds)

    raise RuntimeError(f"Unable to connect to Cassandra: {last_error}")


def query_dataframe(cql: str, parameters: list[Any] | tuple[Any, ...] | None = None) -> pd.DataFrame:
    session = get_session()
    rows = session.execute(cql, parameters or [])
    records = [row._asdict() for row in rows]
    return pd.DataFrame(records)
