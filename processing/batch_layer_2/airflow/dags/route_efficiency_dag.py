"""
dags/route_efficiency_dag.py
─────────────────────────────────────────────────────────────────────────────
Airflow DAG: Route Efficiency Analysis
─────────────────────────────────────────────────────────────────────────────
- Schedule: Daily at 04:00 (After predictive maintenance)
- Logic: Aggregates performance by Start City -> End City.
- Output: Cassandra table `batch_route_efficiency`
─────────────────────────────────────────────────────────────────────────────
"""

import os
from datetime import datetime, timedelta
from airflow.sdk import dag, task
from airflow.providers.standard.operators.empty import EmptyOperator
from airflow.providers.apache.spark.operators.spark_submit import SparkSubmitOperator

# ── Configuration ─────────────────────────────────────────────────────────
SPARK_CONN_ID = os.getenv("SPARK_CONN_ID", "spark_default")
CASSANDRA_HOST = os.getenv("CASSANDRA_HOST", "cassandra")
CASSANDRA_PORT = os.getenv("CASSANDRA_PORT", "9042")
CASSANDRA_KEYSPACE = os.getenv("CASSANDRA_KEYSPACE", "fleet")
LAKE_BUCKET = os.getenv("LAKE_BUCKET", "fleet-data")
LAKE_PREFIX = os.getenv("LAKE_PREFIX", "silver/truck_history")

S3_ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://minio:9000")
S3_ACCESS_KEY = os.getenv("MINIO_ROOT_USER", "minioadmin")
S3_SECRET_KEY = os.getenv("MINIO_ROOT_PASSWORD", "minioadmin")

SPARK_JOB_PATH = "/opt/spark/work-dir/spark_jobs/job_route_efficiency.py"

@dag(
    dag_id="route_efficiency_dag",
    description="Analyze performance and fuel efficiency across delivery routes",
    default_args={
        "owner": "fleet-operations",
        "retries": 1,
        "retry_delay": timedelta(minutes=10),
        "execution_timeout": timedelta(hours=2),
    },
    schedule="0 4 * * *", # 04:00 AM
    start_date=datetime(2026, 5, 1),
    catchup=False,
    tags=["fleet", "operations", "route", "efficiency", "spark"],
)
def route_efficiency_dag():
    
    start = EmptyOperator(task_id="route_analysis_start")

    @task
    def get_analysis_dates(**context):
        logical_date = context.get("logical_date") or context.get("execution_date")
        # Process the full day that just ended
        target_date = logical_date - timedelta(days=1)
        return {
            "date_from": target_date.strftime("%Y-%m-%d"),
            "date_to": target_date.strftime("%Y-%m-%d"),
        }

    dates = get_analysis_dates()

    run_route_job = SparkSubmitOperator(
        task_id="run_route_efficiency_job",
        application=SPARK_JOB_PATH,
        conn_id=SPARK_CONN_ID,
        deploy_mode="client",
        name="fleet_route_efficiency",
        
        conf={
            "spark.cassandra.connection.host": CASSANDRA_HOST,
            "spark.cassandra.connection.port": CASSANDRA_PORT,
            
            "spark.hadoop.fs.s3a.endpoint": S3_ENDPOINT,
            "spark.hadoop.fs.s3a.access.key": S3_ACCESS_KEY,
            "spark.hadoop.fs.s3a.secret.key": S3_SECRET_KEY,
            "spark.hadoop.fs.s3a.path.style.access": "true",
            "spark.hadoop.fs.s3a.impl": "org.apache.hadoop.fs.s3a.S3AFileSystem",
            
            "spark.sql.shuffle.partitions": "100",
            "spark.driver.memory": "2g",
            "spark.executor.memory": "2g",
            
            "spark.executor.env.CASSANDRA_KEYSPACE": CASSANDRA_KEYSPACE,
            "spark.driver.env.CASSANDRA_KEYSPACE": CASSANDRA_KEYSPACE,
            "spark.executor.env.LAKE_BUCKET": LAKE_BUCKET,
            "spark.executor.env.LAKE_PREFIX": LAKE_PREFIX,
            
            "spark.jars.packages": "com.datastax.spark:spark-cassandra-connector_2.12:3.5.0,org.apache.hadoop:hadoop-aws:3.3.4",
        },
        
        application_args=[
            "{{ ti.xcom_pull(task_ids='get_analysis_dates')['date_from'] }}",
            "{{ ti.xcom_pull(task_ids='get_analysis_dates')['date_to'] }}",
        ],
    )

    end = EmptyOperator(task_id="route_analysis_complete")

    start >> dates >> run_route_job >> end

route_efficiency_dag()
