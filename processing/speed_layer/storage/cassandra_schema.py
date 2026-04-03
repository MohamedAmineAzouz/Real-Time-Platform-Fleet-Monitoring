"""
cassandra_schema.py
─────────────────────────────────────────────────────────────────────────────
Creates the fleet keyspace and all tables. Safe to re-run (IF NOT EXISTS).

New columns added:
  fuel_consumed_trip  — total % fuel consumed since last refuel (simulator-computed)
  fuel_refueled       — total % fuel added during current/last refuel event
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

    # ── drivers ───────────────────────────────────────────────────────────────
    f"""
    CREATE TABLE IF NOT EXISTS {CASSANDRA_KEYSPACE}.drivers (
        driver_id               text,
        name                    text,
        license_number          text,
        phone                   text,
        status                  text,
        current_truck_id        int,
        created_at              timestamp,
        updated_at              timestamp,
        PRIMARY KEY (driver_id)
    )
    """,

    # ── trucks ────────────────────────────────────────────────────────────────
    f"""
    CREATE TABLE IF NOT EXISTS {CASSANDRA_KEYSPACE}.trucks (
        truck_id                int,
        license_plate           text,
        model                   text,
        year                    int,
        status                  text,
        fuel_capacity           double,
        max_load_kg             double,
        created_at              timestamp,
        updated_at              timestamp,
        PRIMARY KEY (truck_id)
    )
    """,

    # ── trajets ───────────────────────────────────────────────────────────────
    f"""
    CREATE TABLE IF NOT EXISTS {CASSANDRA_KEYSPACE}.trajets (
        trajet_id               uuid,
        start_city              text,
        end_city                text,
        distance_km             double,
        created_at              timestamp,
        updated_at              timestamp,
        PRIMARY KEY (trajet_id)
    )
    """,

    # ── maintenance_schedules ─────────────────────────────────────────────────
    f"""
    CREATE TABLE IF NOT EXISTS {CASSANDRA_KEYSPACE}.maintenance_schedules (
        schedule_id             uuid,
        truck_id                int,
        maintenance_type        text,
        description             text,
        scheduled_start         timestamp,
        scheduled_end           timestamp,
        assigned_mechanic       text,
        cost                    double,
        created_at              timestamp,
        updated_at              timestamp,
        PRIMARY KEY (schedule_id)
    )
    """,

    # ── truck_latest ──────────────────────────────────────────────────────────
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
        fuel_consumed_trip      double,
        fuel_refueled           double,
        PRIMARY KEY (truck_id)
    )
    """,

    # ── truck_history ─────────────────────────────────────────────────────────
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
        fuel_consumed_trip      double,
        fuel_refueled           double,
        PRIMARY KEY (truck_id, processed_at)
    ) WITH CLUSTERING ORDER BY (processed_at DESC)
      AND default_time_to_live = 86400
    """,

    # ── alerts ────────────────────────────────────────────────────────────────
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
        fuel_consumed_trip      double,
        fuel_refueled           double,
        PRIMARY KEY ((truck_id, alert_type), processed_at)
    ) WITH CLUSTERING ORDER BY (processed_at DESC)
      AND default_time_to_live = 604800
    """,
]

# ── ALTER TABLE for existing deployments ──────────────────────────────────────
# If the tables already exist, ADD COLUMN is idempotent (IF NOT EXISTS not
# supported in older Cassandra, so we catch and ignore AlreadyExists errors).
ALTER_DDL = [
    f"ALTER TABLE {CASSANDRA_KEYSPACE}.truck_latest  ADD fuel_consumed_trip double",
    f"ALTER TABLE {CASSANDRA_KEYSPACE}.truck_latest  ADD fuel_refueled      double",
    f"ALTER TABLE {CASSANDRA_KEYSPACE}.truck_history ADD fuel_consumed_trip double",
    f"ALTER TABLE {CASSANDRA_KEYSPACE}.truck_history ADD fuel_refueled      double",
    f"ALTER TABLE {CASSANDRA_KEYSPACE}.alerts        ADD fuel_consumed_trip double",
    f"ALTER TABLE {CASSANDRA_KEYSPACE}.alerts        ADD fuel_refueled      double",
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
        # Create tables
        for ddl in DDL:
            stmt = ddl.strip()
            if not stmt:
                continue
            label = stmt.split("\n")[0].strip()[:72]
            print(f"  ▶ {label}")
            session.execute(stmt)

        # Add new columns to existing tables (safe if already exists)
        print("  ▶ Adding fuel_consumed_trip / fuel_refueled columns (if missing)...")
        for alter in ALTER_DDL:
            try:
                session.execute(alter)
                print(f"    ✅ {alter.split('ADD')[1].strip()}")
            except Exception:
                pass   # column already exists — ignore

        print(f"✅ Schema ready — tables: drivers, trucks, trajets, truck_latest, truck_history, alerts")
    finally:
        cluster.shutdown()


if __name__ == "__main__":
    init_cassandra_schema()