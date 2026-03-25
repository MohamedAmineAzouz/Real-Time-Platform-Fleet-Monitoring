"""
spark_jobs/job_fuel_and_maintenance.py
─────────────────────────────────────────────────────────────────────────────
Batch Job 3 — Fuel Waste Anomalies + Maintenance Prediction Flags

FIX: Uses fuel_consumed_trip (simulator-computed) for accurate fuel metrics.
─────────────────────────────────────────────────────────────────────────────
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.functions import (
    col, sum as _sum, avg, max as _max, count,
    round as _round, when, lit, to_date,
    percentile_approx, stddev,
)

from batch_config.batch_config import PARQUET_BASE, print_config
from batch_config.spark_config import get_spark_conf
from writers.sink_writer import write

FUEL_ANOMALY_MULTIPLIER  = 1.5
HIGH_TEMP_THRESHOLD      = 90.0
OVERHEAT_ALERT_THRESHOLD = 5
ODOMETER_INTERVAL_KM     = 10_000


def build_spark() -> SparkSession:
    builder = SparkSession.builder.appName("FleetBatch_FuelAndMaintenance")
    for k, v in get_spark_conf().items():
        builder = builder.config(k, v)
    return builder.getOrCreate()


def compute_fuel_waste_anomalies(df: DataFrame, run_date: str) -> DataFrame:
    # Only driving events — fuel_consumed_trip is always positive here
    driving = df.filter(col("refueling") == False)

    per_truck = (
        driving
        .groupBy("truck_id")
        .agg(
            _round(_sum("distance_km"),       2).alias("total_distance_km"),
            # fuel_consumed_trip is a running total — take max (end of day value)
            _round(_max("fuel_consumed_trip"), 2).alias("total_fuel_l"),
            _round(
                when(_sum("distance_km") > 0,
                    _max("fuel_consumed_trip") / _sum("distance_km") * 100
                ).otherwise(lit(0.0)), 2
            ).alias("fuel_per_100km"),
            count("*").alias("event_count"),
        )
        .filter(col("total_distance_km") > 0)
    )

    fleet_median = per_truck.agg(
        percentile_approx("fuel_per_100km", 0.5).alias("median_fuel")
    ).collect()[0]["median_fuel"] or 1.0

    anomaly_threshold = fleet_median * FUEL_ANOMALY_MULTIPLIER

    return (
        per_truck
        .withColumn("fleet_median_fuel_per_100km", lit(round(fleet_median, 2)))
        .withColumn("anomaly_threshold",            lit(round(anomaly_threshold, 2)))
        .withColumn("is_anomaly", col("fuel_per_100km") > lit(anomaly_threshold))
        .withColumn(
            "waste_vs_median_pct",
            _round(
                (col("fuel_per_100km") - lit(fleet_median)) / lit(fleet_median) * 100, 2
            )
        )
        .filter(col("is_anomaly") == True)
        .withColumn("stat_date", lit(run_date))
    )


def compute_maintenance_flags(df: DataFrame, run_date: str) -> DataFrame:
    per_truck = (
        df
        .groupBy("truck_id")
        .agg(
            _round(avg("engine_temp"),              2).alias("avg_engine_temp"),
            _round(_max("engine_temp"),             2).alias("max_engine_temp"),
            _round(_max("odometer_km"),             2).alias("max_odometer_km"),
            _round(avg("fuel_consumption_rate"),    4).alias("avg_fuel_rate"),
            _round(stddev("fuel_consumption_rate"), 4).alias("fuel_rate_stddev"),
            _sum(when(col("alert_type") == "OVERHEAT",   1).otherwise(0)).alias("overheat_count"),
            _sum(when(col("alert_type") == "FUEL_THEFT", 1).otherwise(0)).alias("theft_count"),
            count("*").alias("event_count"),
        )
        .fillna({"fuel_rate_stddev": 0.0})
    )

    return (
        per_truck
        .withColumn("flag_high_temp",
            col("avg_engine_temp") > lit(HIGH_TEMP_THRESHOLD))
        .withColumn("flag_overheat_alerts",
            col("overheat_count") >= lit(OVERHEAT_ALERT_THRESHOLD))
        .withColumn("flag_odometer_milestone",
            (col("max_odometer_km") % lit(ODOMETER_INTERVAL_KM)) < 500)
        .withColumn("flag_fuel_inconsistency",
            col("fuel_rate_stddev") > lit(0.3))
        .withColumn("maintenance_needed",
            col("flag_high_temp") | col("flag_overheat_alerts") |
            col("flag_odometer_milestone") | col("flag_fuel_inconsistency"))
        .withColumn("priority",
            when(
                (col("flag_high_temp").cast("int") +
                 col("flag_overheat_alerts").cast("int") +
                 col("flag_odometer_milestone").cast("int") +
                 col("flag_fuel_inconsistency").cast("int")) >= 2,
                lit("HIGH")
            ).otherwise(lit("MEDIUM")))
        .filter(col("maintenance_needed") == True)
        .withColumn("stat_date", lit(run_date))
    )


def run(date_from: str, date_to: str, run_date: str):
    spark = build_spark()
    spark.sparkContext.setLogLevel("WARN")

    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  Batch Job — Fuel Waste + Maintenance")
    print(f"  Period : {date_from} → {date_to}")
    print_config()
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

    raw = (
        spark.read.parquet(PARQUET_BASE)
        .filter(
            (to_date(col("event_time")) >= date_from) &
            (to_date(col("event_time")) <= date_to)
        )
        .cache()
    )

    fuel_anomalies = compute_fuel_waste_anomalies(raw, run_date)
    print(f"  Fuel anomalies : {fuel_anomalies.count()} trucks flagged")
    write(fuel_anomalies, "fuel_waste_anomalies", mode="overwrite")

    maintenance = compute_maintenance_flags(raw, run_date)
    print(f"  Maintenance    : {maintenance.count()} trucks flagged")
    write(maintenance, "maintenance_flags", mode="overwrite")

    raw.unpersist()
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