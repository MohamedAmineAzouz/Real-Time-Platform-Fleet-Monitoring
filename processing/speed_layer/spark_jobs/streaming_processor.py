"""
streaming_processor.py
─────────────────────────────────────────────────────────────────────────────
Spark Structured Streaming — Speed Layer

Each sink is an INDEPENDENT streaming query reading Kafka directly.
They run in parallel — if one is slow or fails, the others keep running.

  Kafka (truck-gps)
        │
        ├─▶ query_latest   → Cassandra truck_latest   (2s  trigger)
        ├─▶ query_history  → Cassandra truck_history  (5s  trigger)
        ├─▶ query_alerts   → Cassandra alerts         (2s  trigger, filtered)
        ├─▶ query_parquet  → MinIO/GCS raw_events     (30s trigger)
        └─▶ query_agg      → MinIO/GCS aggregates     (60s trigger, windowed)

Why one query per sink (vs one foreachBatch doing everything sequentially):
  - No sink waits for another — truck_latest updates every 2s even if
    truck_history is mid-write
  - A slow MinIO write never delays Cassandra
  - Each query has its own checkpoint — one failure is isolated
  - Triggers tuned independently per sink
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
    lag, radians, sin, cos, asin, sqrt,
    row_number,
)
from pyspark.sql.types import (
    StructType, StructField,
    IntegerType, DoubleType, StringType, BooleanType,
)

from config.storage_config import (
    PATHS, get_spark_storage_conf, print_config,
)
from config.cassandra_config import (
    CASSANDRA_KEYSPACE, TABLES,
    get_spark_cassandra_conf,
    print_config as print_cassandra_config,
)

# ── Kafka ──────────────────────────────────────────────────────────────────────
KAFKA_BROKER = os.getenv("KAFKA_BROKER", "kafka:9092")
KAFKA_TOPIC  = os.getenv("KAFKA_TOPIC",  "truck-gps")

# ── Alert thresholds ───────────────────────────────────────────────────────────
SPEED_THRESHOLD        = 120.0
TEMP_THRESHOLD         = 100.0
FUEL_LOW               = 20.0
FUEL_CONSUMPTION_LIMIT = 0.5
EARTH_RADIUS_KM        = 6371.0

# Max rows written per truck per batch for truck_history.
# Prevents a Kafka catch-up batch (e.g. 959 rows) from flooding Cassandra.
# Complete history is preserved in Parquet.
_MAX_HISTORY_PER_TRUCK = 5

# ── Column selections ──────────────────────────────────────────────────────────
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
    for k, v in get_spark_storage_conf().items():
        builder = builder.config(k, v)
    for k, v in get_spark_cassandra_conf().items():
        builder = builder.config(k, v)
    return builder.getOrCreate()


# ─────────────────────────────────────────────────────────────────────────────
def parse_kafka(spark: SparkSession) -> DataFrame:
    """
    Read Kafka and parse JSON → typed + enriched streaming DataFrame.
    All 5 queries share this base DF — Spark creates one Kafka consumer
    group per query internally, each tracking its own offsets.
    """
    schema = StructType([
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

    raw = (
        spark.readStream
        .format("kafka")
        .option("kafka.bootstrap.servers", KAFKA_BROKER)
        .option("subscribe",               KAFKA_TOPIC)
        .option("startingOffsets",         "latest")
        .option("failOnDataLoss",          "false")
        .load()
    )

    return (
        raw
        .selectExpr("CAST(value AS STRING) AS json_str")
        .select(from_json(col("json_str"), schema).alias("d"))
        .select("d.*")
        # Alert classification + timestamps — streaming-safe, no window functions
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
    Haversine distance + fuel consumption rate.
    Uses lag() — valid only inside foreachBatch (static DataFrame).
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
        .withColumn("high_consumption",
            col("fuel_consumption_rate") > FUEL_CONSUMPTION_LIMIT
        )
        .drop("prev_lat", "prev_lon", "prev_fuel")
    )


# ═════════════════════════════════════════════════════════════════════════════
#  QUERY 1 — truck_latest
#
#  Fastest path: 1 row per truck, no Haversine (placeholder 0.0 metrics).
#  The frontend map reads this table → low latency = good UX.
#  Trigger: 2s
# ═════════════════════════════════════════════════════════════════════════════
def batch_latest(batch_df: DataFrame, batch_id: int):
    import time
    t0 = time.time()

    if not batch_df.take(1):
        return

    dedup_w = Window.partitionBy("truck_id").orderBy(col("event_time").desc())

    (
        batch_df
        .withColumn("_rn", row_number().over(dedup_w))
        .filter(col("_rn") == 1)
        .drop("_rn")
        .withColumn("distance_km",           lit(0.0))
        .withColumn("fuel_used",             lit(0.0))
        .withColumn("fuel_consumption_rate", lit(0.0))
        .withColumn("high_consumption",      lit(False))
        .select(_TELEMETRY_COLS)
        .write
        .format("org.apache.spark.sql.cassandra")
        .mode("append")
        .options(table=TABLES["truck_latest"], keyspace=CASSANDRA_KEYSPACE)
        .save()
    )

    print(f"[latest  #{batch_id:05d}] ✅  {time.time()-t0:.2f}s")


# ═════════════════════════════════════════════════════════════════════════════
#  QUERY 2 — truck_history
#
#  Full metrics (Haversine + fuel rate). Capped to _MAX_HISTORY_PER_TRUCK
#  rows per truck per batch — prevents Kafka catch-up floods.
#  Trigger: 5s (slightly relaxed — history is less latency-sensitive)
# ═════════════════════════════════════════════════════════════════════════════
def batch_history(batch_df: DataFrame, batch_id: int):
    import time
    t0 = time.time()

    if not batch_df.take(1):
        return

    history_w = Window.partitionBy("truck_id").orderBy(col("event_time").desc())

    capped = (
        batch_df
        .withColumn("_rn", row_number().over(history_w))
        .filter(col("_rn") <= _MAX_HISTORY_PER_TRUCK)
        .drop("_rn")
    )

    enriched = add_computed_metrics(capped)

    (
        enriched
        .select(_TELEMETRY_COLS)
        .write
        .format("org.apache.spark.sql.cassandra")
        .mode("append")
        .options(table=TABLES["truck_history"], keyspace=CASSANDRA_KEYSPACE)
        .save()
    )

    print(f"[history #{batch_id:05d}] ✅  {time.time()-t0:.2f}s")


# ═════════════════════════════════════════════════════════════════════════════
#  QUERY 3 — alerts
#
#  Filters only alert rows before writing. Skips batch entirely if no alerts.
#  Trigger: 2s (same as latest — alerts should appear on map quickly)
# ═════════════════════════════════════════════════════════════════════════════
def batch_alerts(batch_df: DataFrame, batch_id: int):
    import time
    t0 = time.time()

    alerts = batch_df.filter(col("is_alert") == True)

    if not alerts.take(1):
        return

    (
        alerts
        .withColumn("distance_km",          lit(0.0))
        .withColumn("fuel_consumption_rate", lit(0.0))
        .select(_ALERT_COLS)
        .write
        .format("org.apache.spark.sql.cassandra")
        .mode("append")
        .options(table=TABLES["alerts"], keyspace=CASSANDRA_KEYSPACE)
        .save()
    )

    alert_count = alerts.count()
    print(f"[alerts  #{batch_id:05d}] 🚨  {alert_count} alert(s)  {time.time()-t0:.2f}s")


# ═════════════════════════════════════════════════════════════════════════════
#  QUERY 4 — Parquet raw archive
#
#  Writes all events with full metrics to MinIO/GCS.
#  Slower trigger — this is a historical archive, not real-time.
#  A slow MinIO write here never affects Cassandra.
#  Trigger: 30s
# ═════════════════════════════════════════════════════════════════════════════
def batch_parquet(batch_df: DataFrame, batch_id: int):
    import time
    t0 = time.time()

    if not batch_df.take(1):
        return

    enriched = add_computed_metrics(batch_df)

    (
        enriched
        .select(_TELEMETRY_COLS)
        .write
        .mode("append")
        .parquet(PATHS["raw_events"])
    )

    print(f"[parquet #{batch_id:05d}] ✅  {time.time()-t0:.2f}s")


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

    # Shared base streaming DF — parsed + alert-enriched Kafka stream.
    # Each query below gets its own Kafka consumer group + checkpoint.
    base = parse_kafka(spark)

    # ── Query 1: truck_latest — 2s ────────────────────────────────────────────
    q_latest = (
        base.writeStream
        .outputMode("append")
        .foreachBatch(batch_latest)
        .option("checkpointLocation", PATHS["checkpoints"] + "latest/")
        .trigger(processingTime="2 seconds")
        .queryName("truck_latest")
        .start()
    )

    # ── Query 2: truck_history — 5s ───────────────────────────────────────────
    q_history = (
        base.writeStream
        .outputMode("append")
        .foreachBatch(batch_history)
        .option("checkpointLocation", PATHS["checkpoints"] + "history/")
        .trigger(processingTime="5 seconds")
        .queryName("truck_history")
        .start()
    )

    # ── Query 3: alerts — 2s ─────────────────────────────────────────────────
    q_alerts = (
        base.writeStream
        .outputMode("append")
        .foreachBatch(batch_alerts)
        .option("checkpointLocation", PATHS["checkpoints"] + "alerts/")
        .trigger(processingTime="2 seconds")
        .queryName("alerts")
        .start()
    )

    # ── Query 4: Parquet raw archive — 30s ───────────────────────────────────
    q_parquet = (
        base.writeStream
        .outputMode("append")
        .foreachBatch(batch_parquet)
        .option("checkpointLocation", PATHS["checkpoints"] + "parquet/")
        .trigger(processingTime="30 seconds")
        .queryName("parquet_archive")
        .start()
    )

    # ── Query 5: windowed aggregates → Parquet — 60s ─────────────────────────
    windowed = (
        base
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
            col("avg_speed"),       col("max_speed"),
            col("avg_engine_temp"), col("max_engine_temp"),
            col("min_fuel_level"),  col("avg_fuel_level"),
            col("event_count"),
        )
    )

    q_agg = (
        windowed.writeStream
        .outputMode("append")
        .format("parquet")
        .option("path",               PATHS["aggregates"])
        .option("checkpointLocation", PATHS["checkpoints"] + "aggregates/")
        .trigger(processingTime="60 seconds")
        .queryName("aggregates")
        .start()
    )

    print("🚀  5 independent streaming queries running:")
    print(f"    • [truck_latest]    trigger=2s   → Cassandra (1 row/truck)")
    print(f"    • [truck_history]   trigger=5s   → Cassandra (last {_MAX_HISTORY_PER_TRUCK} rows/truck)")
    print(f"    • [alerts]          trigger=2s   → Cassandra (alert events only)")
    print(f"    • [parquet_archive] trigger=30s  → {PATHS['raw_events']}")
    print(f"    • [aggregates]      trigger=60s  → {PATHS['aggregates']}")
    print()

    spark.streams.awaitAnyTermination()


if __name__ == "__main__":
    main()