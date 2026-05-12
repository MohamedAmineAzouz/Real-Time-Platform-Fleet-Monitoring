"""
spark_jobs/job_daily_truck_stats.py
─────────────────────────────────────────────────────────────────────────────
Batch Job: Daily Truck Statistics (Silver Lake -> Cassandra)
─────────────────────────────────────────────────────────────────────────────
- Reads Parquet telemetry from MinIO/S3 (Silver Lake)
- Enriches with Truck Registry from Cassandra (Fuel Capacity)
- Calculates fuel consumption in Liters (percentage * capacity)
- Aggregates daily metrics: distance, fuel, speed, and alerts
- Writes to `batch_daily_truck_stats`
─────────────────────────────────────────────────────────────────────────────
"""

import os
import sys
from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.functions import (
    col, sum as _sum, avg, max as _max, count,
    round as _round, to_date, lit, when,
    lag, coalesce
)
from pyspark.sql.window import Window

# ── Configuration ─────────────────────────────────────────────────────────
CASSANDRA_KEYSPACE = os.getenv("CASSANDRA_KEYSPACE", "fleet")
LAKE_BUCKET = os.getenv("LAKE_BUCKET", "fleet-data")
LAKE_PREFIX = os.getenv("LAKE_PREFIX", "silver/truck_history")

# Default S3 Path for MinIO
S3_PATH = f"s3a://{LAKE_BUCKET}/{LAKE_PREFIX}"


def compute_daily_stats(telemetry_df: DataFrame, trucks_df: DataFrame, run_date: str) -> DataFrame:
    """
    Core logic for daily truck statistics.
    1. Segment driving events by refueling cycles.
    2. Convert fuel percentage to liters using truck capacity.
    3. Aggregate all metrics per truck per day.
    """
    
    # ── Join with Truck Registry ──────────────────────────────────────────
    # We need fuel_capacity to convert % to L
    df = telemetry_df.join(trucks_df.select("truck_id", "fuel_capacity"), "truck_id", "left")
    
    # ── Step 1: Identify trip segments ────────────────────────────────────
    # A new segment starts when refueling transitions from True to False
    w_truck = Window.partitionBy("truck_id").orderBy("event_time")
    
    segmented = (
        df
        .withColumn("prev_refueling", lag("refueling", 1, False).over(w_truck))
        .withColumn(
            "segment_start",
            when(
                (col("prev_refueling") == True) & (col("refueling") == False),
                lit(1)
            ).otherwise(lit(0))
        )
        .withColumn(
            "trip_segment",
            _sum("segment_start").over(w_truck.rowsBetween(Window.unboundedPreceding, 0))
        )
    )
    
    # ── Step 2: Calculate Fuel Consumed in Liters ──────────────────────────
    # fuel_consumed_trip is a running percentage (%) since last refuel.
    # total_fuel_l = (max(fuel_consumed_trip) / 100) * fuel_capacity
    
    driving = segmented.filter(col("refueling") == False)
    
    per_segment = (
        driving
        .groupBy("truck_id", "trip_segment", "fuel_capacity")
        .agg(
            _max("fuel_consumed_trip").alias("segment_fuel_pct"),
            _sum("distance_km").alias("segment_distance_km"),
        )
        .withColumn(
            "segment_fuel_l",
            (col("segment_fuel_pct") / 100.0) * coalesce(col("fuel_capacity"), lit(400.0))
        )
    )
    
    # ── Step 3: Aggregate Segments per Truck ──────────────────────────────
    per_truck_fuel = (
        per_segment
        .groupBy("truck_id")
        .agg(
            _round(_sum("segment_fuel_l"), 2).alias("total_fuel_consumed_l"),
            _round(_sum("segment_distance_km"), 2).alias("total_distance_km"),
        )
    )
    
    # ── Step 4: Other Metrics (Speed, Alerts, Events) ─────────────────────
    per_truck_metrics = (
        driving
        .groupBy("truck_id")
        .agg(
            _round(avg("speed"), 2).alias("avg_speed_kmh"),
            _round(_max("speed"), 2).alias("max_speed_kmh"),
            _sum(when(col("is_alert") == True, 1).otherwise(0)).alias("total_alerts"),
            _sum(when(col("alert_type") == "OVERSPEED", 1).otherwise(0)).alias("overspeed_count"),
            _sum(when(col("alert_type") == "OVERHEAT", 1).otherwise(0)).alias("overheat_count"),
            _sum(when(col("alert_type") == "FUEL_THEFT", 1).otherwise(0)).alias("fuel_theft_count"),
            _sum(when(col("alert_type") == "LOW_FUEL", 1).otherwise(0)).alias("low_fuel_count"),
            count("*").alias("event_count"),
        )
    )
    
    # ── Step 5: Final Join and Efficiency Calculation ──────────────────────
    final_stats = (
        per_truck_fuel
        .join(per_truck_metrics, on="truck_id", how="left")
        .withColumn(
            "fuel_per_100km",
            _round(
                when(col("total_distance_km") > 0,
                    (col("total_fuel_consumed_l") / col("total_distance_km")) * 100.0
                ).otherwise(lit(0.0)), 4
            )
        )
        .withColumn("stat_date", lit(run_date))
        .fillna(0.0)
    )
    
    return final_stats


def run_job(spark: SparkSession, date_from: str, date_to: str):
    print(f"🚀 Starting Daily Truck Stats Job: {date_from} → {date_to}")
    
    # ── 1. Load Data ──────────────────────────────────────────────────────
    # Load Telemetry from Parquet (S3/MinIO)
    try:
        telemetry_df = spark.read.parquet(S3_PATH)
        # Filter for the requested period
        telemetry_df = telemetry_df.filter(
            (to_date(col("event_time")) >= date_from) &
            (to_date(col("event_time")) <= date_to)
        )
    except Exception as e:
        print(f"⚠️ Error reading Parquet from {S3_PATH}: {e}")
        return

    if telemetry_df.count() == 0:
        print(f"⚠️ No telemetry data found for period {date_from} to {date_to}")
        return
        
    # Load Truck Registry from Cassandra
    trucks_df = spark.read \
        .format("org.apache.spark.sql.cassandra") \
        .options(table="trucks", keyspace=CASSANDRA_KEYSPACE) \
        .load()
        
    # ── 2. Process ────────────────────────────────────────────────────────
    # Use the date_from as the stat_date for the batch record
    stats_df = compute_daily_stats(telemetry_df, trucks_df, date_from)
    
    # ── 3. Save ───────────────────────────────────────────────────────────
    print(f"💾 Writing {stats_df.count()} records to Cassandra: batch_daily_truck_stats")
    
    stats_df.write \
        .format("org.apache.spark.sql.cassandra") \
        .mode("append") \
        .options(table="batch_daily_truck_stats", keyspace=CASSANDRA_KEYSPACE) \
        .save()
        
    print("✅ Daily Truck Stats Job Completed Successfully")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: spark-submit job_daily_truck_stats.py <date_from> <date_to>")
        sys.exit(1)
        
    spark = SparkSession.builder \
        .appName("DailyTruckStatsBatch") \
        .getOrCreate()
        
    run_job(spark, sys.argv[1], sys.argv[2])
    spark.stop()
