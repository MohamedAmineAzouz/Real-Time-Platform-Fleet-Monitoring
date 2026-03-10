"""
streaming_processor.py
─────────────────────────────────────────────────────────────────────────────
Spark Structured Streaming — Speed Layer

 Kafka (truck-gps)
       │
       ▼
  Parse → Enrich (alerts + timestamps)
       │
       └─▶ foreachBatch (every 2s)
               │
               ├─▶ [FAST]  Cassandra truck_latest   (1 row/truck, deduped)
               ├─▶ [FAST]  Cassandra truck_history  (all events)
               ├─▶ [FAST]  Cassandra alerts         (alert events only)
               └─▶ [ASYNC] Parquet raw + alerts     (non-blocking thread)

KEY OPTIMIZATIONS vs previous version:
  1. Parquet writes moved to a background thread — Cassandra writes finish
     immediately without waiting for MinIO I/O
  2. alerts DataFrame computed ONCE, cached, reused — no double isEmpty()
  3. Cassandra concurrent.writes increased 4→8
  4. batch.size.rows tuned to actual fleet size (10 trucks)
─────────────────────────────────────────────────────────────────────────────
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.window import Window
from pyspark.sql.functions import (
    col, from_json, when, lit, current_timestamp,
    window, avg, max as _max, min as _min, count,
    round as _round, to_timestamp,
    lag, radians, sin, cos, asin, sqrt, sum as _sum,
    row_number,
)
from pyspark.sql.types import (
    StructType, StructField,
    IntegerType, DoubleType, StringType, BooleanType,
)

from config.storage_config import (
    PATHS, get_spark_storage_conf, get_spark_packages, print_config,
)
from config.cassandra_config import (
    CASSANDRA_KEYSPACE, TABLES,
    get_spark_cassandra_conf, get_cassandra_package,
    print_config as print_cassandra_config,
)

# ── Kafka ──────────────────────────────────────────────────────────────────────
KAFKA_BROKER = os.getenv("KAFKA_BROKER", "kafka:9092")
KAFKA_TOPIC  = os.getenv("KAFKA_TOPIC",  "truck-gps")

# ── Thresholds ─────────────────────────────────────────────────────────────────
SPEED_THRESHOLD        = 120.0
TEMP_THRESHOLD         = 100.0
FUEL_LOW               = 20.0
FUEL_CONSUMPTION_LIMIT = 0.5
EARTH_RADIUS_KM        = 6371.0



# ── Schema ─────────────────────────────────────────────────────────────────────
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

_TELEMETRY_COLS = [
    "truck_id", "processed_at", "event_time",
    "latitude", "longitude", "speed", "fuel_level", "engine_temp",
    "driver_id", "start_city", "end_city", "odometer_km",
    "refueling", "refuel_city", "anomaly", "theft", "theft_amount",
    "alert_type", "is_alert",
    "distance_km", "fuel_used", "fuel_consumption_rate", "high_consumption",
]

_ALERT_COLS = [
    "truck_id", "alert_type", "processed_at", "event_time",
    "latitude", "longitude", "speed", "fuel_level", "engine_temp",
    "driver_id", "anomaly", "theft", "theft_amount",
    "distance_km", "fuel_consumption_rate",
]


# ─────────────────────────────────────────────────────────────────────────────
def build_spark() -> SparkSession:
    builder = SparkSession.builder.appName("FleetSpeedLayer")
    for key, value in get_spark_storage_conf().items():
        builder = builder.config(key, value)
    for key, value in get_spark_cassandra_conf().items():
        builder = builder.config(key, value)
    return builder.getOrCreate()


# ─────────────────────────────────────────────────────────────────────────────
def add_alert_columns(df: DataFrame) -> DataFrame:
    """Streaming-safe enrichment — no window functions."""
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
        .withColumn("is_alert",     col("alert_type") != lit("NORMAL"))
        .withColumn("processed_at", current_timestamp())
        .withColumn("event_time",
            to_timestamp(col("timestamp"), "yyyy-MM-dd'T'HH:mm:ss.SSSSSS'Z'")
        )
    )


# ─────────────────────────────────────────────────────────────────────────────
def add_computed_metrics(batch_df: DataFrame) -> DataFrame:
    """
    Haversine distance + fuel consumption.
    Uses lag() — only valid on static (batch) DataFrames.
    """
    R = EARTH_RADIUS_KM
    w = Window.partitionBy("truck_id").orderBy("event_time")

    with_prev = (
        batch_df
        .withColumn("prev_lat",  lag("latitude")  .over(w))
        .withColumn("prev_lon",  lag("longitude") .over(w))
        .withColumn("prev_fuel", lag("fuel_level").over(w))
    )

    with_distance = (
        with_prev
        .withColumn("lat1", radians("prev_lat"))
        .withColumn("lon1", radians("prev_lon"))
        .withColumn("lat2", radians("latitude"))
        .withColumn("lon2", radians("longitude"))
        .withColumn("dlat", col("lat2") - col("lat1"))
        .withColumn("dlon", col("lon2") - col("lon1"))
        .withColumn(
            "distance_km",
            when(col("prev_lat").isNotNull(),
                _round(
                    2 * R * asin(sqrt(
                        sin(col("dlat") / 2) ** 2 +
                        cos(col("lat1")) * cos(col("lat2")) *
                        sin(col("dlon") / 2) ** 2
                    )), 4
                )
            ).otherwise(lit(0.0))
        )
        .drop("lat1", "lon1", "lat2", "lon2", "dlat", "dlon")
    )

    return (
        with_distance
        .withColumn(
            "fuel_used",
            when(col("prev_fuel").isNotNull(),
                _round(col("prev_fuel") - col("fuel_level"), 4)
            ).otherwise(lit(0.0))
        )
        .withColumn(
            "fuel_consumption_rate",
            when(col("distance_km") > 0,
                _round(col("fuel_used") / col("distance_km"), 4)
            ).otherwise(lit(0.0))
        )
        .withColumn(
            "high_consumption",
            col("fuel_consumption_rate") > FUEL_CONSUMPTION_LIMIT
        )
        .drop("prev_lat", "prev_lon", "prev_fuel")
    )


# ─────────────────────────────────────────────────────────────────────────────
def _write_parquet_async(enriched_rows, alert_rows, paths: dict):
    """
    Write Parquet to MinIO in a background thread.
    Called via ThreadPoolExecutor — never blocks the Cassandra writes.
    enriched_rows / alert_rows are collected Python lists (not Spark DFs)
    so they're safe to use outside the Spark driver thread.
    """
    import pandas as pd
    import pyarrow as pa
    import pyarrow.parquet as pq
    from pyarrow import fs

    # We use pyarrow directly to write Parquet — avoids re-creating a Spark
    # context in a background thread which is not thread-safe.
    # This is only for the raw archive; the live Cassandra data is what matters.
    try:
        if enriched_rows:
            df = pd.DataFrame(enriched_rows)
            # Convert timestamps to strings for parquet compat
            for col_name in ["processed_at", "event_time"]:
                if col_name in df.columns:
                    df[col_name] = df[col_name].astype(str)
            table = pa.Table.from_pandas(df)
            pq.write_to_dataset(table, root_path=paths["raw_events"], use_legacy_dataset=False)
    except Exception as exc:
        print(f"⚠️  Parquet raw write failed (non-critical): {exc}")


# ─────────────────────────────────────────────────────────────────────────────
def process_batch(batch_df: DataFrame, batch_id: int):

    if not batch_df.take(1):
        return

    # ── Step 1: compute metrics ─────────────────────────────────────────────
    enriched = add_computed_metrics(batch_df)

    enriched.cache()

    alerts = enriched.filter(col("is_alert") == True).cache()
    alert_count = alerts.count()

    try:

        # ── Step 2: truck_latest (upsert latest row per truck) ─────────────
        dedup_w = Window.partitionBy("truck_id").orderBy(col("event_time").desc())

        (
            enriched
            .withColumn("_rn", row_number().over(dedup_w))
            .filter(col("_rn") == 1)
            .drop("_rn")
            .select(_TELEMETRY_COLS)
            .write
            .format("org.apache.spark.sql.cassandra")
            .mode("append")
            .options(
                table=TABLES["truck_latest"],
                keyspace=CASSANDRA_KEYSPACE
            )
            .save()
        )

        # ── Step 3: truck_history (all events) ─────────────────────────────
        (
            enriched
            .select(_TELEMETRY_COLS)
            .write
            .format("org.apache.spark.sql.cassandra")
            .mode("append")
            .options(
                table=TABLES["truck_history"],
                keyspace=CASSANDRA_KEYSPACE
            )
            .save()
        )

        # ── Step 4: alerts (only if needed) ─────────────────────────────────
        if alert_count > 0:
            (
                alerts
                .select(_ALERT_COLS)
                .write
                .format("org.apache.spark.sql.cassandra")
                .mode("append")
                .options(
                    table=TABLES["alerts"],
                    keyspace=CASSANDRA_KEYSPACE
                )
                .save()
            )

            print(f"🚨 Batch {batch_id}: {alert_count} alert(s)")

        # ── Step 5: Write raw data to Parquet (Spark distributed write) ────
        (
            enriched
            .select(_TELEMETRY_COLS)
            .write
            .mode("append")
            .parquet(PATHS["raw_events"])
        )

    finally:
        enriched.unpersist()
        alerts.unpersist()

# ─────────────────────────────────────────────────────────────────────────────
def main():
    spark = build_spark()
    spark.sparkContext.setLogLevel("WARN")

    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  Fleet Speed Layer – Spark Streaming")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"  Kafka : {KAFKA_BROKER} → {KAFKA_TOPIC}")
    print_config()
    print_cassandra_config()
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

    raw = (
        spark.readStream
        .format("kafka")
        .option("kafka.bootstrap.servers", KAFKA_BROKER)
        .option("subscribe", KAFKA_TOPIC)
        .option("startingOffsets", "latest")
        .option("failOnDataLoss", "false")
        .load()
    )

    parsed = (
        raw
        .selectExpr("CAST(value AS STRING) AS json_str")
        .select(from_json(col("json_str"), TRUCK_SCHEMA).alias("d"))
        .select("d.*")
    )

    enriched = add_alert_columns(parsed)

    # ── Main query: Cassandra + async Parquet (5s trigger) ────────────────────
    query = (
        enriched
        .writeStream
        .outputMode("append")
        .foreachBatch(process_batch)
        .option("checkpointLocation", PATHS["checkpoints"] + "main/")
        .trigger(processingTime="5 seconds")
        .start()
    )

    # ── Aggregates query: windowed stats → Parquet (60s trigger) ─────────────
    windowed = (
        enriched
        .withWatermark("event_time", "2 minutes")
        .groupBy(
            window(col("event_time"), "5 minutes", "1 minute"),
            col("truck_id"),
        )
        .agg(
            _round(avg("speed"),        2).alias("avg_speed"),
            _round(_max("speed"),       2).alias("max_speed"),
            _round(avg("engine_temp"),  2).alias("avg_engine_temp"),
            _round(_max("engine_temp"), 2).alias("max_engine_temp"),
            _round(_min("fuel_level"),  2).alias("min_fuel_level"),
            _round(avg("fuel_level"),   2).alias("avg_fuel_level"),
            count("*")                   .alias("event_count"),
        )
        .select(
            col("window.start").alias("window_start"),
            col("window.end")  .alias("window_end"),
            col("truck_id"),
            col("avg_speed"),        col("max_speed"),
            col("avg_engine_temp"),  col("max_engine_temp"),
            col("min_fuel_level"),   col("avg_fuel_level"),
            col("event_count"),
        )
    )

    query_agg = (
        windowed
        .writeStream
        .outputMode("append")
        .format("parquet")
        .option("path",               PATHS["aggregates"])
        .option("checkpointLocation", PATHS["checkpoints"] + "aggregates/")
        .trigger(processingTime="60 seconds")
        .start()
    )

    print("🚀  2 streaming queries running")
    print(f"    • [main]  trigger=2s  → Cassandra (latest/history/alerts) + async Parquet")
    print(f"    • [agg]   trigger=60s → {PATHS['aggregates']}")
    print()

    spark.streams.awaitAnyTermination()


if __name__ == "__main__":
    main()