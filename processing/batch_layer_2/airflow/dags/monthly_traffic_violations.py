"""
dags/monthly_traffic_violations_dag.py
─────────────────────────────────────────────────────────────────────────────
Airflow DAG: Monthly Traffic Violations (Airflow 3.2 + Env-Only Config)
─────────────────────────────────────────────────────────────────────────────
"""

import os
from datetime import datetime, timedelta
from airflow.sdk import dag, task
from airflow.providers.standard.operators.empty import EmptyOperator
from airflow.providers.apache.spark.operators.spark_submit import SparkSubmitOperator


SPARK_CONN_ID = os.getenv("SPARK_CONN_ID", "spark_default")
CASSANDRA_HOST = os.getenv("CASSANDRA_HOST", "cassandra")
CASSANDRA_PORT = os.getenv("CASSANDRA_PORT", "9042")
CASSANDRA_KEYSPACE = os.getenv("CASSANDRA_KEYSPACE", "fleet")
SPARK_JOB_PATH = "/opt/spark/work-dir/spark_jobs/job_traffic_violations.py"


@dag(
    dag_id="monthly_traffic_violations",
    description="Generate realistic traffic violations based on last month's actual driving telemetry",
    default_args={
        "owner": "fleet-team",
        "retries": 0,
        "retry_delay": timedelta(minutes=1),
        "execution_timeout": timedelta(hours=2),
    },
    schedule="0 2 1 * *",
    start_date=datetime(2026, 5, 1),
    catchup=False,
    tags=["fleet", "batch", "violations", "spark", "cassandra"],
)
def monthly_traffic_violations_dag():
    """DAG definition - NO return statement in Airflow 3.2"""

    start = EmptyOperator(task_id="violations_start")

    @task
    def calc_dates(**context):
        """Calculate previous month date range using logical_date (Airflow 3.x)"""
        logical_date = context["logical_date"]
        first_current = logical_date.replace(day=1)
        prev_month = (first_current - timedelta(days=1)).replace(day=1)
        return {
            "start_date": prev_month.strftime("%Y-%m-%d"),
            "end_date": first_current.strftime("%Y-%m-%d"),
        }

    date_range = calc_dates()

    run_violations_job = SparkSubmitOperator(
        task_id="run_violations_spark_job",
        application=SPARK_JOB_PATH,
        conn_id=SPARK_CONN_ID,
        deploy_mode="client",
        name="traffic_violations_batch",

        conf={
            "spark.cassandra.connection.host": CASSANDRA_HOST,
            "spark.cassandra.connection.port": CASSANDRA_PORT,
            "spark.driver.memory": "1g",
            "spark.executor.memory": "1g",
            "spark.executor.cores": "1",
            "spark.cores.max": "2",
            "spark.sql.shuffle.partitions": "4",

            "spark.executor.env.CASSANDRA_KEYSPACE": CASSANDRA_KEYSPACE,
            "spark.driver.env.CASSANDRA_KEYSPACE": CASSANDRA_KEYSPACE,
            "spark.jars.packages": "com.datastax.spark:spark-cassandra-connector_2.12:3.5.0",
        },

        application_args=[
            "{{ ti.xcom_pull(task_ids='calc_dates')['start_date'] }}",
            "{{ ti.xcom_pull(task_ids='calc_dates')['end_date'] }}",
        ],
        verbose=True,

    )

    post_process = EmptyOperator(task_id="violations_post_process", trigger_rule="all_success")
    end = EmptyOperator(task_id="violations_complete", trigger_rule="all_done")


    start >> date_range >> run_violations_job >> post_process >> end
    run_violations_job >> end  



monthly_traffic_violations_dag()