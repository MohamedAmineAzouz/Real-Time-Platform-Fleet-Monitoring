"""
spark_jobs/job_daily_truck_stats.py
─────────────────────────────────────────────────────────────────────────────
Batch Job 1 — Daily Truck Statistics

fuel_consumed_trip is a RUNNING TOTAL that resets on each refuel.
Correct aggregation strategy:

  Per truck per day:
    total_distance_km      = SUM(distance_km)   where refueling=False
    total_fuel_consumed_l = SUM of completed trip totals
                             + current in-progress trip value
                           = MAX(fuel_consumed_trip) per trip segment

  A "trip segment" = events between two refuels.
  fuel_consumed_trip resets to 0 after each refuel, so within a segment
  it's monotonically increasing. MAX per segment = fuel used that segment.

  fuel_per_100km = total_fuel_consumed_l / total_distance_km * 100
                   should be ~5–20 %/km for this simulator
─────────────────────────────────────────────────────────────────────────────
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.functions import (
    col, sum as _sum, avg, max as _max, count,
    round as _round, to_date, lit, when,
    row_number, lag,
)
from pyspark.sql.window import Window

from batch_config.batch_config import PARQUET_BASE, print_config
from batch_config.spark_config import get_spark_conf
from writers.sink_writer import write


def build_spark(app_name: str = "FleetBatch_DailyTruckStats") -> SparkSession:
    builder = SparkSession.builder.appName(app_name)
    for k, v in get_spark_conf().items():
        builder = builder.config(k, v)
    return builder.getOrCreate()


def read_parquet(spark: SparkSession, date_from: str, date_to: str) -> DataFrame:
    try:
        df = spark.read.parquet(PARQUET_BASE)
        filtered = df.filter(
            (to_date(col("event_time")) >= date_from) &
            (to_date(col("event_time")) <= date_to)
        )
        if filtered.limit(1).count() == 0:
            print(f"  ⚠️  No data in {PARQUET_BASE} for {date_from} → {date_to}")
            return None
        return filtered
    except Exception as e:
        print(f"  ⚠️  Could not read Parquet: {e}")
        return None


def compute_daily_truck_stats(df: DataFrame, run_date: str) -> DataFrame:
    """
    fuel_consumed_trip is a monotonically increasing running total within
    each trip segment (resets to 0 after refuel).

    Strategy:
      1. Assign a trip segment ID per truck: increments each time refueling
         transitions from True→False (i.e. refuel finished, new trip starts).
      2. Take MAX(fuel_consumed_trip) per (truck, segment) = fuel for that segment.
      3. Sum segment maxes = total fuel consumed across all segments today.
    """

    # ── Step 1: identify trip segments ────────────────────────────────────────
    # A new segment starts when refueling flips True→False
    w_truck = Window.partitionBy("truck_id").orderBy("event_time")

    segmented = (
        df
        .withColumn("prev_refueling", lag("refueling", 1, False).over(w_truck))
        # segment_start = True when truck just finished refueling (prev=True, now=False)
        .withColumn(
            "segment_start",
            when(
                (col("prev_refueling") == True) & (col("refueling") == False),
                lit(1)
            ).otherwise(lit(0))
        )
        # cumulative sum of segment_starts = trip segment ID per truck
        .withColumn(
            "trip_segment",
            _sum("segment_start").over(w_truck.rowsBetween(Window.unboundedPreceding, 0))
        )
        .drop("prev_refueling", "segment_start")
    )

    # ── Step 2: max fuel per (truck, segment) — only from driving events ───────
    driving = segmented.filter(col("refueling") == False)

    per_segment = (
        driving
        .groupBy("truck_id", "trip_segment")
        .agg(
            _max("fuel_consumed_trip").alias("segment_fuel_pct"),
            _sum("distance_km").alias("segment_distance_km"),
        )
        # Exclude segments with no meaningful data (first event before any driving)
        .filter(col("segment_fuel_pct") > 0)
    )

    # ── Step 3: sum segments per truck ─────────────────────────────────────────
    per_truck_fuel = (
        per_segment
        .groupBy("truck_id")
        .agg(
            _round(_sum("segment_fuel_pct"),    2).alias("total_fuel_consumed_l"),
            _round(_sum("segment_distance_km"), 2).alias("total_distance_km"),
        )
    )

    # ── Step 4: remaining metrics from driving events ──────────────────────────
    per_truck_metrics = (
        driving
        .groupBy("truck_id")
        .agg(
            _round(avg("speed"),         2).alias("avg_speed_kmh"),
            _round(_max("speed"),        2).alias("max_speed_kmh"),
            _sum(when(col("is_alert") == True,           1).otherwise(0)).alias("total_alerts"),
            _sum(when(col("alert_type") == "OVERSPEED",  1).otherwise(0)).alias("overspeed_count"),
            _sum(when(col("alert_type") == "OVERHEAT",   1).otherwise(0)).alias("overheat_count"),
            _sum(when(col("alert_type") == "FUEL_THEFT", 1).otherwise(0)).alias("fuel_theft_count"),
            _sum(when(col("alert_type") == "LOW_FUEL",   1).otherwise(0)).alias("low_fuel_count"),
            count("*").alias("event_count"),
        )
    )

    # ── Step 5: join and compute efficiency ────────────────────────────────────
    return (
        per_truck_fuel
        .join(per_truck_metrics, on="truck_id", how="left")
        .withColumn(
            "fuel_per_100km",
            _round(
                when(col("total_distance_km") > 0,
                    col("total_fuel_consumed_l") / col("total_distance_km") * 100
                ).otherwise(lit(0.0)), 4
            )
        )
        .withColumn("stat_date", lit(run_date))
        .fillna(0.0)
    )


def run(date_from: str, date_to: str, run_date: str):
    spark = build_spark()
    spark.sparkContext.setLogLevel("WARN")

    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  Batch Job — Daily Truck Stats")
    print(f"  Period : {date_from} → {date_to}")
    print_config()
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

    raw = read_parquet(spark, date_from, date_to)
    if raw is None:
        print("  ⏭  No data — exiting cleanly")
        spark.stop()
        return

    stats = compute_daily_truck_stats(raw, run_date)

    # Debug: show a sample before writing
    print("  Sample output:")
    stats.select(
        "truck_id", "total_distance_km", "total_fuel_consumed_l", "fuel_per_100km"
    ).show(5, truncate=False)

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