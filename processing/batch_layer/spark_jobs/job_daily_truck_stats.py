"""
spark_jobs/job_daily_truck_stats.py
─────────────────────────────────────────────────────────────────────────────
Batch Job 1 — Daily Truck Statistics

Reads raw Parquet events for a given date range and computes per-truck:
  - total distance driven (km)
  - total fuel consumed (L)
  - fuel efficiency (L/100km)
  - average and max speed
  - total alert count by type
  - active driving hours

Output table: batch_daily_truck_stats
─────────────────────────────────────────────────────────────────────────────
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.functions import (
    col, sum as _sum, avg, max as _max, count,
    countDistinct, round as _round,
    to_date, lit, when,
)

from batch_config.batch_config import PARQUET_BASE, print_config
from batch_config.spark_config import get_spark_conf, get_packages
from writers.sink_writer import write


# ─────────────────────────────────────────────────────────────────────────────
def build_spark(app_name: str = "FleetBatch_DailyTruckStats") -> SparkSession:
    builder = SparkSession.builder.appName(app_name)
    for k, v in get_spark_conf().items():
        builder = builder.config(k, v)
    return builder.getOrCreate()


# ─────────────────────────────────────────────────────────────────────────────
def read_parquet(spark: SparkSession, date_from: str, date_to: str) -> DataFrame:
    """
    Read raw Parquet for a date range.
    Parquet is partitioned by date so Spark only reads relevant files.
    """
    return (
        spark.read
        .parquet(PARQUET_BASE)
        .filter(
            (to_date(col("event_time")) >= date_from) &
            (to_date(col("event_time")) <= date_to)
        )
    )


# ─────────────────────────────────────────────────────────────────────────────
def compute_daily_truck_stats(df: DataFrame, run_date: str) -> DataFrame:
    """
    Aggregate raw events → one row per (truck_id, run_date).
    """
    return (
        df
        .groupBy("truck_id")
        .agg(
            # Distance
            _round(_sum("distance_km"),           2).alias("total_distance_km"),

            # Fuel
            _round(_sum("fuel_used"),             2).alias("total_fuel_consumed_l"),

            # Efficiency: L per 100km — null-safe
            _round(
                (_sum("fuel_used") / _sum("distance_km")) * 100, 2
            ).alias("fuel_per_100km"),

            # Speed
            _round(avg("speed"),                  2).alias("avg_speed_kmh"),
            _round(_max("speed"),                 2).alias("max_speed_kmh"),

            # Alerts
            _sum(when(col("is_alert") == True, 1).otherwise(0))
                                                   .alias("total_alerts"),
            _sum(when(col("alert_type") == "OVERSPEED", 1).otherwise(0))
                                                   .alias("overspeed_count"),
            _sum(when(col("alert_type") == "OVERHEAT",  1).otherwise(0))
                                                   .alias("overheat_count"),
            _sum(when(col("alert_type") == "FUEL_THEFT",1).otherwise(0))
                                                   .alias("fuel_theft_count"),
            _sum(when(col("alert_type") == "LOW_FUEL",  1).otherwise(0))
                                                   .alias("low_fuel_count"),

            # Activity
            count("*")                             .alias("event_count"),
        )
        # Add the run date as partition column
        .withColumn("stat_date", lit(run_date))
        # Replace null efficiency (truck didn't move) with 0
        .fillna({"fuel_per_100km": 0.0})
    )


# ─────────────────────────────────────────────────────────────────────────────
def run(date_from: str, date_to: str, run_date: str):
    spark = build_spark()
    spark.sparkContext.setLogLevel("WARN")

    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  Batch Job — Daily Truck Stats")
    print(f"  Period : {date_from} → {date_to}")
    print_config()
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

    raw = read_parquet(spark, date_from, date_to)
    stats = compute_daily_truck_stats(raw, run_date)

    print(f"  Writing {stats.count()} rows → daily_truck_stats")
    write(stats, "daily_truck_stats", mode="overwrite")
    print("  ✅ Done")

    spark.stop()


if __name__ == "__main__":
    import argparse
    from datetime import date, timedelta

    parser = argparse.ArgumentParser()
    parser.add_argument("--date-from", default=str(date.today() - timedelta(days=1)))
    parser.add_argument("--date-to",   default=str(date.today() - timedelta(days=1)))
    parser.add_argument("--run-date",  default=str(date.today()))
    args = parser.parse_args()

    run(args.date_from, args.date_to, args.run_date)