
"""
dags/traffic_violations_dag.py
─────────────────────────────────────────────────────────────────────────────
Airflow DAG: Monthly Traffic Violations
─────────────────────────────────────────────────────────────────────────────
Runs: 1st of every month at 02:00.
Action: Generates violation report for the PREVIOUS month.
─────────────────────────────────────────────────────────────────────────────
"""

import os
from datetime import datetime, timedelta
from airflow.sdk import dag
from airflow.providers.standard.operators.empty import EmptyOperator
from airflow.providers.standard.operators.bash import BashOperator

@dag(
    dag_id="monthly_traffic_violations",
    description="Generate realistic traffic violations based on last month's driving history",
    default_args={
        "owner": "fleet-team",
        "retries": 1,
        "retry_delay": timedelta(minutes=5),
    },
    schedule="0 2 1 * *",  # At 02:00 on day 1 of every month
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["fleet", "batch", "violations"],
)
def traffic_violations_dag():

    violations_start = EmptyOperator(task_id="violations_start")

    generate_and_run = BashOperator(
        task_id="run_violations_job",
        bash_command=(
            "START_DATE=$(date -d 'last month' +%Y-%m-01) && "
            "END_DATE=$(date +%Y-%m-01) && "
            "echo '========================================' && "
            "echo '📅 Generating Violations Report' && "
            "echo '📉 Period: ' $START_DATE ' to ' $END_DATE && "
            "echo '========================================' && "
            "spark-submit "
            "--packages com.datastax.spark:spark-cassandra-connector_2.12:3.4.1 "
            "--conf spark.cassandra.connection.host=cassandra "
            "/opt/airflow/batch_layer/spark_jobs/job_traffic_violations.py $START_DATE $END_DATE"
        ),
    )

    violations_complete = EmptyOperator(
        task_id="violations_complete",
        trigger_rule="all_done",
    )

    violations_start >> generate_and_run >> violations_complete

traffic_violations_dag()