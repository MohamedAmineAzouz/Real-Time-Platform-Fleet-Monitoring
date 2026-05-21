import os, time
import pandas as pd
import streamlit as st
from cassandra.cluster import Cluster
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
            return session
        except Exception as exc:
            last_exception = exc
            time.sleep(2)

    raise RuntimeError(
        f"❌ Could not connect to Cassandra after 40 attempts: {last_exception}"
    )

def query_df(cql: str, params=None) -> pd.DataFrame:
    session = get_session()
    rows = session.execute(cql, params or [])
    return pd.DataFrame(rows)
