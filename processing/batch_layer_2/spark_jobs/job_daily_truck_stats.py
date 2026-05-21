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
    col, sum as _sum, max as _max, count,
    round as _round, to_date, lit, when, lag
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
    Simplified core logic for daily truck statistics.
    Sum deltas for distance and fuel, and calculate time metrics.
    """
    
    # Window to calculate time deltas between events
    # Including driver_id in partition to handle driver swaps on same truck
    w_truck = Window.partitionBy("truck_id", "driver_id").orderBy("event_time")
    
    # Calculate duration between events in seconds
    with_time_deltas = (
        telemetry_df
        .withColumn("prev_event_time", lag("event_time", 1).over(w_truck))
        .withColumn(
            "duration_sec",
            when(col("prev_event_time").isNotNull(),
                col("event_time").cast("long") - col("prev_event_time").cast("long")
            ).otherwise(lit(0))
        )
        # Cap duration at 10 minutes to avoid spikes from gaps in telemetry
        .withColumn("duration_sec", when(col("duration_sec") > 600, lit(600)).otherwise(col("duration_sec")))
    )
    
    # ── Step 1: Sum Deltas per Truck & Driver ─────────────────────────────
    per_truck_deltas = (
        with_time_deltas
        .groupBy("truck_id", "driver_id")
        .agg(
            _round(_sum("fuel_consumed_l"), 2).alias("total_fuel_consumed_l"),
            _round(_sum("distance_km"), 2).alias("total_distance_km"),
            
            # Time Metrics
            _round(_sum(when(col("speed") > 2.0, col("duration_sec")).otherwise(0)) / 3600.0, 2).alias("hours_driven"),
            _round(_sum(when(col("speed") <= 2.0, col("duration_sec")).otherwise(0)) / 3600.0, 2).alias("hours_stopped"),
            
            _round(_max("speed"), 2).alias("max_speed_kmh"),
            _sum(when(col("is_alert") == True, 1).otherwise(0)).alias("total_alerts"),
            _sum(when(col("alert_type") == "OVERSPEED", 1).otherwise(0)).alias("overspeed_count"),
            _sum(when(col("alert_type") == "OVERHEAT", 1).otherwise(0)).alias("overheat_count"),
            _sum(when(col("alert_type") == "FUEL_THEFT", 1).otherwise(0)).alias("fuel_theft_count"),
            _sum(when(col("alert_type") == "LOW_FUEL", 1).otherwise(0)).alias("low_fuel_count"),
            count("*").alias("event_count")
        )
    )
    
    # ── Step 2: Efficiency Calculation ────────────────────────────────────
    final_stats = (
        per_truck_deltas
        .withColumn(
            "avg_speed_kmh",
            _round(
                when(
                    col("hours_driven") > 0,
                    col("total_distance_km") / col("hours_driven")
                ).otherwise(lit(0.0)),
                2
            )
        )
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
