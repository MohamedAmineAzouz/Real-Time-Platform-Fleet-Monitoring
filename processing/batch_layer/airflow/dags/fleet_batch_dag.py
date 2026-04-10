"""
dags/fleet_batch_dag.py
─────────────────────────────────────────────────────────────────────────────
Fleet Batch Layer — Airflow 3 DAG
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta

from airflow.sdk import dag, task
from airflow.providers.standard.operators.empty import EmptyOperator
from airflow.providers.apache.spark.operators.spark_submit import SparkSubmitOperator

log = logging.getLogger(__name__)

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
    "MINIO_ACCESS":     os.getenv("MINIO_ACCESS",     "minioadmin"),
    "MINIO_SECRET":     os.getenv("MINIO_SECRET",     "minioadmin"),
    "MINIO_BUCKET":     os.getenv("MINIO_BUCKET",     "fleet-data-dev"),
    "GCS_BUCKET":       os.getenv("GCS_BUCKET",       ""),
    "BIGQUERY_PROJECT": os.getenv("BIGQUERY_PROJECT", ""),
    "BIGQUERY_DATASET": os.getenv("BIGQUERY_DATASET", "fleet_analytics"),
    "GOOGLE_APPLICATION_CREDENTIALS": os.getenv("GOOGLE_APPLICATION_CREDENTIALS", ""),
    "CASSANDRA_HOST":     os.getenv("CASSANDRA_HOST",     "cassandra"),
    "CASSANDRA_PORT":     os.getenv("CASSANDRA_PORT",     "9042"),
    "CASSANDRA_KEYSPACE": os.getenv("CASSANDRA_KEYSPACE", "fleet"),
}

SPARK_CONF = {
    "spark.sql.shuffle.partitions": "32",
    "spark.sql.adaptive.enabled":   "true",
}

SPARK_MASTER = os.getenv("SPARK_MASTER", "local[2]")


def _spark_job(task_id: str, script: str) -> SparkSubmitOperator:
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
        spark_binary="spark-submit",
    )


@dag(
    dag_id="fleet_batch_layer",
    description="Fleet analytics batch pipeline — Parquet → Cassandra (minio) or BigQuery (gcs)",
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

    @task.branch
    def check_source(**context) -> str:
        """
        Check Parquet source data exists for the run date.
        Uses **context so Airflow injects ds, logical_date, etc automatically.
        """
        ds = context["ds"]
        log.info("check_source running for date=%s backend=%s", ds, STORAGE_BACKEND)

        try:
            if STORAGE_BACKEND == "minio":
                import boto3
                from botocore.client import Config
                from botocore.exceptions import BotoCoreError, ClientError

                log.info("Connecting to MinIO at %s", os.getenv("MINIO_ENDPOINT"))
                s3 = boto3.client(
                    "s3",
                    endpoint_url=os.getenv("MINIO_ENDPOINT", "http://minio:9000"),
                    aws_access_key_id=os.getenv("MINIO_ACCESS", "minioadmin"),
                    aws_secret_access_key=os.getenv("MINIO_SECRET", "minioadmin"),
                    config=Config(signature_version="s3v4"),
                )
                bucket = os.getenv("MINIO_BUCKET", "fleet-data-dev")
                prefix = f"raw/"
                log.info("Listing s3://%s/%s", bucket, prefix)
                result   = s3.list_objects_v2(Bucket=bucket, Prefix=prefix, MaxKeys=1)
                has_data = result.get("KeyCount", 0) > 0
                log.info("MinIO result: KeyCount=%s has_data=%s", result.get("KeyCount"), has_data)

            else:
                from google.cloud import storage as gcs
                log.info("Connecting to GCS bucket=%s", os.getenv("GCS_BUCKET"))
                client   = gcs.Client()
                bucket   = client.bucket(os.getenv("GCS_BUCKET", ""))
                blobs    = list(bucket.list_blobs(
                    prefix=f"raw_events/event_time={ds}/", max_results=1
                ))
                has_data = len(blobs) > 0
                log.info("GCS result: blobs=%s has_data=%s", len(blobs), has_data)

        except Exception as e:
            # Log the full exception so it appears in the Airflow task log
            log.exception("check_source failed with exception: %s", e)
            raise

        if has_data:
            log.info("✅ Source data found for %s — proceeding to Spark jobs", ds)
            return "run_spark_jobs"
        else:
            log.warning("⚠️  No source data for %s — skipping batch run", ds)
            return "no_data_skip"

    batch_start   = EmptyOperator(task_id="batch_start")
    run_jobs_gate = EmptyOperator(task_id="run_spark_jobs")
    no_data       = EmptyOperator(task_id="no_data_skip")

    t_daily_stats = _spark_job("daily_truck_stats",    "job_daily_truck_stats.py")
    t_driver_perf = _spark_job("driver_performance",   "job_driver_performance.py")
    t_fuel_maint  = _spark_job("fuel_and_maintenance", "job_fuel_and_maintenance.py")
    t_route_eff   = _spark_job("route_efficiency",     "job_route_efficiency.py")

    batch_done = EmptyOperator(
        task_id="batch_complete",
        trigger_rule="all_done",
    )

    source = check_source()

    batch_start >> source >> [run_jobs_gate, no_data]
    run_jobs_gate >> [t_daily_stats, t_driver_perf, t_fuel_maint, t_route_eff]
    [t_daily_stats, t_driver_perf, t_fuel_maint, t_route_eff] >> batch_done


fleet_batch_dag()