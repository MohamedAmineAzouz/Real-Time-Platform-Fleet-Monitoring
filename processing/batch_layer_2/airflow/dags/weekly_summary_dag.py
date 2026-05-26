"""
dags/weekly_summary_dag.py
─────────────────────────────────────────────────────────────────────────────
Airflow DAG: Weekly Fleet Summary
─────────────────────────────────────────────────────────────────────────────
- Schedule: Monday at 03:00 AM
- Logic: Aggregates daily batch data into a strategic weekly report.
- Output: Cassandra table `batch_weekly_summary`
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

SPARK_JOB_PATH = "/opt/spark/work-dir/spark_jobs/job_weekly_summary.py"

@dag(
    dag_id="weekly_summary_dag",
    description="Aggregate daily data into weekly executive summaries",
    default_args={
        "owner": "fleet-executive",
        "retries": 1,
        "retry_delay": timedelta(minutes=30),
        "execution_timeout": timedelta(hours=1),
    },
    schedule="0 3 * * 1", # Monday 03:00 AM
    start_date=datetime(2026, 5, 1),
    catchup=False,
    tags=["fleet", "executive", "weekly", "spark"],
)
def weekly_summary_dag():
    
    start = EmptyOperator(task_id="weekly_summary_start")

    @task
    def get_summary_end_date(**context):
        """
        The job runs on Monday. We want to process the week ending on the previous Sunday.
        """
        logical_date = context.get("logical_date") or context.get("execution_date")
        
        # If run on Monday, logical_date might be Monday. 
        # We want the stats up to Sunday.
        # target = logical_date - timedelta(days=1)
        target = logical_date
        
        return target.strftime("%Y-%m-%d")

    target_date = get_summary_end_date()

    run_summary_job = SparkSubmitOperator(
        task_id="run_weekly_summary_job",
        application=SPARK_JOB_PATH,
        conn_id=SPARK_CONN_ID,
        deploy_mode="client",
        name="fleet_weekly_summary",
        
        conf={
            "spark.cassandra.connection.host": CASSANDRA_HOST,
            "spark.cassandra.connection.port": CASSANDRA_PORT,
            "spark.sql.shuffle.partitions": "50",
            "spark.jars.packages": "com.datastax.spark:spark-cassandra-connector_2.12:3.5.0",
            "spark.executor.env.CASSANDRA_KEYSPACE": CASSANDRA_KEYSPACE,
        },
        
        application_args=[
            "{{ ti.xcom_pull(task_ids='get_summary_end_date') }}",
        ],
    )

    end = EmptyOperator(task_id="weekly_summary_complete")

    start >> target_date >> run_summary_job >> end

weekly_summary_dag()
