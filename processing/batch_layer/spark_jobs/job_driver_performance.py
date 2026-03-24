"""
spark_jobs/job_driver_performance.py
─────────────────────────────────────────────────────────────────────────────
Batch Job 2 — Driver Performance Scoring

Computes per-driver metrics and a composite performance score (0–100).

Score formula:
  - Speed compliance  (30%) — % of trips under speed limit
  - Fuel efficiency   (30%) — compared to fleet average
  - Alert rate        (25%) — alerts per 100 events
  - Distance coverage (15%) — normalized total km driven

Output table: batch_driver_performance
─────────────────────────────────────────────────────────────────────────────
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.functions import (
    col, sum as _sum, avg, max as _max, count,
    round as _round, when, lit, to_date,
    min as _min,
)
from pyspark.sql.window import Window

from batch_config.batch_config import PARQUET_BASE, print_config
from batch_config.spark_config import get_spark_conf
from writers.sink_writer import write


SPEED_LIMIT = 120.0


# ─────────────────────────────────────────────────────────────────────────────
def build_spark() -> SparkSession:
    builder = SparkSession.builder.appName("FleetBatch_DriverPerformance")
    for k, v in get_spark_conf().items():
        builder = builder.config(k, v)
    return builder.getOrCreate()


# ─────────────────────────────────────────────────────────────────────────────
def compute_driver_performance(df: DataFrame, run_date: str) -> DataFrame:
    """
    Per-driver aggregation + composite score.
    """
    # ── Step 1: raw per-driver aggregates ─────────────────────────────────────
    per_driver = (
        df
        .groupBy("driver_id")
        .agg(
            count("*")                                         .alias("total_events"),
            _round(_sum("distance_km"), 2)                     .alias("total_distance_km"),
            _round(_sum("fuel_used"),   2)                     .alias("total_fuel_l"),
            _round(avg("speed"),        2)                     .alias("avg_speed"),
            _round(_max("speed"),       2)                     .alias("max_speed"),

            # Speed compliance: fraction of events under limit
            _round(
                _sum(when(col("speed") <= SPEED_LIMIT, 1).otherwise(0)) /
                count("*"), 4
            ).alias("speed_compliance_rate"),

            # Alert rate: alerts per 100 events
            _round(
                _sum(when(col("is_alert") == True, 1).otherwise(0)) /
                count("*") * 100, 2
            ).alias("alert_rate_per_100"),

            # Fuel efficiency L/100km
            _round(
                (_sum("fuel_used") / _sum("distance_km")) * 100, 2
            ).alias("fuel_per_100km"),

            # Trucks driven
            _sum(when(col("alert_type") == "FUEL_THEFT", 1).otherwise(0))
                                                             .alias("theft_events"),
        )
        .fillna({"fuel_per_100km": 0.0})
    )

    # ── Step 2: fleet-wide averages for relative scoring ──────────────────────
    fleet_avg = per_driver.agg(
        avg("fuel_per_100km")  .alias("fleet_avg_fuel"),
        avg("alert_rate_per_100").alias("fleet_avg_alert_rate"),
        avg("total_distance_km").alias("fleet_avg_distance"),
    ).collect()[0]

    fleet_avg_fuel     = fleet_avg["fleet_avg_fuel"]     or 1.0
    fleet_avg_alerts   = fleet_avg["fleet_avg_alert_rate"] or 1.0
    fleet_avg_distance = fleet_avg["fleet_avg_distance"]  or 1.0

    # ── Step 3: composite score 0–100 ─────────────────────────────────────────
    #
    #  speed_score     = speed_compliance_rate × 100          (higher = better)
    #  fuel_score      = clamp(fleet_avg / driver_fuel × 100) (lower fuel = better)
    #  alert_score     = clamp((1 - alert_rate/fleet_avg) × 100)
    #  distance_score  = clamp(driver_km / fleet_avg_km × 100)
    #
    scored = (
        per_driver
        .withColumn(
            "speed_score",
            _round(col("speed_compliance_rate") * 100, 2)
        )
        .withColumn(
            "fuel_score",
            _round(
                when(col("fuel_per_100km") > 0,
                    (lit(fleet_avg_fuel) / col("fuel_per_100km")) * 100
                ).otherwise(lit(100.0)), 2
            )
        )
        .withColumn(
            "alert_score",
            _round(
                when(col("alert_rate_per_100") > 0,
                    (lit(1.0) - col("alert_rate_per_100") / lit(fleet_avg_alerts)) * 100
                ).otherwise(lit(100.0)), 2
            )
        )
        .withColumn(
            "distance_score",
            _round(
                (col("total_distance_km") / lit(fleet_avg_distance)) * 100, 2
            )
        )
        # Clamp all component scores to [0, 100]
        .withColumn("speed_score",    _round(
            when(col("speed_score")    > 100, 100).when(col("speed_score")    < 0, 0).otherwise(col("speed_score")),    2))
        .withColumn("fuel_score",     _round(
            when(col("fuel_score")     > 100, 100).when(col("fuel_score")     < 0, 0).otherwise(col("fuel_score")),     2))
        .withColumn("alert_score",    _round(
            when(col("alert_score")    > 100, 100).when(col("alert_score")    < 0, 0).otherwise(col("alert_score")),    2))
        .withColumn("distance_score", _round(
            when(col("distance_score") > 100, 100).when(col("distance_score") < 0, 0).otherwise(col("distance_score")), 2))
        # Weighted composite
        .withColumn(
            "performance_score",
            _round(
                col("speed_score")    * 0.30 +
                col("fuel_score")     * 0.30 +
                col("alert_score")    * 0.25 +
                col("distance_score") * 0.15,
                2
            )
        )
        # Rank drivers (1 = best)
        .withColumn(
            "rank",
            _round(col("performance_score"), 0).cast("int")  # placeholder, window rank below
        )
        .withColumn("stat_date", lit(run_date))
    )

    # ── Step 4: add ranking by score ──────────────────────────────────────────
    rank_w = Window.orderBy(col("performance_score").desc())
    return scored.withColumn(
        "rank",
        col("performance_score").cast("int")   # replaced below
    ).withColumn(
        "rank",
        count("*").over(rank_w)   # dense rank via window
    ).drop("rank").withColumn(
        "fleet_rank",
        _round(
            (lit(1.0) - col("performance_score") / 100.0) *
            count("driver_id").over(Window.orderBy(lit(1))),
            0
        ).cast("int")
    )


# ─────────────────────────────────────────────────────────────────────────────
def run(date_from: str, date_to: str, run_date: str):
    spark = build_spark()
    spark.sparkContext.setLogLevel("WARN")

    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  Batch Job — Driver Performance")
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