"""
spark_jobs/job_eta_prediction.py
─────────────────────────────────────────────────────────────────────────────
Dynamic ETA & Route Optimization — Daily Inference Job
─────────────────────────────────────────────────────────────────────────────
Loads the frozen production ETA model and runs inference for every
active corridor observed in today's telemetry.

Output columns (→ batch_eta_prediction):
  start_city           text
  end_city             text
  stat_date            text       (today's date string YYYY-MM-DD)
  hour_of_day          int
  day_of_week          int
  predicted_eta_hours  double
  avg_speed_kmh        double
  distance_km          double
  confidence           text       (HIGH / MEDIUM / LOW)
  sample_count         int
─────────────────────────────────────────────────────────────────────────────
"""

import os
import sys
from datetime import datetime

from pyspark.sql import SparkSession, DataFrame, Window
from pyspark.sql.functions import (
    col, avg as _avg, max as _max, count as _count,
    hour, dayofweek, lit, when, round as _round
)
from pyspark.ml import PipelineModel

CASSANDRA_KEYSPACE  = os.getenv("CASSANDRA_KEYSPACE", "fleet")
LAKE_BUCKET         = os.getenv("LAKE_BUCKET", "fleet-data")
LAKE_PREFIX         = os.getenv("LAKE_PREFIX", "silver/truck_history")
S3_PATH             = f"s3a://{LAKE_BUCKET}/{LAKE_PREFIX}"
ETA_PRODUCTION_PATH = f"s3a://{LAKE_BUCKET}/models/eta_production_model"


HIGH_CONFIDENCE_THRESHOLD   = 5   
MEDIUM_CONFIDENCE_THRESHOLD = 2   


def build_inference_features(df: DataFrame, run_hour: int, run_dow: int) -> DataFrame:
    """
    Aggregate today's telemetry into one feature row per corridor.
    We use the current wall-clock hour and day-of-week as time signals,
    and compute avg_speed and distance from the live trucks on that corridor.
    """
    corridor_agg = df.groupBy("start_city", "end_city").agg(
        _round(_avg("speed"), 2).alias("avg_speed_kmh"),
        _round(_max("distance_km"), 2).alias("distance_km"),
        _count("truck_id").alias("sample_count")
    ) \
    .withColumn("hour_of_day", lit(run_hour)) \
    .withColumn("day_of_week", lit(run_dow)) \
    .filter(col("avg_speed_kmh") > 0) \
    .filter(col("distance_km") > 0)

    return corridor_agg


def run_job(spark: SparkSession, date_from: str, date_to: str):
    now = datetime.now()
    run_hour = now.hour
    run_dow = (now.weekday() + 2) % 7 or 7

    print(f"🚦 Starting Daily ETA Prediction: {date_from} "
          f"(hour={run_hour}, dow={run_dow})")

    current_path = f"{S3_PATH}/event_date={date_from}"
    print(f"  [i] Reading telemetry from: {current_path}")
    try:
        today_df = spark.read.parquet(current_path).repartition(10)
    except Exception as e:
        print(f"  [!] Today's folder not found or empty: {e}. Skipping.")
        return

    active_df = today_df \
        .filter(col("start_city").isNotNull()) \
        .filter(col("end_city").isNotNull()) \
        .filter(col("start_city") != col("end_city")) \
        .filter(col("speed") > 0) \
        .filter(col("in_maintenance") == False)  # noqa: E712

    if active_df.count() == 0:
        print("  [!] No active trucks found in today's data. Skipping.")
        return

    print("  [1/3] Building corridor feature rows...")
    features_df = build_inference_features(active_df, run_hour, run_dow)

    print(f"  [2/3] Loading production ETA model from {ETA_PRODUCTION_PATH}...")
    try:
        model = PipelineModel.load(ETA_PRODUCTION_PATH)
    except Exception as e:
        print(f"  [!] Critical: Could not load production ETA model. "
              f"Has the monthly training run? Error: {e}")
        raise e

    print("  [3/3] Predicting ETAs for all active corridors...")
    predictions = model.transform(features_df)

    results = predictions.select(
        col("start_city"),
        col("end_city"),
        lit(date_from).alias("stat_date"),
        col("hour_of_day"),
        col("day_of_week"),
        _round(col("prediction"), 2).alias("predicted_eta_hours"),
        col("avg_speed_kmh"),
        col("distance_km"),
        when(col("sample_count") >= HIGH_CONFIDENCE_THRESHOLD, lit("HIGH"))
        .when(col("sample_count") >= MEDIUM_CONFIDENCE_THRESHOLD, lit("MEDIUM"))
        .otherwise(lit("LOW")).alias("confidence"),
        col("sample_count"),
    ).filter(col("predicted_eta_hours") > 0)

    print(f"  [i] Writing {results.count()} corridor predictions "
          f"to {CASSANDRA_KEYSPACE}.batch_eta_prediction...")
    results.write \
        .format("org.apache.spark.sql.cassandra") \
        .mode("append") \
        .options(table="batch_eta_prediction", keyspace=CASSANDRA_KEYSPACE) \
        .save()

    print("✅ Daily ETA Prediction Inference completed successfully.")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: job_eta_prediction.py <date_from> <date_to>")
        sys.exit(1)

    spark = SparkSession.builder \
        .appName("ETAPredictionInference") \
        .getOrCreate()

    run_job(spark, sys.argv[1], sys.argv[2])
    spark.stop()
