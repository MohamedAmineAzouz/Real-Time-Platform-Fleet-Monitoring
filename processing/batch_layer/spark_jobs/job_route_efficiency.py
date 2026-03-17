"""
spark_jobs/job_route_efficiency.py
─────────────────────────────────────────────────────────────────────────────
Batch Job 4 — Route Efficiency Analysis

For each (start_city → end_city) route:
  - Average distance driven
  - Average fuel consumed
  - Average duration (estimated from event count × simulator interval)
  - Fleet efficiency score for the route
  - Best-performing truck/driver on each route

Output table: batch_route_efficiency
─────────────────────────────────────────────────────────────────────────────
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.functions import (
    col, sum as _sum, avg, max as _max, min as _min,
    count, round as _round, when, lit, to_date,
    first,
)
from pyspark.sql.window import Window

from config.batch_config import PARQUET_BASE, print_config
from config.spark_config import get_spark_conf
from writers.sink_writer import write

# Simulator sends one event per truck per second — used to estimate duration
SIMULATOR_INTERVAL_SECONDS = 1


# ─────────────────────────────────────────────────────────────────────────────
def build_spark() -> SparkSession:
    builder = SparkSession.builder.appName("FleetBatch_RouteEfficiency")
    for k, v in get_spark_conf().items():
        builder = builder.config(k, v)
    return builder.getOrCreate()


# ─────────────────────────────────────────────────────────────────────────────
def compute_route_efficiency(df: DataFrame, run_date: str) -> DataFrame:
    """
    Per-route aggregation: (start_city, end_city, truck_id) → metrics.
    """
    # ── Per trip (truck × route) ──────────────────────────────────────────────
    per_trip = (
        df
        .filter(
            col("start_city").isNotNull() &
            col("end_city").isNotNull() &
            (col("start_city") != col("end_city"))
        )
        .groupBy("truck_id", "driver_id", "start_city", "end_city")
        .agg(
            _round(_sum("distance_km"),  2).alias("trip_distance_km"),
            _round(_sum("fuel_used"),    2).alias("trip_fuel_l"),
            _round(avg("speed"),         2).alias("avg_speed"),
            count("*")                    .alias("event_count"),
            _round(
                (_sum("fuel_used") / _sum("distance_km")) * 100, 2
            ).alias("fuel_per_100km"),
            _sum(when(col("is_alert") == True, 1).otherwise(0))
                                          .alias("alerts_on_trip"),
        )
        .fillna({"fuel_per_100km": 0.0})
        # Estimated trip duration in minutes
        .withColumn(
            "estimated_duration_min",
            _round(col("event_count") * lit(SIMULATOR_INTERVAL_SECONDS) / 60.0, 1)
        )
    )

    # ── Per route (start_city → end_city) fleet summary ───────────────────────
    per_route = (
        per_trip
        .groupBy("start_city", "end_city")
        .agg(
            count("*")                              .alias("total_trips"),
            _round(avg("trip_distance_km"),   2)   .alias("avg_distance_km"),
            _round(avg("trip_fuel_l"),        2)   .alias("avg_fuel_l"),
            _round(avg("fuel_per_100km"),     2)   .alias("avg_fuel_per_100km"),
            _round(avg("avg_speed"),          2)   .alias("avg_speed_kmh"),
            _round(avg("estimated_duration_min"), 1).alias("avg_duration_min"),
            _round(avg("alerts_on_trip"),     2)   .alias("avg_alerts_per_trip"),
        )
    )

    # ── Best truck/driver per route ───────────────────────────────────────────
    # Best = lowest fuel_per_100km
    best_w = Window.partitionBy("start_city", "end_city").orderBy("fuel_per_100km")
    best_on_route = (
        per_trip
        .withColumn("_rank", col("fuel_per_100km"))
        .withColumn(
            "_rn",
            col("_rank")
        )
        # Take the most efficient trip per route
        .groupBy("start_city", "end_city")
        .agg(
            first("truck_id")         .alias("most_efficient_truck"),
            first("driver_id")        .alias("most_efficient_driver"),
            _min("fuel_per_100km")    .alias("best_fuel_per_100km"),
        )
    )

    return (
        per_route
        .join(best_on_route, on=["start_city", "end_city"], how="left")
        .withColumn("stat_date", lit(run_date))
    )


# ─────────────────────────────────────────────────────────────────────────────
def run(date_from: str, date_to: str, run_date: str):
    spark = build_spark()
    spark.sparkContext.setLogLevel("WARN")

    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  Batch Job — Route Efficiency")
    print(f"  Period : {date_from} → {date_to}")
    print_config()
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

    raw = (
        spark.read
        .parquet(PARQUET_BASE)
        .filter(
            (to_date(col("event_time")) >= date_from) &
            (to_date(col("event_time")) <= date_to)
        )
    )

    result = compute_route_efficiency(raw, run_date)

    print(f"  Writing {result.count()} routes → route_efficiency")
    write(result, "route_efficiency", mode="overwrite")
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