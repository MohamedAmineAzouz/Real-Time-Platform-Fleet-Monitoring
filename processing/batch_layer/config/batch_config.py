"""
config/batch_config.py
─────────────────────────────────────────────────────────────────────────────
Batch layer configuration.

STORAGE_BACKEND controls where Spark reads source data and where results
are written:

  dev      → reads MinIO Parquet  → writes Cassandra
  staging  → reads GCS Parquet    → writes BigQuery
  prod     → reads GCS Parquet    → writes BigQuery

Switching environments only requires changing STORAGE_BACKEND in .env.
No Spark job code changes needed.
─────────────────────────────────────────────────────────────────────────────
"""

import os

# ── Environment ────────────────────────────────────────────────────────────────
STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "minio")   # dev | staging | prod

# ── Source: where Spark reads raw Parquet data ─────────────────────────────────
if STORAGE_BACKEND == "minio":
    PARQUET_BASE = f"s3a://{os.getenv("MINIO_BUCKET")}/raw_events/"
else:
    GCS_BUCKET   = os.getenv("GCS_BUCKET", "fleet-data-staging")
    PARQUET_BASE = f"gs://{GCS_BUCKET}/raw_events/"

# ── Sink: where Spark writes aggregated results ────────────────────────────────
# dev    → Cassandra tables
# staging/prod → BigQuery dataset
CASSANDRA_HOST     = os.getenv("CASSANDRA_HOST",     "cassandra")
CASSANDRA_PORT     = os.getenv("CASSANDRA_PORT",     "9042")
CASSANDRA_KEYSPACE = os.getenv("CASSANDRA_KEYSPACE", "fleet")

BIGQUERY_PROJECT = os.getenv("BIGQUERY_PROJECT", "")
BIGQUERY_DATASET = os.getenv("BIGQUERY_DATASET", "fleet_analytics")

# ── Cassandra batch result tables (dev sink) ───────────────────────────────────
BATCH_TABLES = {
    "daily_truck_stats":   "batch_daily_truck_stats",
    "driver_performance":  "batch_driver_performance",
    "fuel_waste_anomalies":"batch_fuel_waste_anomalies",
    "maintenance_flags":   "batch_maintenance_flags",
    "route_efficiency":    "batch_route_efficiency",
}

# ── BigQuery table names (staging/prod sink) ───────────────────────────────────
# Same logical names — BigQuery uses dataset.table format
BIGQUERY_TABLES = {k: f"{BIGQUERY_DATASET}.{v}" for k, v in BATCH_TABLES.items()}


def is_dev() -> bool:
    return STORAGE_BACKEND == "dev"


def get_sink_label() -> str:
    if is_dev():
        return f"Cassandra ({CASSANDRA_HOST}:{CASSANDRA_PORT}/{CASSANDRA_KEYSPACE})"
    return f"BigQuery ({BIGQUERY_PROJECT}.{BIGQUERY_DATASET})"


def get_source_label() -> str:
    return PARQUET_BASE


def print_config():
    print(f"  Backend  : {STORAGE_BACKEND}")
    print(f"  Source   : {get_source_label()}")
    print(f"  Sink     : {get_sink_label()}")