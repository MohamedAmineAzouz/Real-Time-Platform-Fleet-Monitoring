import os
import sys
from pyspark.sql import SparkSession, DataFrame, Window
from pyspark.sql.functions import (
    col, sum as _sum, avg as _avg, count, countDistinct,
    to_date, lit, when, round as _round, lag
)

# ── Configuration ─────────────────────────────────────────────────────────
CASSANDRA_KEYSPACE = os.getenv("CASSANDRA_KEYSPACE", "fleet")
LAKE_BUCKET = os.getenv("LAKE_BUCKET", "fleet-data")
LAKE_PREFIX = os.getenv("LAKE_PREFIX", "silver/truck_history")
S3_PATH = f"s3a://{LAKE_BUCKET}/{LAKE_PREFIX}"

def compute_route_efficiency(telemetry_df: DataFrame, trajets_df: DataFrame, run_date: str) -> DataFrame:
    """
    Groups telemetry by Route, Truck, and Driver.
    Compares total_distance_km with trajets_df to determine finish status.
    """

    # ── Step 1: Calculate Time Deltas ─────────────────────────────────────
    w_trip = Window.partitionBy("truck_id", "driver_id", "start_city", "end_city").orderBy("event_time")

    with_time = (
        telemetry_df
        .withColumn("prev_time", lag("event_time", 1).over(w_trip))
        .withColumn(
            "duration_sec",
            when(col("prev_time").isNotNull(),
                col("event_time").cast("long") - col("prev_time").cast("long")
            ).otherwise(lit(0))
        )
        .withColumn("duration_sec", when(col("duration_sec") > 600, lit(600)).otherwise(col("duration_sec")))
    )

    # ── Step 2: Aggregate by Route + Truck + Driver ───────────────────────
    route_stats = (
        with_time
        .groupBy("start_city", "end_city", "truck_id", "driver_id")
        .agg(
            lit(1).alias("total_trips"),
            _round(_sum("distance_km"), 2).alias("total_distance_km"),
            _round(_sum("fuel_consumed_l"), 2).alias("total_fuel_consumed_l"),
            _round(_avg("speed"), 2).alias("avg_speed_kmh"),
            _round(_sum("duration_sec") / 3600.0, 2).alias("total_duration_h"),
            _sum(when(col("is_alert") == True, 1).otherwise(0)).alias("total_alerts")
        )
    )

    # ── Step 3: Join with Trajets for Target Distance ─────────────────────
    # Standardize trajets: one record per city pair
    std_trajets = trajets_df.groupBy("start_city", "end_city").agg(_avg("distance_km").alias("target_distance_km"))

    with_targets = route_stats.join(std_trajets, ["start_city", "end_city"], "left")

    # ── Step 4: Determine Finish Status ───────────────────────────────────
    # We consider a route 'finished' if actual distance is >= 95% of target
    # target_distance_km is used only for calculation and not saved to Cassandra
    final_df = (
        with_targets
        .withColumn(
            "status",
            when(
                (col("target_distance_km").isNotNull()) &
                (col("total_distance_km") >= (col("target_distance_km") * 0.95)),
                lit("finished")
            ).otherwise(lit("unfinished"))
        )
        .withColumn(
            "avg_fuel_per_100km",
            _round(
                when(col("total_distance_km") > 0,
                    (col("total_fuel_consumed_l") / col("total_distance_km")) * 100.0
                ).otherwise(lit(0.0)), 2
            )
        )
        .withColumn(
            "avg_alerts_per_trip",
            _round(
                when(col("total_trips") > 0,
                    col("total_alerts") / col("total_trips")
                ).otherwise(lit(0.0)), 2
            )
        )
        .withColumn("stat_date", lit(run_date))
        .drop("total_alerts", "target_distance_km") # DROPPED target_distance_km
    )

    return final_df

def run_job(spark: SparkSession, date_from: str, date_to: str):
    print(f"🛣️ Starting Route Efficiency Job: {date_from}")

    # ── 1. Load Data ──────────────────────────────────────────────────────
    # Read specifically from the event_date partition in MinIO
    partition_path = f"{S3_PATH}/event_date={date_from}"
    print(f"📖 Reading telemetry partition from MinIO: {partition_path}")

    try:
        telemetry_df = spark.read.parquet(partition_path)
    except Exception as e:
        print(f"⚠️ Could not read direct partition {partition_path}: {e}. Reading entire S3_PATH with basePath...")
        try:
            telemetry_df = spark.read.option("basePath", S3_PATH).parquet(S3_PATH).filter(col("event_date") == date_from)
        except Exception as e2:
            print(f"❌ Error reading Parquet: {e2}")
            return

    row_count = telemetry_df.count()
    print(f"📊 Telemetry DataFrame: {row_count} rows loaded for date {date_from}")

    if row_count == 0:
        print(f"⚠️ Partition for date {date_from} contains 0 records. Skipping job.")
        return

    # Load Trajets from Cassandra
    try:
        trajets_df = spark.read \
            .format("org.apache.spark.sql.cassandra") \
            .options(table="trajets", keyspace=CASSANDRA_KEYSPACE) \
            .load()
    except Exception as e:
        print(f"⚠️ Error reading Trajets: {e}")
        # Create empty fallback to avoid crash
        trajets_df = spark.createDataFrame([], "start_city STRING, end_city STRING, distance_km DOUBLE")

    # Process
    route_df = compute_route_efficiency(telemetry_df, trajets_df, date_from)

    # Save to Cassandra
    print(f"💾 Committing route intelligence to: {CASSANDRA_KEYSPACE}.batch_route_efficiency")

    route_df.write \
        .format("org.apache.spark.sql.cassandra") \
        .mode("append") \
        .options(table="batch_route_efficiency", keyspace=CASSANDRA_KEYSPACE) \
        .save()

    print("✅ Route Efficiency Job Completed Successfully")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(1)

    spark = SparkSession.builder \
        .appName("RouteEfficiencyBatch") \
        .getOrCreate()

    run_job(spark, sys.argv[1], sys.argv[2])
    spark.stop()
