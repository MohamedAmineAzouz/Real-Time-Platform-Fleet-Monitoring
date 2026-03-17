"""
dags/fleet_batch_dag.py
─────────────────────────────────────────────────────────────────────────────
Fleet Batch Layer — Airflow 3 DAG

Airflow 3 key changes applied here:
  - Imports from airflow.sdk  (@dag, @task, @task.branch)
  - No BranchPythonOperator / PythonOperator — replaced by decorators
  - EmptyOperator from airflow.providers.standard.operators.empty
  - schedule= instead of schedule_interval=
  - provide_context=True removed — context injected automatically
  - logical_date replaces execution_date in context

Pipeline:
  check_source              ← verify Parquet data exists for the run date
       │
       ├─▶ run_spark_jobs ──┬─▶ daily_truck_stats     ──┐
       │                   ├─▶ driver_performance     ──┤─▶ batch_complete
       │                   ├─▶ fuel_and_maintenance   ──┤
       │                   └─▶ route_efficiency        ──┘
       │
       └─▶ no_data_skip
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta

# ── Airflow 3: all core DAG constructs from airflow.sdk ───────────────────────
from airflow.sdk import dag, task
from airflow.providers.standard.operators.empty import EmptyOperator
from airflow.providers.apache.spark.operators.spark_submit import SparkSubmitOperator

# ── Environment ────────────────────────────────────────────────────────────────
STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "minio")

_PACKAGES_DEV = ",".join([
    "com.datastax.spark:spark-cassandra-connector_2.12:3.4.1",
    "org.apache.hadoop:hadoop-aws:3.3.4",
    "com.amazonaws:aws-java-sdk-bundle:1.12.262",
])
_PACKAGES_STAGING = ",".join([
    "com.google.cloud.spark:spark-bigquery-with-dependencies_2.12:0.34.0",
    "com.google.cloud.bigdataoss:gcs-connector:hadoop3-2.2.17",
])
SPARK_PACKAGES = _PACKAGES_DEV if STORAGE_BACKEND == "minio" else _PACKAGES_STAGING

SPARK_ENV_VARS = {
    "STORAGE_BACKEND":  STORAGE_BACKEND,
    "MINIO_ENDPOINT":   os.getenv("MINIO_ENDPOINT",   "http://minio:9000"),
    "MINIO_ACCESS":     os.getenv("MINIO_ACCESS",      "minioadmin"),
    "MINIO_SECRET":     os.getenv("MINIO_SECRET",      "minioadmin"),
    "MINIO_BUCKET":     os.getenv("MINIO_BUCKET",      "fleet-data-dev"),
    "GCS_BUCKET":       os.getenv("GCS_BUCKET",        ""),
    "BIGQUERY_PROJECT": os.getenv("BIGQUERY_PROJECT",  ""),
    "BIGQUERY_DATASET": os.getenv("BIGQUERY_DATASET",  "fleet_analytics"),
    "GOOGLE_APPLICATION_CREDENTIALS": os.getenv("GOOGLE_APPLICATION_CREDENTIALS", ""),
    "CASSANDRA_HOST":     os.getenv("CASSANDRA_HOST",     "cassandra"),
    "CASSANDRA_PORT":     os.getenv("CASSANDRA_PORT",     "9042"),
    "CASSANDRA_KEYSPACE": os.getenv("CASSANDRA_KEYSPACE", "fleet"),
}

SPARK_CONF = {
    "spark.sql.shuffle.partitions": "4",
    "spark.sql.adaptive.enabled":   "true",
}


# ── Helper: build SparkSubmitOperator ──────────────────────────────────────────
def _spark_job(task_id: str, script: str) -> SparkSubmitOperator:
    """
    Wraps a Spark job script as a SparkSubmitOperator.
    Dates are Jinja-templated from the DAG run logical_date.
    """
    return SparkSubmitOperator(
        task_id=task_id,
        application=f"/opt/airflow/batch_layer/spark_jobs/{script}",
        application_args=[
            "--date-from", "{{ ds }}",
            "--date-to",   "{{ ds }}",
            "--run-date",  "{{ ds }}",
        ],
        conn_id="spark_default",
        packages=SPARK_PACKAGES,
        conf=SPARK_CONF,
        env_vars=SPARK_ENV_VARS,
        verbose=True,
    )


# ── DAG ────────────────────────────────────────────────────────────────────────
@dag(
    dag_id="fleet_batch_layer",
    description="Fleet analytics batch pipeline — Parquet → Cassandra (dev) or BigQuery (staging)",
    default_args={
        "owner":            "fleet-team",
        "retries":          1,
        "retry_delay":      timedelta(minutes=1),
        "email_on_failure": False,
    },
    schedule="0 2 * * *",
    start_date=datetime(2026, 3, 12),
    catchup=False,
    max_active_runs=1,
    tags=["fleet", "batch", "spark"],
)
def fleet_batch_dag():

    # ── Task 1: check source data exists ──────────────────────────────────────
    # Airflow 3: @task.branch replaces BranchPythonOperator
    # context is injected automatically — no provide_context=True needed
    @task.branch
    def check_source(**context) -> str:   # ds = logical date YYYY-MM-DD (injected)
        """
        Verify that Parquet files exist for the run date before launching
        Spark jobs. Returns the task_id of the next branch to execute.
        """
        ds = context["ds"]
        if STORAGE_BACKEND == "minio":
            import boto3
            from botocore.client import Config

            s3 = boto3.client(
                "s3",
                endpoint_url=os.getenv("MINIO_ENDPOINT", "http://minio:9000"),
                aws_access_key_id=os.getenv("MINIO_ACCESS", "minioadmin"),
                aws_secret_access_key=os.getenv("MINIO_SECRET", "minioadmin"),
                config=Config(signature_version="s3v4"),
            )
            bucket   = os.getenv("MINIO_BUCKET", "fleet-data-dev")
            prefix   = f"raw_events/event_time={ds}/"
            result   = s3.list_objects_v2(Bucket=bucket, Prefix=prefix, MaxKeys=1)
            has_data = result.get("KeyCount", 0) > 0
        else:
            from google.cloud import storage as gcs
            client   = gcs.Client()
            bucket   = client.bucket(os.getenv("GCS_BUCKET", ""))
            blobs    = list(bucket.list_blobs(prefix=f"raw_events/event_time={ds}/", max_results=1))
            has_data = len(blobs) > 0

        if has_data:
            print(f"✅ Source data found for {ds}")
            return "run_spark_jobs"
        else:
            print(f"⚠️  No source data for {ds} — skipping")
            return "no_data_skip"

    # ── Branch gates ──────────────────────────────────────────────────────────
    run_jobs_gate = EmptyOperator(task_id="run_spark_jobs")
    no_data       = EmptyOperator(task_id="no_data_skip")

    # ── Spark jobs (run in parallel after gate) ───────────────────────────────
    t_daily_stats = _spark_job("daily_truck_stats",    "job_daily_truck_stats.py")
    t_driver_perf = _spark_job("driver_performance",   "job_driver_performance.py")
    t_fuel_maint  = _spark_job("fuel_and_maintenance", "job_fuel_and_maintenance.py")
    t_route_eff   = _spark_job("route_efficiency",     "job_route_efficiency.py")

    # ── Completion marker ─────────────────────────────────────────────────────
    batch_done = EmptyOperator(
        task_id="batch_complete",
        trigger_rule="all_done",
    )

    # ── Wiring ────────────────────────────────────────────────────────────────
    source = check_source()

    source >> [run_jobs_gate, no_data]

    run_jobs_gate >> [t_daily_stats, t_driver_perf, t_fuel_maint, t_route_eff]

    [t_daily_stats, t_driver_perf, t_fuel_maint, t_route_eff] >> batch_done


# Instantiate — Airflow 3 discovers the DAG from this call
fleet_batch_dag()