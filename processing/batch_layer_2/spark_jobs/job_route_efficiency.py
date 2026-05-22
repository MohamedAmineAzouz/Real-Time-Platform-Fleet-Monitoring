"""
spark_jobs/job_route_efficiency.py
─────────────────────────────────────────────────────────────────────────────
Route Efficiency Analysis: Aggregating performance by Start -> End city pairs.
─────────────────────────────────────────────────────────────────────────────
"""

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

def compute_route_efficiency(telemetry_df: DataFrame, run_date: str) -> DataFrame:
    """
    Groups telemetry by Start City, End City, Truck, and Driver to analyze granular route performance.
    """
    
    # ── Step 1: Calculate Time Deltas (similar to stats job) ────────────────
    # We now partition by truck, driver AND the specific route
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
            # Since we group by truck/driver/route, total_trips is usually 1 for a single day record
            # but we can count unique sessions if needed. For now, lit(1) is the standard daily contribution.
            lit(1).alias("total_trips"), 
            _round(_sum("distance_km"), 2).alias("total_distance_km"),
            _round(_sum("fuel_consumed_l"), 2).alias("total_fuel_consumed_l"),
            _round(_avg("speed"), 2).alias("avg_speed_kmh"),
            _round(_sum("duration_sec") / 3600.0, 2).alias("total_duration_h"),
            _sum(when(col("is_alert") == True, 1).otherwise(0)).alias("total_alerts")
        )
    )
    
    # ── Step 3: Derived Efficiency Metrics ────────────────────────────────
    final_df = (
        route_stats
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
        .drop("total_alerts") 
    )
    
    return final_df

def run_job(spark: SparkSession, date_from: str, date_to: str):
    print(f"🛣️ Starting Route Efficiency Job: {date_from}")
    
    try:
        telemetry_df = spark.read.parquet(S3_PATH)
        telemetry_df = telemetry_df.filter(
            (to_date(col("event_time")) >= date_from) &
            (to_date(col("event_time")) <= date_to)
        )
    except Exception as e:
        print(f"⚠️ Error reading Telemetry: {e}")
        return

    # Process
    route_df = compute_route_efficiency(telemetry_df, date_from)
    
    # Save to Cassandra
    print(f"💾 Saving route efficiency stats to: {CASSANDRA_KEYSPACE}.batch_route_efficiency")
    
    route_df.write \
        .format("org.apache.spark.sql.cassandra") \
        .mode("append") \
        .options(table="batch_route_efficiency", keyspace=CASSANDRA_KEYSPACE) \
        .save()
        
    print("✅ Route Efficiency Job Completed")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(1)
        
    spark = SparkSession.builder \
        .appName("RouteEfficiencyBatch") \
        .getOrCreate()
        
    run_job(spark, sys.argv[1], sys.argv[2])
    spark.stop()
