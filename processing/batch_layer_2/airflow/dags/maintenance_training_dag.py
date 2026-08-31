"""
dags/maintenance_training_dag.py
─────────────────────────────────────────────────────────────────────────────
Airflow DAG: Predictive Maintenance Model Training Pipeline
─────────────────────────────────────────────────────────────────────────────
- Schedule: Monthly (1st of every month at 04:00 AM)
- Logic: Prepares, cleans, splits data, trains a Random Forest model,
         evaluates accuracy, and validates against a fixed dataset.
- Output: Frozen ML model saved to S3/MinIO
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

SPARK_JOB_PATH = "/opt/spark/work-dir/spark_jobs/job_train_pipeline.py"

SPARK_CONF = {
    "spark.cassandra.connection.host": CASSANDRA_HOST,
    "spark.cassandra.connection.port": CASSANDRA_PORT,

    "spark.hadoop.fs.s3a.endpoint": S3_ENDPOINT,
    "spark.hadoop.fs.s3a.access.key": S3_ACCESS_KEY,
    "spark.hadoop.fs.s3a.secret.key": S3_SECRET_KEY,
    "spark.hadoop.fs.s3a.path.style.access": "true",
    "spark.hadoop.fs.s3a.impl": "org.apache.hadoop.fs.s3a.S3AFileSystem",

    "spark.sql.shuffle.partitions": "10",
    "spark.driver.memory": "2g",
    "spark.executor.memory": "2g",

    "spark.executor.env.CASSANDRA_KEYSPACE": CASSANDRA_KEYSPACE,
    "spark.driver.env.CASSANDRA_KEYSPACE": CASSANDRA_KEYSPACE,
    "spark.executor.env.LAKE_BUCKET": LAKE_BUCKET,
    "spark.executor.env.LAKE_PREFIX": LAKE_PREFIX,

    "spark.jars.packages": "com.datastax.spark:spark-cassandra-connector_2.12:3.5.0,org.apache.hadoop:hadoop-aws:3.3.4",
}

@dag(
    dag_id="maintenance_training_dag",
    description="Monthly execution of the Predictive Maintenance Machine Learning Pipeline",
    default_args={
        "owner": "fleet-maintenance",
        "retries": 0,
        "retry_delay": timedelta(minutes=1),
        "execution_timeout": timedelta(hours=24),
    },
    schedule="0 4 1 * *",  # 04:00 AM on the 1st of every month
    start_date=datetime(2026, 6, 1),
    catchup=False,
    tags=["fleet", "maintenance", "training", "ml", "spark"],
)
def maintenance_training_dag():

    start = EmptyOperator(task_id="training_pipeline_start")

    @task
    def get_training_target_date(**context):
        logical_date = context.get("logical_date") or context.get("execution_date")
        # Train on data up to the logical date
        return logical_date.strftime("%Y-%m-%d")

    target_date = get_training_target_date()

    # Task 1: Prepare Data
    prepare_data = SparkSubmitOperator(
        task_id="prepare_data",
        application=SPARK_JOB_PATH,
        conn_id=SPARK_CONN_ID,
        deploy_mode="client",
        name="ml_pipeline_prepare_data",
        conf=SPARK_CONF,
        application_args=[
            "--task", "prepare_data",
            "{{ ti.xcom_pull(task_ids='get_training_target_date') }}",
        ],
    )

    # Task 2: Clean Data
    clean_data = SparkSubmitOperator(
        task_id="clean_data",
        application=SPARK_JOB_PATH,
        conn_id=SPARK_CONN_ID,
        deploy_mode="client",
        name="ml_pipeline_clean_data",
        conf=SPARK_CONF,
        application_args=["--task", "clean_data"],
    )

    # Task 3: Split Data
    split_data = SparkSubmitOperator(
        task_id="split_data",
        application=SPARK_JOB_PATH,
        conn_id=SPARK_CONN_ID,
        deploy_mode="client",
        name="ml_pipeline_split_data",
        conf=SPARK_CONF,
        application_args=["--task", "split_data"],
    )

    # Task 4: Train Model
    train_model = SparkSubmitOperator(
        task_id="train_model",
        application=SPARK_JOB_PATH,
        conn_id=SPARK_CONN_ID,
        deploy_mode="client",
        name="ml_pipeline_train_model",
        conf=SPARK_CONF,
        application_args=["--task", "train_model"],
    )

    # Task 5: Evaluate Model Accuracy
    # evaluate_model = SparkSubmitOperator(
    #     task_id="evaluate_model_accuracy",
    #     application=SPARK_JOB_PATH,
    #     conn_id=SPARK_CONN_ID,
    #     deploy_mode="client",
    #     name="ml_pipeline_evaluate_model",
    #     conf=SPARK_CONF,
    #     application_args=["--task", "evaluate_model"],
    # )

    # Task 6: Model Validation
    validate_model = SparkSubmitOperator(
        task_id="model_validation_unit_test",
        application=SPARK_JOB_PATH,
        conn_id=SPARK_CONN_ID,
        deploy_mode="client",
        name="ml_pipeline_validate_model",
        conf=SPARK_CONF,
        application_args=["--task", "validate_model"],
    )

    end = EmptyOperator(task_id="training_pipeline_complete")

    start >> target_date >> prepare_data >> clean_data >> split_data >> train_model >> validate_model >> end

maintenance_training_dag()