"""
writers/sink_writer.py
─────────────────────────────────────────────────────────────────────────────
Unified writer interface.

Usage (same call regardless of backend):

    from writers.sink_writer import write

    write(df, "daily_truck_stats", mode="overwrite")

Internally routes to:
  dev      → Cassandra via spark-cassandra-connector
  staging  → BigQuery  via spark-bigquery connector
  prod     → BigQuery  via spark-bigquery connector
─────────────────────────────────────────────────────────────────────────────
"""

from pyspark.sql import DataFrame
from batch_config.batch_config import (
    is_dev,
    CASSANDRA_KEYSPACE,
    BATCH_TABLES,
    BIGQUERY_TABLES,
    BIGQUERY_PROJECT,
)


def write(df: DataFrame, logical_table: str, mode: str = "overwrite"):
    """
    Write a DataFrame to the configured sink.

    Args:
        df:            Spark DataFrame to write.
        logical_table: Key from BATCH_TABLES (e.g. "daily_truck_stats").
        mode:          "overwrite" (default) or "append".
                       Cassandra does upserts on overwrite via primary key.
                       BigQuery truncates + rewrites on overwrite.
    """
    if logical_table not in BATCH_TABLES:
        raise ValueError(
            f"Unknown table '{logical_table}'. "
            f"Valid keys: {list(BATCH_TABLES.keys())}"
        )

    if is_dev():
        _write_cassandra(df, BATCH_TABLES[logical_table], mode)
    else:
        _write_bigquery(df, BIGQUERY_TABLES[logical_table], mode)


# ─────────────────────────────────────────────────────────────────────────────
def _write_cassandra(df: DataFrame, table: str, mode: str):
    (
        df.write
        .format("org.apache.spark.sql.cassandra")
        .mode(mode)
        .options(table=table, keyspace=CASSANDRA_KEYSPACE)
        .save()
    )


def _write_bigquery(df: DataFrame, table: str, mode: str):
    bq_mode = "WRITE_TRUNCATE" if mode == "overwrite" else "WRITE_APPEND"
    (
        df.write
        .format("bigquery")
        .option("table",        table)
        .option("project",      BIGQUERY_PROJECT)
        .option("writeMethod",  "indirect")          # uses GCS as staging area
        .option("writeDisposition", bq_mode)
        .save()
    )