"""
batch_schema.py
─────────────────────────────────────────────────────────────────────────────
Cassandra schema for batch layer result tables (dev sink).

Run once before first batch job execution:
  python3 batch_schema.py

In staging/prod these tables don't exist — BigQuery creates them automatically
from the DataFrame schema on first write.
─────────────────────────────────────────────────────────────────────────────
"""

import os
import time
from cassandra.cluster import Cluster
from cassandra.policies import DCAwareRoundRobinPolicy

CASSANDRA_HOST     = os.getenv("CASSANDRA_HOST",     "cassandra")
CASSANDRA_PORT     = os.getenv("CASSANDRA_PORT",     "9042")
CASSANDRA_KEYSPACE = os.getenv("CASSANDRA_KEYSPACE", "fleet")
CASSANDRA_USER     = os.getenv("CASSANDRA_USER",     "")
CASSANDRA_PASS     = os.getenv("CASSANDRA_PASS",     "")

SCHEMA = [

    # ── Job 1: daily truck stats ───────────────────────────────────────────────
    f"""
    CREATE TABLE IF NOT EXISTS {CASSANDRA_KEYSPACE}.batch_daily_truck_stats (
        stat_date          TEXT,
        truck_id           INT,
        total_distance_km  DOUBLE,
        total_fuel_consumed_l DOUBLE,
        fuel_per_100km     DOUBLE,
        avg_speed_kmh      DOUBLE,
        max_speed_kmh      DOUBLE,
        total_alerts       INT,
        overspeed_count    INT,
        overheat_count     INT,
        fuel_theft_count   INT,
        low_fuel_count     INT,
        event_count        BIGINT,
        PRIMARY KEY ((stat_date), truck_id)
    ) WITH CLUSTERING ORDER BY (truck_id ASC)
    AND default_time_to_live = 2592000;
    """,
    # TTL: 30 days — batch results are historical, keep 30 days in Cassandra
    # (full history lives in Parquet on MinIO/GCS)

    # ── Job 2: driver performance ──────────────────────────────────────────────
    f"""
    CREATE TABLE IF NOT EXISTS {CASSANDRA_KEYSPACE}.batch_driver_performance (
        stat_date              TEXT,
        driver_id              TEXT,
        total_events           BIGINT,
        total_distance_km      DOUBLE,
        total_fuel_l           DOUBLE,
        avg_speed              DOUBLE,
        max_speed              DOUBLE,
        speed_compliance_rate  DOUBLE,
        alert_rate_per_100     DOUBLE,
        fuel_per_100km         DOUBLE,
        theft_events           INT,
        speed_score            DOUBLE,
        fuel_score             DOUBLE,
        alert_score            DOUBLE,
        distance_score         DOUBLE,
        performance_score      DOUBLE,
        fleet_rank             INT,
        PRIMARY KEY ((stat_date), performance_score, driver_id)
    ) WITH CLUSTERING ORDER BY (performance_score DESC, driver_id ASC)
    AND default_time_to_live = 2592000;
    """,

    # ── Job 3a: fuel waste anomalies ───────────────────────────────────────────
    f"""
    CREATE TABLE IF NOT EXISTS {CASSANDRA_KEYSPACE}.batch_fuel_waste_anomalies (
        stat_date                   TEXT,
        truck_id                    INT,
        total_distance_km           DOUBLE,
        total_fuel_l                DOUBLE,
        fuel_per_100km              DOUBLE,
        fleet_median_fuel_per_100km DOUBLE,
        anomaly_threshold           DOUBLE,
        waste_vs_median_pct         DOUBLE,
        is_anomaly                  BOOLEAN,
        event_count                 BIGINT,
        PRIMARY KEY ((stat_date), truck_id)
    ) WITH default_time_to_live = 2592000;
    """,

    # ── Job 3b: maintenance flags ──────────────────────────────────────────────
    f"""
    CREATE TABLE IF NOT EXISTS {CASSANDRA_KEYSPACE}.batch_maintenance_flags (
        stat_date                TEXT,
        truck_id                 INT,
        avg_engine_temp          DOUBLE,
        max_engine_temp          DOUBLE,
        max_odometer_km          DOUBLE,
        avg_fuel_rate            DOUBLE,
        fuel_rate_stddev         DOUBLE,
        overheat_count           INT,
        theft_count              INT,
        event_count              BIGINT,
        flag_high_temp           BOOLEAN,
        flag_overheat_alerts     BOOLEAN,
        flag_odometer_milestone  BOOLEAN,
        flag_fuel_inconsistency  BOOLEAN,
        maintenance_needed       BOOLEAN,
        priority                 TEXT,
        PRIMARY KEY ((stat_date), priority, truck_id)
    ) WITH CLUSTERING ORDER BY (priority ASC, truck_id ASC)
    AND default_time_to_live = 2592000;
    """,

    # ── Job 4: route efficiency ────────────────────────────────────────────────
    f"""
    CREATE TABLE IF NOT EXISTS {CASSANDRA_KEYSPACE}.batch_route_efficiency (
        stat_date               TEXT,
        start_city              TEXT,
        end_city                TEXT,
        total_trips             BIGINT,
        avg_distance_km         DOUBLE,
        avg_fuel_l              DOUBLE,
        avg_fuel_per_100km      DOUBLE,
        avg_speed_kmh           DOUBLE,
        avg_duration_min        DOUBLE,
        avg_alerts_per_trip     DOUBLE,
        most_efficient_truck    INT,
        most_efficient_driver   TEXT,
        best_fuel_per_100km     DOUBLE,
        PRIMARY KEY ((stat_date), start_city, end_city)
    ) WITH CLUSTERING ORDER BY (start_city ASC, end_city ASC)
    AND default_time_to_live = 2592000;
    """,
]


def create_schema():
    from cassandra.cluster import Cluster
    from cassandra.auth import PlainTextAuthProvider

    # cluster = Cluster(
    #     [CASSANDRA_HOST],
    #     port=CASSANDRA_PORT,
    #     load_balancing_policy=DCAwareRoundRobinPolicy(local_dc="dc1"),
    #     protocol_version=5,
    # )
    # session = cluster.connect()

    auth = PlainTextAuthProvider(CASSANDRA_USER, CASSANDRA_PASS) if CASSANDRA_USER else None

    for attempt in range(1, 40 + 1):
        try:
            cluster = Cluster(
                [CASSANDRA_HOST],
                port=int(CASSANDRA_PORT),
                auth_provider=auth,
                connect_timeout=10,
            )
            session = cluster.connect()
            print("✅ Cassandra is ready")
            break
        
        except Exception as exc:
            print(f"⏳ Cassandra not ready ({attempt}/{40}): {exc}")
            time.sleep(5)
            
    print(f"Connected to Cassandra at {CASSANDRA_HOST}:{CASSANDRA_PORT}")

    for statement in SCHEMA:
        clean = statement.strip()
        table_name = clean.split(f"{CASSANDRA_KEYSPACE}.")[1].split(" ")[0] if f"{CASSANDRA_KEYSPACE}." in clean else "?"
        session.execute(clean)
        print(f"  ✅ {table_name}")

    session.shutdown()
    cluster.shutdown()
    print("\nBatch schema ready.")


if __name__ == "__main__":
    create_schema()