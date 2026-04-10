"""
dags/maintenance_scheduler_dag.py
─────────────────────────────────────────────────────────────────────────────
Maintenance Schedule Generator — Airflow DAG
─────────────────────────────────────────────────────────────────────────────
Runs on the 30th of each month at 02:00.
Generates maintenance schedules for the NEXT month.

Example:
  - DAG runs on April 30 → Generates schedules for May
  - DAG runs on May 30   → Generates schedules for June
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import logging
import os
import random
import uuid
from datetime import datetime, timedelta

from airflow.sdk import dag, task
from airflow.providers.standard.operators.empty import EmptyOperator

log = logging.getLogger(__name__)

# ── Environment ────────────────────────────────────────────────────────────────
CASSANDRA_HOST     = os.getenv("CASSANDRA_HOST",     "cassandra")
CASSANDRA_PORT     = os.getenv("CASSANDRA_PORT",     "9042")
CASSANDRA_KEYSPACE = os.getenv("CASSANDRA_KEYSPACE", "fleet")
CASSANDRA_USER     = os.getenv("CASSANDRA_USER",     "")
CASSANDRA_PASS     = os.getenv("CASSANDRA_PASS",     "")

# ── Configuration ──────────────────────────────────────────────────────────────
MAINTENANCE_PER_TRUCK = 2

MAINTENANCE_TYPES = {
    "oil_change":           (1, 2, 50),
    "tire_rotation":        (1, 2, 40),
    "brake_inspection":     (2, 4, 150),
    "engine_tune":          (3, 6, 300),
    "transmission_service": (4, 8, 500),
    "coolant_flush":        (1, 2, 80),
    "filter_replacement":   (1, 2, 60),
    "battery_check":        (1, 2, 100),
    "full_inspection":      (6, 12, 800),
    "suspension_repair":    (4, 8, 400),
}

MECHANICS = [
    "Ahmed Benali", "Mohammed Tazi", "Karim El Amrani", "Youssef Bennani",
    "Hassan Idrissi", "Rachid Fassi", "Omar Chakir", "Ali Berrada",
    "Jean Martin", "Pierre Dupont", "Carlos Garcia", "Miguel Rodriguez",
]

WORK_START_HOUR = 8
WORK_END_HOUR   = 18

DESCRIPTIONS = {
    "oil_change":           "Engine oil replacement",
    "tire_rotation":        "Rotate and balance tires",
    "brake_inspection":     "Inspect and test brake system",
    "engine_tune":          "Engine tuning and performance check",
    "transmission_service": "Transmission fluid change and inspection",
    "coolant_flush":        "Coolant system flush and refill",
    "filter_replacement":   "Replace air and fuel filters",
    "battery_check":        "Battery health check and terminal cleaning",
    "full_inspection":      "Comprehensive vehicle inspection",
    "suspension_repair":    "Suspension system check and repair",
}


def _connect_cassandra():
    """Connect to Cassandra and return session + cluster."""
    from cassandra.cluster import Cluster
    from cassandra.auth import PlainTextAuthProvider

    auth = PlainTextAuthProvider(CASSANDRA_USER, CASSANDRA_PASS) if CASSANDRA_USER else None

    cluster = Cluster(
        [CASSANDRA_HOST],
        port=int(CASSANDRA_PORT),
        auth_provider=auth,
        connect_timeout=10,
    )
    session = cluster.connect()
    session.set_keyspace(CASSANDRA_KEYSPACE)
    return session, cluster


def _get_truck_ids(session):
    """Get all truck IDs from the trucks table."""
    result = session.execute("SELECT truck_id FROM trucks")
    return [row.truck_id for row in result]


def _random_time(month_start, day=None):
    """Generate a random datetime within working hours."""
    if day is None:
        day = random.randint(1, 28)
    hour   = random.randint(WORK_START_HOUR, WORK_END_HOUR - 1)
    minute = random.choice([0, 15, 30, 45])
    return month_start.replace(day=day, hour=hour, minute=minute, second=0, microsecond=0)


@task
def generate_maintenance_schedules(**context):
    """
    Generate maintenance schedules for all trucks for the NEXT month.
    """
    execution_date = context["logical_date"]

    # Calculate target month (next month)
    if execution_date.month == 12:
        target_year  = execution_date.year + 1
        target_month = 1
    else:
        target_year  = execution_date.year
        target_month = execution_date.month + 1

    log.info("=" * 72)
    log.info("  Maintenance Schedule Generator")
    log.info("=" * 72)
    log.info("  Execution Date : %s", execution_date.strftime("%Y-%m-%d"))
    log.info("  Target Month   : %d-%02d", target_year, target_month)
    log.info("=" * 72)

    session, cluster = _connect_cassandra()

    try:
        truck_ids = _get_truck_ids(session)
        if not truck_ids:
            log.warning("⚠️  No trucks found in database — nothing to generate")
            return 0

        log.info("📊 Generating maintenance schedules for %d trucks", len(truck_ids))

        month_start = datetime(target_year, target_month, 1)
        if target_month == 12:
            month_end = datetime(target_year + 1, 1, 1)
        else:
            month_end = datetime(target_year, target_month + 1, 1)
        days_in_month = (month_end - month_start).days

        insert_stmt = """
            INSERT INTO maintenance_schedules (
                schedule_id, truck_id, maintenance_type, description,
                scheduled_start, scheduled_end, assigned_mechanic,
                cost, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """

        schedules_created = 0
        now = datetime.utcnow()

        for truck_id in truck_ids:
            num_schedules = random.randint(1, MAINTENANCE_PER_TRUCK + 1)

            for _ in range(num_schedules):
                schedule_id  = uuid.uuid4()
                maint_type   = random.choice(list(MAINTENANCE_TYPES.keys()))
                min_h, max_h, base_cost = MAINTENANCE_TYPES[maint_type]
                duration_h   = random.uniform(min_h, max_h)

                random_day   = random.randint(1, days_in_month)
                sched_start  = _random_time(month_start, random_day)
                sched_end    = sched_start + timedelta(hours=duration_h)

                # If end time exceeds working hours, shift to next day
                if sched_end.hour > WORK_END_HOUR:
                    sched_start = _random_time(month_start, min(random_day + 1, days_in_month))
                    sched_end   = sched_start + timedelta(hours=duration_h)

                description = DESCRIPTIONS.get(maint_type, f"Maintenance for truck {truck_id}")
                mechanic    = random.choice(MECHANICS)
                cost        = base_cost * random.uniform(0.8, 1.3)

                session.execute(insert_stmt, (
                    schedule_id, truck_id, maint_type, description,
                    sched_start, sched_end, mechanic,
                    round(cost, 2), now, now,
                ))
                schedules_created += 1

        log.info("✅ Created %d maintenance schedules for %d-%02d",
                 schedules_created, target_year, target_month)
        return schedules_created

    finally:
        cluster.shutdown()


# ── DAG Definition ─────────────────────────────────────────────────────────────

@dag(
    dag_id="maintenance_schedule_generator",
    description="Generate monthly maintenance schedules for fleet trucks",
    default_args={
        "owner":            "fleet-team",
        "retries":          1,
        "retry_delay":      timedelta(minutes=5),
        "email_on_failure": False,
    },
    # Run on the 30th of every month at 02:00
    schedule="0 2 30 * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["fleet", "maintenance", "cassandra"],
)
def maintenance_scheduler_dag():

    sched_start = EmptyOperator(task_id="maintenance_sched_start")
    sched_done  = EmptyOperator(task_id="maintenance_sched_complete", trigger_rule="all_done")

    generate = generate_maintenance_schedules()

    sched_start >> generate >> sched_done


maintenance_scheduler_dag()
