"""
dags/generate_march_history_dag.py
─────────────────────────────────────────────────────────────────────────────
DAG to populate `fleet.truck_history` with realistic data for March 2026.
Airflow 3 Compatible.
─────────────────────────────────────────────────────────────────────────────
"""

import random, os
from datetime import datetime, timedelta

from airflow.sdk import dag, task

# ── Configuration ─────────────────────────────────────────────────────────
CASSANDRA_HOST     = os.getenv("CASSANDRA_HOST",     "cassandra")
CASSANDRA_PORT     = os.getenv("CASSANDRA_PORT",     "9042")
CASSANDRA_KEYSPACE = os.getenv("CASSANDRA_KEYSPACE", "fleet")
CASSANDRA_USER     = os.getenv("CASSANDRA_USER",     "")
CASSANDRA_PASS     = os.getenv("CASSANDRA_PASS",     "")

# Data pools
CITIES = ["Casablanca", "Rabat", "Marrakech", "Tanger", "Agadir", "Fes", "Oujda", "Meknes"]
DRIVERS = ["DRV-0001", "DRV-0002", "DRV-0003", "DRV-0004", "DRV-0005"]

# Date Range for March 2026
START_DATE = datetime(2026, 3, 1)
END_DATE = datetime(2026, 4, 1)


@task
def generate_march_history():
    """Connect to Cassandra and insert realistic truck history for March."""
    from cassandra.cluster import Cluster
    from cassandra.auth import PlainTextAuthProvider

    print(f"🚀 Starting data generation for {START_DATE.strftime('%Y-%m')}...")

    auth = PlainTextAuthProvider(CASSANDRA_USER, CASSANDRA_PASS) if CASSANDRA_USER else None

    cluster = Cluster(
        [CASSANDRA_HOST],
        port=int(CASSANDRA_PORT),
        auth_provider=auth,
        connect_timeout=10,
    )
    
    session = cluster.connect()
    session.set_keyspace(CASSANDRA_KEYSPACE)

    # Prepare statement for speed
    insert_stmt = session.prepare("""
        INSERT INTO truck_history (
            truck_id, processed_at, event_time, latitude, longitude, speed,
            fuel_level, engine_temp, driver_id, start_city, end_city,
            odometer_km, refueling, refuel_city, anomaly, theft, theft_amount,
            alert_type, is_alert, distance_km, fuel_used, fuel_consumption_rate,
            high_consumption, fuel_consumed_trip, fuel_refueled,
            in_maintenance, maintenance_type, maintenance_desc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0.0, False, null, 'none', False, 0.0, 'NORMAL', False, 0.0, 0.0, 0.0, False, 0.0, 0.0, ?, ?, ?)
    """)

    rows_inserted = 0
    current_date = START_DATE

    while current_date < END_DATE:
        for truck_id in range(1, 11):
            # ── Logic: Truck 4 in Maintenance for first week ──
            if truck_id == 4 and 1 <= current_date.day <= 7:
                ts = current_date.replace(hour=10, minute=0)
                session.execute(insert_stmt, (
                    truck_id, ts, ts, 33.5731, -7.5898, 0.0, 80.0, 70.0, "DRV-MAINT",
                    "Garage", "Garage", True, "scheduled_repair", "Engine repair"
                ))
                rows_inserted += 1
            else:
                # ── Logic: Normal Driving ──
                # Generate 2 records per day per truck (Morning & Afternoon)
                for hour in [9, 15]:
                    ts = current_date.replace(hour=hour, minute=random.randint(0, 59))

                    # Speed logic
                    speed = random.uniform(60, 110)
                    in_maint = False

                    # Truck 2 speeds occasionally
                    if truck_id == 2 and random.random() < 0.3:
                        speed = random.uniform(125, 150)

                    session.execute(insert_stmt, (
                        truck_id, ts, ts,
                        random.uniform(30.0, 36.0), random.uniform(-10.0, -5.0),
                        speed, random.uniform(40, 95), random.uniform(75, 95),
                        random.choice(DRIVERS), random.choice(CITIES), random.choice(CITIES),
                        in_maint, None, None
                    ))
                    rows_inserted += 1

        current_date += timedelta(days=1)

    print(f"✅ Successfully inserted {rows_inserted} records into {CASSANDRA_KEYSPACE}.truck_history")
    cluster.shutdown()


@dag(
    dag_id="generate_march_history",
    description="One-time DAG to seed March 2026 data into truck_history",
    start_date=datetime(2026, 3, 1),
    schedule=None,  # Manual trigger only
    catchup=False,
    tags=["fleet", "maintenance", "seed"],
)
def generate_march_history_dag():
    generate_march_history()


generate_march_history_dag()
