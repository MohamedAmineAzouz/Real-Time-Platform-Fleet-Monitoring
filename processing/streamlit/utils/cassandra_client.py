"""
utils/cassandra_client.py
─────────────────────────────────────────────────────────────────────────────
Shared Cassandra connection for all Streamlit pages.
Uses st.cache_resource so the connection is created once per session.
─────────────────────────────────────────────────────────────────────────────
"""

import os, time
import pandas as pd
import streamlit as st
from cassandra.cluster import Cluster
from cassandra.policies import DCAwareRoundRobinPolicy
from cassandra.auth import PlainTextAuthProvider


CASSANDRA_HOST     = os.getenv("CASSANDRA_HOST",     "cassandra")
CASSANDRA_PORT     = int(os.getenv("CASSANDRA_PORT", "9042"))
CASSANDRA_KEYSPACE = os.getenv("CASSANDRA_KEYSPACE", "fleet")
CASSANDRA_USER     = os.getenv("CASSANDRA_USER",     "")
CASSANDRA_PASS     = os.getenv("CASSANDRA_PASS",     "")


@st.cache_resource(show_spinner="Connecting to Cassandra...")
def get_session():
    auth = (
        PlainTextAuthProvider(CASSANDRA_USER, CASSANDRA_PASS)
        if CASSANDRA_USER else None
    )

    last_exception = None

    for attempt in range(1, 41):
        try:
            cluster = Cluster(
                [CASSANDRA_HOST],
                port=CASSANDRA_PORT,
                auth_provider=auth,
                connect_timeout=10,
            )
            session = cluster.connect(CASSANDRA_KEYSPACE)
            print("✅ Connected to Cassandra")
            return session

        except Exception as exc:
            last_exception = exc
            print(f"⏳ Cassandra not ready ({attempt}/40): {exc}")
            time.sleep(5)

    # 🚨 VERY IMPORTANT
    raise RuntimeError(
        f"❌ Could not connect to Cassandra after 40 attempts: {last_exception}"
    )
    

def query_df(cql: str, params=None) -> pd.DataFrame:
    """Execute a CQL query and return results as a DataFrame."""
    session = get_session()
    rows = session.execute(cql, params or [])
    return pd.DataFrame(rows)