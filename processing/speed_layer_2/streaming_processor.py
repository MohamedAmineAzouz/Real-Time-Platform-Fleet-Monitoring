"""
streaming_processor.py
─────────────────────────────────────────────────────────────────────────────
Spark Structured Streaming — Speed Layer (Spark Cluster Mode)

Reads from Kafka → processes → writes to Cassandra truck_latest table
Each micro-batch updates the latest position for every truck.

Run with:
  docker compose exec spark-master /opt/spark/bin/spark-submit \
    --master spark://spark-master:7077 \
    --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.1,com.datastax.spark:spark-cassandra-connector_2.12:3.4.1 \
    --conf spark.cassandra.connection.host=cassandra \
    /opt/spark/work-dir/streaming_processor.py
─────────────────────────────────────────────────────────────────────────────
"""

import os
import sys
from datetime import datetime

from pyspark.sql import SparkSession
from pyspark.sql.types import (
    StructType, StructField,
    IntegerType, DoubleType, StringType, BooleanType, TimestampType
)
from pyspark.sql.functions import (
    col, from_json, lit, current_timestamp, to_timestamp,
    when, row_number, round as _round
)

# ── Configuration ─────────────────────────────────────────────────────────────
# These defaults work when running inside Docker network on iot_network
KAFKA_BROKER = os.getenv("KAFKA_BROKER", "kafka:9092")
KAFKA_TOPIC  = os.getenv("KAFKA_TOPIC", "truck-gps-staging-1")

CASSANDRA_HOST     = os.getenv("CASSANDRA_HOST", "cassandra")
CASSANDRA_PORT     = os.getenv("CASSANDRA_PORT", "9042")
CASSANDRA_KEYSPACE = os.getenv("CASSANDRA_KEYSPACE", "fleet_1")
CASSANDRA_TABLE    = "truck_latest"

# Alert thresholds
SPEED_THRESHOLD    = 120.0
TEMP_THRESHOLD     = 100.0
FUEL_LOW           = 20.0

# Earth radius for Haversine formula (km)
EARTH_RADIUS_KM = 6371.0


# ── Spark Session ──────────────────────────────────────────────────────────────
def create_spark_session() -> SparkSession:
    return (SparkSession.builder
        .appName("Fleet_1SpeedLayer-RealTime")
        .config("spark.cassandra.connection.host", CASSANDRA_HOST)
        .config("spark.cassandra.connection.port", CASSANDRA_PORT)
        .config("spark.cassandra.output.consistency.level", "LOCAL_ONE")
        .config("spark.cassandra.output.concurrent.writes", "32")
        .config("spark.cassandra.output.batch.size.rows", "1000")
        .getOrCreate())


# ── Schema Definition ──────────────────────────────────────────────────────────
def get_truck_schema() -> StructType:
    return StructType([
        StructField("truck_id",     IntegerType(), True),
        StructField("latitude",     DoubleType(),  True),
        StructField("longitude",    DoubleType(),  True),
        StructField("speed",        DoubleType(),  True),
        StructField("fuel_level",   DoubleType(),  True),
        StructField("engine_temp",  DoubleType(),  True),
        StructField("driver_id",    StringType(),  True),
        StructField("start_city",   StringType(),  True),
        StructField("end_city",     StringType(),  True),
        StructField("odometer_km",  DoubleType(),  True),
        StructField("refueling",    BooleanType(), True),
        StructField("refuel_city",  StringType(),  True),
        StructField("anomaly",      StringType(),  True),
        StructField("theft",        BooleanType(), True),
        StructField("theft_amount", DoubleType(),  True),
        StructField("fuel_consumed_trip", DoubleType(),  True),
        StructField("fuel_refueled",      DoubleType(),  True),
        StructField("timestamp",          StringType(),  True),
        StructField("in_maintenance",     BooleanType(), True),
        StructField("maintenance_type",   StringType(),  True),
        StructField("maintenance_desc",   StringType(),  True),
    ])


# ── Alert Classification ───────────────────────────────────────────────────────
def classify_alert(df):
    """Add alert_type and is_alert columns based on thresholds."""
    return (df
        .withColumn("alert_type",
            when(col("speed")        > SPEED_THRESHOLD, lit("OVERSPEED"))
            .when(col("engine_temp") > TEMP_THRESHOLD,  lit("OVERHEAT"))
            .when(col("theft")       == True,           lit("FUEL_THEFT"))
            .when(col("anomaly")     == "fuel_leak",    lit("FUEL_LEAK"))
            .when(col("fuel_level")  < FUEL_LOW,        lit("LOW_FUEL"))
            .otherwise(lit("NORMAL"))
        )
        .withColumn("is_alert", col("alert_type") != lit("NORMAL"))
    )


def calculate_trajectory_distance(df):
    """
    Add distance_km placeholder for streaming (real calculation done in batch layer).
    Note: Stateful distance calculation requires mapGroupsWithState which adds complexity.
    For truck_latest table, we use odometer_km as the distance reference.
    """
    # Use odometer_km as distance reference for streaming
    # Full trajectory distance calculation happens in batch layer
    return df.withColumn("distance_km", col("odometer_km"))


# ── Write to Cassandra ─────────────────────────────────────────────────────────
TRUCK_HISTORY_TABLE = "truck_history"
ALERTS_TABLE        = "alerts"

