"""
spark_jobs/job_driver_performance.py
─────────────────────────────────────────────────────────────────────────────
Batch Job 2 — Driver Performance Scoring

FIX: Uses fuel_consumed_trip (simulator-computed) instead of lag()-based
fuel_used to avoid negative values from refueling events.
─────────────────────────────────────────────────────────────────────────────
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.functions import (
    col, sum as _sum, avg, max as _max, count,
    round as _round, when, lit, to_date,
)
from pyspark.sql.window import Window

from batch_config.batch_config import PARQUET_BASE, print_config
from batch_config.spark_config import get_spark_conf
from writers.sink_writer import write

SPEED_LIMIT = 120.0


def build_spark() -> SparkSession:
    builder = SparkSession.builder.appName("FleetBatch_DriverPerformance")
    for k, v in get_spark_conf().items():
        builder = builder.config(k, v)
    return builder.getOrCreate()


def compute_driver_performance(df: DataFrame, run_date: str) -> DataFrame:

    # Use only driving events for speed/distance/alert metrics
    driving = df.filter(col("refueling") == False)

    per_driver = (
        driving
        .groupBy("driver_id")
        .agg(
            count("*")                                          .alias("total_events"),
            _round(_sum("distance_km"),  2)                    .alias("total_distance_km"),
            _round(_max("fuel_consumed_trip"), 2)              .alias("total_fuel_l"),
            _round(avg("speed"),         2)                    .alias("avg_speed"),
            _round(_max("speed"),        2)                    .alias("max_speed"),

            _round(
                _sum(when(col("speed") <= SPEED_LIMIT, 1).otherwise(0)) /
                count("*"), 4
            ).alias("speed_compliance_rate"),

            _round(
                _sum(when(col("is_alert") == True, 1).otherwise(0)) /
                count("*") * 100, 2
            ).alias("alert_rate_per_100"),

            # FIX: use fuel_consumed_trip (always positive, excludes refuels)
            _round(
                when(_sum("distance_km") > 0,
                    (_max("fuel_consumed_trip") / _sum("distance_km")) * 100
                ).otherwise(lit(0.0)), 2
            ).alias("fuel_per_100km"),

            _sum(when(col("alert_type") == "FUEL_THEFT", 1).otherwise(0))
                                                             .alias("theft_events"),
        )
        .fillna({"fuel_per_100km": 0.0, "total_fuel_l": 0.0})
    )

    # Fleet averages for relative scoring
    fleet_avg = per_driver.agg(
        avg("fuel_per_100km")    .alias("fleet_avg_fuel"),
        avg("alert_rate_per_100").alias("fleet_avg_alert_rate"),
        avg("total_distance_km") .alias("fleet_avg_distance"),
    ).collect()[0]

    fleet_avg_fuel     = fleet_avg["fleet_avg_fuel"]      or 1.0
    fleet_avg_alerts   = fleet_avg["fleet_avg_alert_rate"] or 1.0
    fleet_avg_distance = fleet_avg["fleet_avg_distance"]   or 1.0

    def _clamp(c, lo=0, hi=100):
        return when(c > hi, hi).when(c < lo, lo).otherwise(c)

    scored = (
        per_driver
        .withColumn("speed_score",
            _round(_clamp(col("speed_compliance_rate") * 100), 2))
        .withColumn("fuel_score",
            _round(_clamp(
                when(col("fuel_per_100km") > 0,
                    lit(fleet_avg_fuel) / col("fuel_per_100km") * 100
                ).otherwise(lit(100.0))
            ), 2))
        .withColumn("alert_score",
            _round(_clamp(
                when(col("alert_rate_per_100") > 0,
                    (lit(1.0) - col("alert_rate_per_100") / lit(fleet_avg_alerts)) * 100
                ).otherwise(lit(100.0))
            ), 2))
        .withColumn("distance_score",
            _round(_clamp(
                col("total_distance_km") / lit(fleet_avg_distance) * 100
            ), 2))
        .withColumn("performance_score",
            _round(
                col("speed_score")    * 0.30 +
                col("fuel_score")     * 0.30 +
                col("alert_score")    * 0.25 +
                col("distance_score") * 0.15,
                2
            ))
        .withColumn("stat_date", lit(run_date))
    )

    rank_w = Window.orderBy(col("performance_score").desc())
    return scored.withColumn(
        "fleet_rank",
        count("driver_id").over(rank_w).cast("int")
    )


def run(date_from: str, date_to: str, run_date: str):
    spark = build_spark()
    spark.sparkContext.setLogLevel("WARN")

    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  Batch Job — Driver Performance")
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

    result = compute_driver_performance(raw, run_date)
    print(f"  Writing {result.count()} rows → driver_performance")
    write(result, "driver_performance", mode="overwrite")
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