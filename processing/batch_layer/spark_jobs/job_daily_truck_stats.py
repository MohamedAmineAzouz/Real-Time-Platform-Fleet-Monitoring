"""
spark_jobs/job_daily_truck_stats.py
─────────────────────────────────────────────────────────────────────────────
Batch Job 1 — Daily Truck Statistics
─────────────────────────────────────────────────────────────────────────────
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.functions import (
    col, sum as _sum, avg, max as _max, count,
    round as _round, to_date, lit, when, max as _max_ts,
)

from batch_config.batch_config import PARQUET_BASE, print_config
from batch_config.spark_config import get_spark_conf
from writers.sink_writer import write


def build_spark() -> SparkSession:
    builder = SparkSession.builder.appName("FleetBatch_DailyTruckStats")
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
    FIX: Use fuel_consumed_trip (simulator-computed) instead of lag()-based
    fuel_used. fuel_consumed_trip is exact, always positive, and correctly
    excludes refueling events by design in the simulator.

    For total daily fuel: take the MAX fuel_consumed_trip per truck
    (it's a running total that resets after each refuel, so the max
    across the day = the last trip's cumulative value, which is correct
    when the truck hasn't refueled yet, or sum across refuel boundaries).

    Better approach: sum fuel_consumed_trip only from refueling=True events
    (which carry the completed trip total) PLUS the current in-progress trip.
    """

    # ── Completed trips: fuel_consumed_trip on the refueling event ─────────────
    # When a truck finishes a trip and starts refueling, the refueling=True events
    # carry the accumulated fuel_consumed_trip for that completed trip.
    # Take the MAX per truck per trip (last refuel tick has the final total).
    completed = (
        df
        .filter(col("refueling") == True)
        .groupBy("truck_id")
        .agg(
            _round(_sum("fuel_consumed_trip"), 2).alias("_completed_fuel"),
        )
    )

    # ── In-progress trip: latest fuel_consumed_trip from driving events ─────────
    in_progress = (
        df
        .filter(col("refueling") == False)
        .groupBy("truck_id")
        .agg(
            _round(_max_ts("fuel_consumed_trip"), 2).alias("_inprogress_fuel"),
        )
    )

    # ── Main aggregation ────────────────────────────────────────────────────────
    driving = df.filter(col("refueling") == False)

    main = (
        driving
        .groupBy("truck_id")
        .agg(
            _round(_sum("distance_km"),  2).alias("total_distance_km"),
            _round(avg("speed"),         2).alias("avg_speed_kmh"),
            _round(_max_ts("speed"),     2).alias("max_speed_kmh"),
            _sum(when(col("is_alert") == True,           1).otherwise(0)).alias("total_alerts"),
            _sum(when(col("alert_type") == "OVERSPEED",  1).otherwise(0)).alias("overspeed_count"),
            _sum(when(col("alert_type") == "OVERHEAT",   1).otherwise(0)).alias("overheat_count"),
            _sum(when(col("alert_type") == "FUEL_THEFT", 1).otherwise(0)).alias("fuel_theft_count"),
            _sum(when(col("alert_type") == "LOW_FUEL",   1).otherwise(0)).alias("low_fuel_count"),
            count("*").alias("event_count"),
        )
    )

    # ── Join and compute final fuel metrics ─────────────────────────────────────
    result = (
        main
        .join(completed,   on="truck_id", how="left")
        .join(in_progress, on="truck_id", how="left")
        .fillna({"_completed_fuel": 0.0, "_inprogress_fuel": 0.0})
        .withColumn(
            "total_fuel_consumed_l",
            _round(col("_completed_fuel") + col("_inprogress_fuel"), 2)
        )
        .withColumn(
            "fuel_per_100km",
            _round(
                when(col("total_distance_km") > 0,
                    col("total_fuel_consumed_l") / col("total_distance_km") * 100
                ).otherwise(lit(0.0)), 2
            )
        )
        .drop("_completed_fuel", "_inprogress_fuel")
        .withColumn("stat_date", lit(run_date))
    )

    return result


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