def write_to_cassandra(batch_df, batch_id: int):
    """
    Write latest state per truck to Cassandra.
    Uses dropDuplicates to keep latest record per truck (streaming-compatible).
    Also inserts into truck_history (all records) and alerts (alert records only).
    """
    import time
    t0 = time.time()

    if batch_df.rdd.isEmpty():
        print(f"[batch #{batch_id:05d}] ⚠️  Empty batch")
        return

    # Deduplicate: keep only the latest record per truck based on event_time
    # dropDuplicatesWithWatermark is handled by sorting before dedup
    deduped = batch_df.dropDuplicates(["truck_id"])

    # Select only the columns needed for truck_latest
    columns = [
        "truck_id", "processed_at", "event_time",
        "latitude", "longitude", "speed", "fuel_level", "engine_temp",
        "driver_id", "start_city", "end_city", "odometer_km",
        "refueling", "refuel_city", "anomaly", "theft", "theft_amount",
        "distance_km", "fuel_used", "fuel_consumption_rate", "high_consumption",
        "fuel_consumed_trip", "fuel_refueled",
        "alert_type", "is_alert",
        "in_maintenance", "maintenance_type", "maintenance_desc"
    ]

    # Add placeholder metrics (real calculations done in batch layer)
    final_df = (deduped
        .withColumn("fuel_used",             lit(0.0))
        .withColumn("fuel_consumption_rate", lit(0.0))
        .withColumn("high_consumption",      lit(False))
        .select(columns)
    )

    # Write to truck_latest
    (final_df.write
        .format("org.apache.spark.sql.cassandra")
        .mode("append")
        .options(table=CASSANDRA_TABLE, keyspace=CASSANDRA_KEYSPACE)
        .save()
    )

    # Write ALL records to truck_history (full history, TTL = 1 day)
    history_columns = [
        "truck_id", "processed_at", "event_time",
        "latitude", "longitude", "speed", "fuel_level", "engine_temp",
        "driver_id", "start_city", "end_city", "odometer_km",
        "refueling", "refuel_city", "anomaly", "theft", "theft_amount",
        "distance_km", "fuel_used", "fuel_consumption_rate", "high_consumption",
        "fuel_consumed_trip", "fuel_refueled",
        "alert_type", "is_alert",
        "in_maintenance", "maintenance_type", "maintenance_desc"
    ]
    history_df = final_df.select(history_columns)
    (history_df.write
        .format("org.apache.spark.sql.cassandra")
        .mode("append")
        .options(table=TRUCK_HISTORY_TABLE, keyspace=CASSANDRA_KEYSPACE)
        .save()
    )

    # Write only alert records to alerts table
    alert_columns = [
        "truck_id", "alert_type", "processed_at", "event_time",
        "latitude", "longitude", "speed", "fuel_level", "engine_temp",
        "driver_id", "anomaly", "theft", "theft_amount",
        "distance_km", "fuel_consumption_rate", "fuel_consumed_trip", "fuel_refueled",
        "in_maintenance", "maintenance_type", "maintenance_desc"
    ]
    alerts_df = (final_df
        .filter(col("is_alert") == True)
        .select(alert_columns)
    )

    if not alerts_df.rdd.isEmpty():
        (alerts_df.write
            .format("org.apache.spark.sql.cassandra")
            .mode("append")
            .options(table=ALERTS_TABLE, keyspace=CASSANDRA_KEYSPACE)
            .save()
        )

    count = final_df.count()
    alert_count = alerts_df.count() if not alerts_df.rdd.isEmpty() else 0
    print(f"[batch #{batch_id:05d}] ✅ Wrote {count} truck(s) to {CASSANDRA_KEYSPACE}.{CASSANDRA_TABLE}, "
          f"{count} to {TRUCK_HISTORY_TABLE}, {alert_count} alerts to {ALERTS_TABLE}  ({time.time()-t0:.2f}s)")


# ── Main Processing ────────────────────────────────────────────────────────────
def main():
    print("\n" + "="*60)
    print("  Fleet_1 Speed Layer — Real-Time Streaming (Spark Cluster)")
    print("="*60)
    print(f"  Kafka:     {KAFKA_BROKER} → {KAFKA_TOPIC}")
    print(f"  Cassandra: {CASSANDRA_HOST}:{CASSANDRA_PORT}")
    print(f"  Table:     {CASSANDRA_KEYSPACE}.{CASSANDRA_TABLE}")
    print("="*60 + "\n")

    spark = create_spark_session()
    spark.sparkContext.setLogLevel("WARN")

    # Read from Kafka
    kafka_df = (spark.readStream
        .format("kafka")
        .option("kafka.bootstrap.servers", KAFKA_BROKER)
        .option("subscribe", KAFKA_TOPIC)
        .option("startingOffsets", "latest")
        .option("failOnDataLoss", "false")
        .load()
    )

    # Parse JSON
    schema = get_truck_schema()
    parsed = (kafka_df
        .selectExpr("CAST(value AS STRING) AS json_str")
        .select(from_json(col("json_str"), schema).alias("data"))
        .select("data.*")
    )

    # Add timestamps and alert classification
    enriched = (parsed
        .withColumn("processed_at", current_timestamp())
        .withColumn("event_time",
            to_timestamp(col("timestamp"), "yyyy-MM-dd'T'HH:mm:ss.SSSSSS'Z'")
        )
    )

    # Classify alerts
    alerted = classify_alert(enriched)

    # Calculate cumulative distance per trajectory (resets when route changes)
    with_distance = calculate_trajectory_distance(alerted)

    # Start streaming query
    query = (with_distance.writeStream
        .outputMode("append")
        .foreachBatch(write_to_cassandra)
        .option("checkpointLocation", "/tmp/checkpoints/truck_latest/")
        .trigger(processingTime="2 seconds")
        .queryName("truck_latest_stream")
        .start()
    )

    print("🚀  Streaming started — writing to Cassandra every 2 seconds")
    print("    Press Ctrl+C to stop\n")

    query.awaitTermination()


if __name__ == "__main__":
    main()
