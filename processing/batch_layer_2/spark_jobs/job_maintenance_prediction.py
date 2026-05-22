"""
spark_jobs/job_maintenance_prediction.py
─────────────────────────────────────────────────────────────────────────────
Predictive Maintenance Job: Analyzing vehicle health and flagging maintenance needs.
─────────────────────────────────────────────────────────────────────────────
- Reads Parquet telemetry from Silver Lake (MinIO/S3)
- Calculates health metrics: Engine Temp, Odometer, Fuel consistency
- Identifies critical thresholds and flags
- Categorizes maintenance priority (HIGH/MEDIUM)
- Writes to `batch_maintenance_flags`
─────────────────────────────────────────────────────────────────────────────
"""

import os
import sys
from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.functions import (
    col, avg as _avg, max as _max, count,
    stddev as _stddev, to_date, lit, when, expr
)

# ── Configuration ─────────────────────────────────────────────────────────
CASSANDRA_KEYSPACE = os.getenv("CASSANDRA_KEYSPACE", "fleet")
LAKE_BUCKET = os.getenv("LAKE_BUCKET", "fleet-data")
LAKE_PREFIX = os.getenv("LAKE_PREFIX", "silver/truck_history")
S3_PATH = f"s3a://{LAKE_BUCKET}/{LAKE_PREFIX}"

def compute_maintenance_flags(telemetry_df: DataFrame, run_date: str) -> DataFrame:
    """
    Core analytics for predictive maintenance.
    Groups telemetry by truck and driver to identify health patterns.
    """
    
    # ── Step 1: Aggregate Health Metrics ──────────────────────────────────
    health_metrics = (
        telemetry_df
        .groupBy("truck_id", "driver_id")
        .agg(
            _avg("engine_temp").alias("avg_engine_temp"),
            _max("engine_temp").alias("max_engine_temp"),
            _max("odometer_km").alias("max_odometer_km"),
            _avg("fuel_level").alias("avg_fuel_rate"), 
            _stddev("fuel_level").alias("fuel_rate_stddev"),
            count(when(col("alert_type") == "OVERHEAT", 1)).alias("overheat_count"),
            count(when(col("alert_type") == "FUEL_THEFT", 1)).alias("theft_count"),
            count("*").alias("event_count")
        )
    )
    
    # ── Step 2: Apply Prediction Logic ────────────────────────────────────
    # 1. High Temp: Avg > 90
    # 2. Overheat Alert: count >= 5
    # 3. Odometer Milestone: Near 10k, 20k, etc (within 500km)
    # 4. Fuel Inconsistency: stddev > 1.5 (volatile consumption)
    
    flagged_df = (
        health_metrics
        .withColumn("flag_high_temp", col("avg_engine_temp") > 90.0)
        .withColumn("flag_overheat_alerts", col("overheat_count") >= 5)
        .withColumn("flag_odometer_milestone", (col("max_odometer_km") % 10000) >= 9500.0)
        .withColumn("flag_fuel_inconsistency", col("fuel_rate_stddev") > 2.0) # Using 2.0 as threshold
    )
    
    # ── Step 3: Maintenance Status & Priority ─────────────────────────────
    final_df = (
        flagged_df
        .withColumn(
            "maintenance_needed",
            col("flag_high_temp") | 
            col("flag_overheat_alerts") | 
            col("flag_odometer_milestone") | 
            col("flag_fuel_inconsistency")
        )
        .withColumn(
            "priority",
            when(col("flag_high_temp") | col("flag_overheat_alerts"), lit("HIGH"))
            .when(col("maintenance_needed"), lit("MEDIUM"))
            .otherwise(lit("NORMAL"))
        )
        # Filter for only trucks that actually need attention
        .filter(col("maintenance_needed") == True)
        .withColumn("stat_date", lit(run_date))
    )
    
    return final_df

def run_job(spark: SparkSession, date_from: str, date_to: str):
    print(f"🛠️ Starting Maintenance Prediction Job: {date_from}")
    
    try:
        telemetry_df = spark.read.parquet(S3_PATH)
        # Filter for the requested day
        telemetry_df = telemetry_df.filter(
            (to_date(col("event_time")) >= date_from) &
            (to_date(col("event_time")) <= date_to)
        )
    except Exception as e:
        print(f"⚠️ Error reading Telemetry: {e}")
        return

    # ── Process ──
    predictions_df = compute_maintenance_flags(telemetry_df, date_from)
    
    # ── Save ──
    print(f"💾 Committing maintenance flags to Cassandra: {CASSANDRA_KEYSPACE}.batch_maintenance_flags")
    
    predictions_df.write \
        .format("org.apache.spark.sql.cassandra") \
        .mode("append") \
        .options(table="batch_maintenance_flags", keyspace=CASSANDRA_KEYSPACE) \
        .save()
        
    print("✅ Maintenance Prediction Job Completed")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(1)
        
    spark = SparkSession.builder \
        .appName("MaintenancePredictionBatch") \
        .getOrCreate()
        
    run_job(spark, sys.argv[1], sys.argv[2])
    spark.stop()
