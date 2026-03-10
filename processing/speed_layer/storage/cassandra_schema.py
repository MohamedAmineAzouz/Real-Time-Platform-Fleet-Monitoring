"""
cassandra_schema.py
─────────────────────────────────────────────────────────────────────────────
Creates the fleet keyspace and all tables. Safe to re-run (IF NOT EXISTS).

Tables:
  truck_latest   — one row per truck (live map + current metrics)
  truck_history  — full 24h time-series per truck (charts + telemetry)
  alerts         — all alert events, 7 day TTL (alerts dashboard)
─────────────────────────────────────────────────────────────────────────────
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config.cassandra_config import (
    CASSANDRA_HOST, CASSANDRA_PORT, CASSANDRA_KEYSPACE,
    CASSANDRA_USER, CASSANDRA_PASS,
)

DDL = [

    f"""
    CREATE KEYSPACE IF NOT EXISTS {CASSANDRA_KEYSPACE}
    WITH replication = {{'class': 'SimpleStrategy', 'replication_factor': '1'}}
    AND durable_writes = true
    """,

    # ── truck_latest ──────────────────────────────────────────────────────────
    # One row per truck_id. Every INSERT overwrites the previous row (upsert).
    # No TTL — we always want the last known state for the live map.
    f"""
    CREATE TABLE IF NOT EXISTS {CASSANDRA_KEYSPACE}.truck_latest (
        truck_id                int,
        processed_at            timestamp,
        event_time              timestamp,
        latitude                double,
        longitude               double,
        speed                   double,
        fuel_level              double,
        engine_temp             double,
        driver_id               text,
        start_city              text,
        end_city                text,
        odometer_km             double,
        refueling               boolean,
        refuel_city             text,
        anomaly                 text,
        theft                   boolean,
        theft_amount            double,
        alert_type              text,
        is_alert                boolean,
        distance_km             double,
        fuel_used               double,
        fuel_consumption_rate   double,
        high_consumption        boolean,
        PRIMARY KEY (truck_id)
    )
    """,

    # ── truck_history ─────────────────────────────────────────────────────────
    # Full time-series. Partitioned by truck_id, newest-first.
    # TTL 86400s = 24 hours.
    f"""
    CREATE TABLE IF NOT EXISTS {CASSANDRA_KEYSPACE}.truck_history (
        truck_id                int,
        processed_at            timestamp,
        event_time              timestamp,
        latitude                double,
        longitude               double,
        speed                   double,
        fuel_level              double,
        engine_temp             double,
        driver_id               text,
        start_city              text,
        end_city                text,
        odometer_km             double,
        refueling               boolean,
        refuel_city             text,
        anomaly                 text,
        theft                   boolean,
        theft_amount            double,
        alert_type              text,
        is_alert                boolean,
        distance_km             double,
        fuel_used               double,
        fuel_consumption_rate   double,
        high_consumption        boolean,
        PRIMARY KEY (truck_id, processed_at)
    ) WITH CLUSTERING ORDER BY (processed_at DESC)
      AND default_time_to_live = 86400
    """,

    # ── alerts ────────────────────────────────────────────────────────────────
    # Partitioned by (truck_id, alert_type) for dashboard queries like
    # "all OVERSPEED events for truck 3".
    # TTL 604800s = 7 days.
    f"""
    CREATE TABLE IF NOT EXISTS {CASSANDRA_KEYSPACE}.alerts (
        truck_id                int,
        alert_type              text,
        processed_at            timestamp,
        event_time              timestamp,
        latitude                double,
        longitude               double,
        speed                   double,
        fuel_level              double,
        engine_temp             double,
        driver_id               text,
        anomaly                 text,
        theft                   boolean,
        theft_amount            double,
        distance_km             double,
        fuel_consumption_rate   double,
        PRIMARY KEY ((truck_id, alert_type), processed_at)
    ) WITH CLUSTERING ORDER BY (processed_at DESC)
      AND default_time_to_live = 604800
    """,
]


def _connect(retries: int = 40, delay: int = 5):
    from cassandra.cluster import Cluster
    from cassandra.auth import PlainTextAuthProvider

    auth = PlainTextAuthProvider(CASSANDRA_USER, CASSANDRA_PASS) if CASSANDRA_USER else None

    for attempt in range(1, retries + 1):
        try:
            cluster = Cluster(
                [CASSANDRA_HOST],
                port=int(CASSANDRA_PORT),
                auth_provider=auth,
                connect_timeout=10,
            )
            session = cluster.connect()
            print("✅ Cassandra is ready")
            return session, cluster
        except Exception as exc:
            print(f"⏳ Cassandra not ready ({attempt}/{retries}): {exc}")
            time.sleep(delay)

    raise RuntimeError("❌ Cassandra did not become ready in time")


def init_cassandra_schema():
    print(f"  Host     : {CASSANDRA_HOST}:{CASSANDRA_PORT}")
    print(f"  Keyspace : {CASSANDRA_KEYSPACE}")

    session, cluster = _connect()
    try:
        for ddl in DDL:
            stmt = ddl.strip()
            if not stmt:
                continue
            label = stmt.split("\n")[0].strip()[:72]
            print(f"  ▶ {label}")
            session.execute(stmt)
        print(f"✅ Cassandra schema ready — tables: truck_latest, truck_history, alerts")
    finally:
        cluster.shutdown()


if __name__ == "__main__":
    init_cassandra_schema()