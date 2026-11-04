"""
dags/daily_truck_stats_dag.py
─────────────────────────────────────────────────────────────────────────────
Airflow DAG: Daily Truck Statistics (Silver Lake -> Cassandra)
─────────────────────────────────────────────────────────────────────────────
- Schedule: Daily at 02:00
- Logic: Aggregates yesterday's telemetry into daily stats
- Platform: Spark on Kubernetes/Standalone via SparkSubmitOperator
─────────────────────────────────────────────────────────────────────────────
"""

import os
from datetime import datetime, timedelta
from airflow.sdk import dag, task
from airflow.providers.standard.operators.empty import EmptyOperator
from airflow.providers.apache.spark.operators.spark_submit import SparkSubmitOperator

# ── Configuration (Environment Based) ─────────────────────────────────────
SPARK_CONN_ID = os.getenv("SPARK_CONN_ID", "spark_default")
CASSANDRA_HOST = os.getenv("CASSANDRA_HOST", "cassandra")
CASSANDRA_PORT = os.getenv("CASSANDRA_PORT", "9042")
CASSANDRA_KEYSPACE = os.getenv("CASSANDRA_KEYSPACE", "fleet")
LAKE_BUCKET = os.getenv("LAKE_BUCKET", "fleet-data")
LAKE_PREFIX = os.getenv("LAKE_PREFIX", "silver/truck_history")

# S3 / MinIO Credentials
S3_ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://minio:9000")
S3_ACCESS_KEY = os.getenv("MINIO_ROOT_USER", "minioadmin")
S3_SECRET_KEY = os.getenv("MINIO_ROOT_PASSWORD", "minioadmin")

# Path to the Spark job within the container
SPARK_JOB_PATH = "/opt/spark/work-dir/spark_jobs/job_daily_truck_stats.py"


@dag(
    dag_id="daily_truck_stats_dag",
    description="Aggregate daily truck telemetry from Parquet into Cassandra statistics",
    default_args={
        "owner": "fleet-data-eng",
        "retries": 1,
        "retry_delay": timedelta(minutes=5),
        "execution_timeout": timedelta(hours=4),
    },
    schedule="0 2 * * *",
    start_date=datetime(2026, 5, 1),
    catchup=False,
    tags=["fleet", "batch", "statistics", "spark", "silver_lake"],
)
def daily_truck_stats_dag():
    start = EmptyOperator(task_id="stats_pipeline_start")

    @task
    def get_execution_dates(**context):
        logical_date = context.get("logical_date") or context.get("execution_date")
        target_date = logical_date - timedelta(days=1)
        
        return {
            "date_from": target_date.strftime("%Y-%m-%d"),
            "date_to": target_date.strftime("%Y-%m-%d"),
        }

    dates = get_execution_dates()

    run_stats_job = SparkSubmitOperator(
        task_id="run_daily_stats_spark_job",
        application=SPARK_JOB_PATH,
        conn_id=SPARK_CONN_ID,
        deploy_mode="client",
        name="daily_truck_stats_aggregation",
        
        conf={
            # Cassandra Connectivity
            "spark.cassandra.connection.host": CASSANDRA_HOST,
            "spark.cassandra.connection.port": CASSANDRA_PORT,
            
            # S3/MinIO Connectivity
            "spark.hadoop.fs.s3a.endpoint": S3_ENDPOINT,
            "spark.hadoop.fs.s3a.access.key": S3_ACCESS_KEY,
            "spark.hadoop.fs.s3a.secret.key": S3_SECRET_KEY,
            "spark.hadoop.fs.s3a.path.style.access": "true",
            "spark.hadoop.fs.s3a.impl": "org.apache.hadoop.fs.s3a.S3AFileSystem",
            
            # Resource Allocation
            "spark.driver.memory": "2g",
            "spark.executor.memory": "2g",
            # "spark.executor.cores": "2",
            "spark.sql.shuffle.partitions": "200",
            
            # Environment Variables for the Job
            "spark.executor.env.CASSANDRA_KEYSPACE": CASSANDRA_KEYSPACE,
            "spark.driver.env.CASSANDRA_KEYSPACE": CASSANDRA_KEYSPACE,
            "spark.executor.env.LAKE_BUCKET": LAKE_BUCKET,
            "spark.driver.env.LAKE_BUCKET": LAKE_BUCKET,
            "spark.executor.env.LAKE_PREFIX": LAKE_PREFIX,
            "spark.driver.env.LAKE_PREFIX": LAKE_PREFIX,
            
            # Necessary Packages
            "spark.jars.packages": "com.datastax.spark:spark-cassandra-connector_2.12:3.5.0,org.apache.hadoop:hadoop-aws:3.3.4",
        },
        
        application_args=[
            "{{ ti.xcom_pull(task_ids='get_execution_dates')['date_from'] }}",
            "{{ ti.xcom_pull(task_ids='get_execution_dates')['date_to'] }}",
        ],
        verbose=True,
    )

    end = EmptyOperator(task_id="stats_pipeline_complete")

    start >> dates >> run_stats_job >> end


daily_truck_stats_dag()
