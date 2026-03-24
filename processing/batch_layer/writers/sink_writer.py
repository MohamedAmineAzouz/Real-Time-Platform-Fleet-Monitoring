"""
writers/sink_writer.py
─────────────────────────────────────────────────────────────────────────────
Unified writer interface.

Usage:
    from writers.sink_writer import write
    write(df, "daily_truck_stats")

Routes to Cassandra (minio) or BigQuery (gcs) based on STORAGE_BACKEND.
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
    if logical_table not in BATCH_TABLES:
        raise ValueError(
            f"Unknown table '{logical_table}'. "
            f"Valid keys: {list(BATCH_TABLES.keys())}"
        )

    if is_dev():
        _write_cassandra(df, BATCH_TABLES[logical_table], mode)
    else:
        _write_bigquery(df, BIGQUERY_TABLES[logical_table], mode)


def _write_cassandra(df: DataFrame, table: str, mode: str):
    # FIX: Cassandra connector does NOT support mode="overwrite" (no TRUNCATE).
    # It only supports "append" — upserts happen automatically via primary key.
    # Passing "overwrite" raises: java.lang.IllegalArgumentException: Unsupported save mode
    (
        df.write
        .format("org.apache.spark.sql.cassandra")
        .mode("append")                              # always append — PK handles upsert
        .options(table=table, keyspace=CASSANDRA_KEYSPACE)
        .save()
    )


def _write_bigquery(df: DataFrame, table: str, mode: str):
    bq_mode = "WRITE_TRUNCATE" if mode == "overwrite" else "WRITE_APPEND"
    (
        df.write
        .format("bigquery")
        .option("table",            table)
        .option("project",          BIGQUERY_PROJECT)
        .option("writeMethod",      "indirect")
        .option("writeDisposition", bq_mode)
        .save()
    )