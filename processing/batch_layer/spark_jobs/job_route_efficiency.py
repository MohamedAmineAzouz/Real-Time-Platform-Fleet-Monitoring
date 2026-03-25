"""
spark_jobs/job_route_efficiency.py
─────────────────────────────────────────────────────────────────────────────
Batch Job 4 — Route Efficiency Analysis

FIX: Uses fuel_consumed_trip (simulator-computed) for accurate fuel metrics.
─────────────────────────────────────────────────────────────────────────────
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.functions import (
    col, sum as _sum, avg, max as _max, min as _min,
    count, round as _round, when, lit, to_date, first,
)
from pyspark.sql.window import Window

from batch_config.batch_config import PARQUET_BASE, print_config
from batch_config.spark_config import get_spark_conf
from writers.sink_writer import write

SIMULATOR_INTERVAL_SECONDS = 1


def build_spark() -> SparkSession:
    builder = SparkSession.builder.appName("FleetBatch_RouteEfficiency")
    for k, v in get_spark_conf().items():
        builder = builder.config(k, v)
    return builder.getOrCreate()


def compute_route_efficiency(df: DataFrame, run_date: str) -> DataFrame:

    # Only driving events — cleaner route stats without refuel stops
    driving = df.filter(
    (col("refueling") == False) &
    (col("start_city").isNotNull()) &
    (col("end_city").isNotNull()) &
    (col("start_city") != col("end_city"))
)

    per_trip = (
        driving
        .groupBy("truck_id", "driver_id", "start_city", "end_city")
        .agg(
            _round(_sum("distance_km"),          2).alias("trip_distance_km"),
            # FIX: use max(fuel_consumed_trip) — it's a running total per trip
            _round(_max("fuel_consumed_trip"),   2).alias("trip_fuel_pct"),
            _round(avg("speed"),                 2).alias("avg_speed"),
            count("*")                             .alias("event_count"),
            _round(
                when(_sum("distance_km") > 0,
                    _max("fuel_consumed_trip") / _sum("distance_km") * 100
                ).otherwise(lit(0.0)), 2
            ).alias("fuel_per_100km"),
            _sum(when(col("is_alert") == True, 1).otherwise(0)).alias("alerts_on_trip"),
        )
        .withColumn(
            "estimated_duration_min",
            _round(col("event_count") * lit(SIMULATOR_INTERVAL_SECONDS) / 60.0, 1)
        )
    )

    per_route = (
        per_trip
        .groupBy("start_city", "end_city")
        .agg(
            count("*")                               .alias("total_trips"),
            _round(avg("trip_distance_km"),    2)   .alias("avg_distance_km"),
            _round(avg("trip_fuel_pct"),       2)   .alias("avg_fuel_l"),
            _round(avg("fuel_per_100km"),      2)   .alias("avg_fuel_per_100km"),
            _round(avg("avg_speed"),           2)   .alias("avg_speed_kmh"),
            _round(avg("estimated_duration_min"), 1).alias("avg_duration_min"),
            _round(avg("alerts_on_trip"),      2)   .alias("avg_alerts_per_trip"),
        )
    )

    best_on_route = (
        per_trip
        .groupBy("start_city", "end_city")
        .agg(
            first("truck_id")      .alias("most_efficient_truck"),
            first("driver_id")     .alias("most_efficient_driver"),
            _min("fuel_per_100km") .alias("best_fuel_per_100km"),
        )
    )

    return (
        per_route
        .join(best_on_route, on=["start_city", "end_city"], how="left")
        .withColumn("stat_date", lit(run_date))
    )


def run(date_from: str, date_to: str, run_date: str):
    spark = build_spark()
    spark.sparkContext.setLogLevel("WARN")

    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  Batch Job — Route Efficiency")
    print(f"  Period : {date_from} → {date_to}")
    print_config()
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

    raw = (
        spark.read.parquet(PARQUET_BASE)
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