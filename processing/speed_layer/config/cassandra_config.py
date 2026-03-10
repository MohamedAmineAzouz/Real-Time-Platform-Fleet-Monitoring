"""
cassandra_config.py
─────────────────────────────────────────────────────────────────────────────
Single source of truth for Cassandra connection settings.

Dev  : Cassandra running in Docker (same iot_network)
Staging: Managed Cassandra (Astra DB or self-hosted on GCP)

TO MIGRATE: just update CASSANDRA_HOST in .env.staging
No code changes needed.
─────────────────────────────────────────────────────────────────────────────
"""

import os

CASSANDRA_HOST     = os.getenv("CASSANDRA_HOST",     "cassandra")
CASSANDRA_PORT     = os.getenv("CASSANDRA_PORT",     "9042")
CASSANDRA_KEYSPACE = os.getenv("CASSANDRA_KEYSPACE", "fleet")
CASSANDRA_USER     = os.getenv("CASSANDRA_USER",     "")
CASSANDRA_PASS     = os.getenv("CASSANDRA_PASS",     "")

# ── Tables ────────────────────────────────────────────────────────────────────
TABLES = {
    "truck_latest":  "truck_latest",   # latest position + telemetry per truck
    "truck_history": "truck_history",  # last 24h time-series per truck
    "alerts":        "alerts",         # all alerts, queryable by truck + time
}


def get_spark_cassandra_conf() -> dict:
    """Spark config dict for the Cassandra connector."""
    conf = {
        "spark.cassandra.connection.host": CASSANDRA_HOST,
        "spark.cassandra.connection.port": CASSANDRA_PORT,
        # Tuning for streaming micro-batches
        "spark.cassandra.output.consistency.level":      "LOCAL_ONE",
        "spark.cassandra.output.concurrent.writes":      "32",
        "spark.cassandra.output.batch.grouping.key":     "partition",
        "spark.cassandra.output.batch.size.rows":        "1000",
        "spark.cassandra.connection.keepAliveMS":        "60000",
    }
    if CASSANDRA_USER:
        conf["spark.cassandra.auth.username"] = CASSANDRA_USER
        conf["spark.cassandra.auth.password"] = CASSANDRA_PASS
    return conf


def get_cassandra_package() -> str:
    return "com.datastax.spark:spark-cassandra-connector_2.12:3.4.1"


def print_config():
    print(f"  Cassandra: {CASSANDRA_HOST}:{CASSANDRA_PORT}  keyspace={CASSANDRA_KEYSPACE}")
    for name, table in TABLES.items():
        print(f"  {name:<16}: {CASSANDRA_KEYSPACE}.{table}")