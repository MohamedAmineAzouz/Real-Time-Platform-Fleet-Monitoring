"""
streaming_processor.py
─────────────────────────────────────────────────────────────────────────────
Spark Structured Streaming — Speed Layer

 Kafka (truck-gps)
       │
       ▼
  Parse + Enrich (anomaly detection)
       │
       ├─▶ [Sink 1]  Storage/raw/truck_events/    Parquet  (every 10 s)
       ├─▶ [Sink 2]  Storage/alerts/              Parquet  (every 5 s)
       ├─▶ [Sink 3]  Storage/aggregates/          Parquet  (5-min windows)
       └─▶ [Sink 4]  Console                      ALERT rows only (debug)

Storage backend is controlled by STORAGE_BACKEND env var ("minio" | "gcs").
─────────────────────────────────────────────────────────────────────────────
"""

import os
import sys

# So Python finds storage_config regardless of working directory
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col, from_json, when, lit, current_timestamp,
    window, avg, max as _max, min as _min, count,
    round as _round, to_timestamp,
)
from pyspark.sql.types import (
    StructType, StructField,
    IntegerType, DoubleType, StringType, BooleanType,
)

from processing.speed_layer.config.storage_config import (
    PATHS, get_spark_storage_conf, get_spark_packages, print_config
)

# ── Kafka ──────────────────────────────────────────────────────────────────────
KAFKA_BROKER = os.getenv("KAFKA_BROKER", "kafka:9092")
KAFKA_TOPIC  = os.getenv("KAFKA_TOPIC",  "truck-gps")

# ── Anomaly thresholds ─────────────────────────────────────────────────────────
SPEED_THRESHOLD = 120.0   # km/h
TEMP_THRESHOLD  = 100.0   # °C
FUEL_LOW        = 20.0    # %

# ── Truck telemetry schema (matches IoT simulator output) ──────────────────────
TRUCK_SCHEMA = StructType([
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
    StructField("timestamp",    StringType(),  True),
])


# ─────────────────────────────────────────────────────────────────────────────
def build_spark() -> SparkSession:
    builder = SparkSession.builder.appName("FleetSpeedLayer")

    # Apply all storage-backend Hadoop configs
    for key, value in get_spark_storage_conf().items():
        builder = builder.config(key, value)

    return builder.getOrCreate()


# ─────────────────────────────────────────────────────────────────────────────
def add_alert_columns(df):
    """
    Derive alert_type and is_alert from telemetry values.
    Priority: OVERSPEED > OVERHEAT > FUEL_THEFT > FUEL_LEAK > LOW_FUEL > NORMAL
    """
    return (
        df
        .withColumn(
            "alert_type",
            when(col("speed")        > SPEED_THRESHOLD, lit("OVERSPEED"))
            .when(col("engine_temp") > TEMP_THRESHOLD,  lit("OVERHEAT"))
            .when(col("theft")       == True,           lit("FUEL_THEFT"))
            .when(col("anomaly")     == "fuel_leak",    lit("FUEL_LEAK"))
            .when(col("fuel_level")  < FUEL_LOW,        lit("LOW_FUEL"))
            .otherwise(lit("NORMAL"))
        )
        .withColumn("is_alert",      col("alert_type") != lit("NORMAL"))
        .withColumn("processed_at",  current_timestamp())
        .withColumn("event_time",
            to_timestamp(col("timestamp"), "yyyy-MM-dd'T'HH:mm:ss.SSSSSS'Z'")
        )
    )


