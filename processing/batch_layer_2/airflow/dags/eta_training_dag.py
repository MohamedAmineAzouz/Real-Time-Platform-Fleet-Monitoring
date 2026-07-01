"""
dags/eta_training_dag.py
─────────────────────────────────────────────────────────────────────────────
Airflow DAG: Dynamic ETA Model Training Pipeline
─────────────────────────────────────────────────────────────────────────────
- Schedule: Monthly (1st of every month at 05:00 AM — after maintenance training)
- Logic: Prepares 90-day trip data, cleans/engineers features, splits,
         trains a GBT model, and validates RMSE against a fixed dataset.
- Output: Frozen ETA model saved to S3/MinIO
─────────────────────────────────────────────────────────────────────────────
"""

import os
from datetime import datetime, timedelta
from airflow.sdk import dag, task
from airflow.providers.standard.operators.empty import EmptyOperator
from airflow.providers.apache.spark.operators.spark_submit import SparkSubmitOperator

# ── Configuration ─────────────────────────────────────────────────────────
SPARK_CONN_ID     = os.getenv("SPARK_CONN_ID", "spark_default")
CASSANDRA_HOST    = os.getenv("CASSANDRA_HOST", "cassandra")
CASSANDRA_PORT    = os.getenv("CASSANDRA_PORT", "9042")
CASSANDRA_KEYSPACE = os.getenv("CASSANDRA_KEYSPACE", "fleet")
LAKE_BUCKET       = os.getenv("LAKE_BUCKET", "fleet-data")
LAKE_PREFIX       = os.getenv("LAKE_PREFIX", "silver/truck_history")

S3_ENDPOINT  = os.getenv("MINIO_ENDPOINT",       "http://minio:9000")
S3_ACCESS_KEY = os.getenv("MINIO_ROOT_USER",     "minioadmin")
S3_SECRET_KEY = os.getenv("MINIO_ROOT_PASSWORD", "minioadmin")

SPARK_JOB_PATH = "/opt/spark/work-dir/spark_jobs/job_eta_train_pipeline.py"

SPARK_CONF = {
    "spark.cassandra.connection.host": CASSANDRA_HOST,
    "spark.cassandra.connection.port": CASSANDRA_PORT,

    "spark.hadoop.fs.s3a.endpoint":          S3_ENDPOINT,
    "spark.hadoop.fs.s3a.access.key":        S3_ACCESS_KEY,
    "spark.hadoop.fs.s3a.secret.key":        S3_SECRET_KEY,
    "spark.hadoop.fs.s3a.path.style.access": "true",
    "spark.hadoop.fs.s3a.impl":              "org.apache.hadoop.fs.s3a.S3AFileSystem",

    "spark.sql.shuffle.partitions": "10",
    "spark.driver.memory":          "3g",
    "spark.executor.memory":        "3g",

    "spark.executor.env.CASSANDRA_KEYSPACE": CASSANDRA_KEYSPACE,
    "spark.driver.env.CASSANDRA_KEYSPACE":   CASSANDRA_KEYSPACE,
    "spark.executor.env.LAKE_BUCKET":        LAKE_BUCKET,
    "spark.executor.env.LAKE_PREFIX":        LAKE_PREFIX,

    "spark.jars.packages": (
        "com.datastax.spark:spark-cassandra-connector_2.12:3.5.0,"
        "org.apache.hadoop:hadoop-aws:3.3.4"
    ),
}


@dag(
    dag_id="eta_training_dag",
    description="Monthly execution of the Dynamic ETA Machine Learning Training Pipeline",
    default_args={
        "owner": "fleet-maintenance",
        "retries": 0,
        "retry_delay": timedelta(minutes=1),
        "execution_timeout": timedelta(hours=24),
    },
    schedule="0 5 1 * *",  # 05:00 AM on the 1st of every month (after maintenance training)
    start_date=datetime(2026, 6, 1),
    catchup=False,
    tags=["fleet", "eta", "training", "ml", "spark"],
)
def eta_training_dag():

    start = EmptyOperator(task_id="training_pipeline_start")

    # Task 0: Resolve training target date from logical_date
    prepare_data = SparkSubmitOperator(
        task_id="prepare_data",
        application=SPARK_JOB_PATH,
        conn_id=SPARK_CONN_ID,
        deploy_mode="client",
        name="eta_pipeline_prepare_data",
        conf=SPARK_CONF,
        application_args=[
            "--task", "prepare_data",
            "{{ logical_date.strftime('%Y-%m-%d') }}",
        ],
    )

    # Task 2: Clean Data & Engineer Trip Features
    clean_data = SparkSubmitOperator(
        task_id="clean_data",
        application=SPARK_JOB_PATH,
        conn_id=SPARK_CONN_ID,
        deploy_mode="client",
        name="eta_pipeline_clean_data",
        conf=SPARK_CONF,
        application_args=["--task", "clean_data"],
    )

    # Task 3: Split Data
    split_data = SparkSubmitOperator(
        task_id="split_data",
        application=SPARK_JOB_PATH,
        conn_id=SPARK_CONN_ID,
        deploy_mode="client",
        name="eta_pipeline_split_data",
        conf=SPARK_CONF,
        application_args=["--task", "split_data"],
    )

    # Task 4: Train GBT Model
    train_model = SparkSubmitOperator(
        task_id="train_model",
        application=SPARK_JOB_PATH,
        conn_id=SPARK_CONN_ID,
        deploy_mode="client",
        name="eta_pipeline_train_model",
        conf=SPARK_CONF,
        application_args=["--task", "train_model"],
    )

    # Task 5: Validate Model (RMSE gate) & Freeze to Production
    validate_model = SparkSubmitOperator(
        task_id="model_validation_unit_test",
        application=SPARK_JOB_PATH,
        conn_id=SPARK_CONN_ID,
        deploy_mode="client",
        name="eta_pipeline_validate_model",
        conf=SPARK_CONF,
        application_args=["--task", "validate_model"],
    )

    end = EmptyOperator(task_id="training_pipeline_complete")

    start >> prepare_data >> clean_data >> split_data >> train_model >> validate_model >> end


eta_training_dag()