# ─────────────────────────────────────────────────────────────────────────────
def main():
    spark = build_spark()
    spark.sparkContext.setLogLevel("WARN")

    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  Fleet Speed Layer – Spark Streaming")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"  Kafka : {KAFKA_BROKER} → {KAFKA_TOPIC}")
    print_config()
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

    # ── 1. Read raw stream from Kafka ─────────────────────────────────────────
    raw = (
        spark.readStream
        .format("kafka")
        .option("kafka.bootstrap.servers", KAFKA_BROKER)
        .option("subscribe", KAFKA_TOPIC)
        .option("startingOffsets", "latest")
        .option("failOnDataLoss", "false")
        .load()
    )

    # ── 2. Parse JSON + enrich ────────────────────────────────────────────────
    parsed = (
        raw
        .selectExpr("CAST(value AS STRING) AS json_str")
        .select(from_json(col("json_str"), TRUCK_SCHEMA).alias("d"))
        .select("d.*")
    )

    enriched = add_alert_columns(parsed)

    # ─────────────────────────────────────────────────────────────────────────
    # SINK 1 — All events → Storage/raw/truck_events/  (Parquet)
    # Partitioned by alert_type so downstream batch jobs scan efficiently.
    # ─────────────────────────────────────────────────────────────────────────
    sink_raw = (
        enriched
        .writeStream
        .outputMode("append")
        .format("parquet")
        .option("path",              PATHS["raw_events"])
        .option("checkpointLocation", PATHS["checkpoints"] + "parquet_raw/")
        .partitionBy("alert_type")
        .trigger(processingTime="10 seconds")
        .start()
    )

    # ─────────────────────────────────────────────────────────────────────────
    # SINK 2 — Alerts only → Storage/alerts/  (Parquet, fast path)
    # ─────────────────────────────────────────────────────────────────────────
    sink_alerts = (
        enriched
        .filter(col("is_alert") == True)
        .writeStream
        .outputMode("append")
        .format("parquet")
        .option("path",              PATHS["alerts"])
        .option("checkpointLocation", PATHS["checkpoints"] + "parquet_alerts/")
        .trigger(processingTime="5 seconds")
        .start()
    )

    # ─────────────────────────────────────────────────────────────────────────
    # SINK 3 — 5-minute rolling window aggregates → Storage/aggregates/
    # One row per (truck_id, window) with avg/max speed, temp, min fuel.
    # ─────────────────────────────────────────────────────────────────────────
    windowed = (
        enriched
        .withWatermark("event_time", "2 minutes")
        .groupBy(
            window(col("event_time"), "5 minutes", "1 minute"),
            col("truck_id"),
        )
        .agg(
            _round(avg("speed"),          2).alias("avg_speed"),
            _round(_max("speed"),         2).alias("max_speed"),
            _round(avg("engine_temp"),    2).alias("avg_engine_temp"),
            _round(_max("engine_temp"),   2).alias("max_engine_temp"),
            _round(_min("fuel_level"),    2).alias("min_fuel_level"),
            _round(avg("fuel_level"),     2).alias("avg_fuel_level"),
            count("*")                     .alias("event_count"),
        )
        .select(
            col("window.start").alias("window_start"),
            col("window.end")  .alias("window_end"),
            col("truck_id"),
            col("avg_speed"),       col("max_speed"),
            col("avg_engine_temp"), col("max_engine_temp"),
            col("min_fuel_level"),  col("avg_fuel_level"),
            col("event_count"),
        )
    )

    sink_agg = (
        windowed
        .writeStream
        .outputMode("append")
        .format("parquet")
        .option("path",              PATHS["aggregates"])
        .option("checkpointLocation", PATHS["checkpoints"] + "aggregates/")
        .trigger(processingTime="60 seconds")
        .start()
    )

    # ─────────────────────────────────────────────────────────────────────────
    # SINK 4 — Console (alert rows only, for local debugging)
    # ─────────────────────────────────────────────────────────────────────────
    sink_console = (
        enriched
        .filter(col("is_alert") == True)
        .select(
            "truck_id", "alert_type",
            "speed", "engine_temp", "fuel_level",
            "latitude", "longitude", "anomaly", "theft",
        )
        .writeStream
        .outputMode("append")
        .format("console")
        .option("truncate", False)
        .option("numRows",  20)
        .trigger(processingTime="10 seconds")
        .start()
    )

    print(f"🚀  4 streaming sinks running")
    print(f"    • raw events  → {PATHS['raw_events']}")
    print(f"    • alerts      → {PATHS['alerts']}")
    print(f"    • aggregates  → {PATHS['aggregates']}")
    print(f"    • console     → alert rows only\n")

    spark.streams.awaitAnyTermination()


if __name__ == "__main__":
    main()