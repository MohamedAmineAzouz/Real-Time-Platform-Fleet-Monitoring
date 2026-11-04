"""
spark_jobs/job_eta_train_pipeline.py
─────────────────────────────────────────────────────────────────────────────
Dynamic ETA & Route Optimization — ML Training Pipeline
─────────────────────────────────────────────────────────────────────────────
Uses Spark ML's GBTRegressor (Gradient Boosted Trees — Spark's native
equivalent of XGBoost) to learn corridor-level travel duration patterns.

Features fed to the model:
  - hour_of_day   : integer 0–23  (time-of-day signal)
  - day_of_week   : integer 1–7   (weekday pattern, 1=Sunday)
  - distance_km   : corridor reference distance
  - avg_speed_kmh : rolling average speed of trucks on this corridor

Label:
  - duration_h    : actual elapsed hours to complete the trip
                    (derived from time-delta between first & last event
                     for each (truck_id, start_city, end_city) trip)

Tasks dispatched via --task <name>:
  prepare_data  → Read 90-day silver parquet, build trip-level rows
  clean_data    → Filter/deduplicate, compute features
  split_data    → 70/30 random split
  train_model   → Fit GBT pipeline, save candidate model
  validate_model→ RMSE gate on fixed validation set; freeze as production
─────────────────────────────────────────────────────────────────────────────
"""

import os
import sys
from datetime import datetime, timedelta

from pyspark.sql import SparkSession, DataFrame, Window
from pyspark.sql.functions import (
    col, avg as _avg, min as _min, max as _max, count as _count,
    hour, dayofweek, unix_timestamp, lit, round as _round,
    first, last, abs as _abs, sqrt as _sqrt
)
from pyspark.ml import Pipeline, PipelineModel
from pyspark.ml.feature import VectorAssembler
from pyspark.ml.regression import GBTRegressor
from pyspark.ml.evaluation import RegressionEvaluator

# ── Paths ──────────────────────────────────────────────────────────────────
LAKE_BUCKET = os.getenv("LAKE_BUCKET", "fleet-data")
LAKE_PREFIX = os.getenv("LAKE_PREFIX", "silver/truck_history")
S3_PATH                 = f"s3a://{LAKE_BUCKET}/{LAKE_PREFIX}"
ETA_STAGING_PATH        = f"s3a://{LAKE_BUCKET}/eta_staging"
ETA_CANDIDATE_PATH      = f"s3a://{LAKE_BUCKET}/models/eta_candidate_model"
ETA_PRODUCTION_PATH     = f"s3a://{LAKE_BUCKET}/models/eta_production_model"
ETA_VALIDATION_PATH     = f"s3a://{LAKE_BUCKET}/validation/eta_fixed_validation"

MIN_TRIP_SAMPLES = 5       
MIN_DURATION_H   = 0.1    
MAX_DURATION_H   = 24.0   
RMSE_THRESHOLD   = 2.0    



def build_trip_features(df: DataFrame) -> DataFrame:
    """
    From raw telemetry events, collapse each (truck_id, start_city, end_city)
    trip into a single row with:
      - duration_h      (label)
      - hour_of_day     (from trip start time)
      - day_of_week     (from trip start time)
      - avg_speed_kmh
      - distance_km     (max odometer diff within the trip)
    """
    w_trip = Window.partitionBy("truck_id", "start_city", "end_city") \
                   .orderBy("event_time")

    trips = df \
        .withColumn("trip_start_ts", _min(unix_timestamp("event_time")).over(
            Window.partitionBy("truck_id", "start_city", "end_city"))) \
        .withColumn("trip_end_ts", _max(unix_timestamp("event_time")).over(
            Window.partitionBy("truck_id", "start_city", "end_city"))) \
        .withColumn("trip_start_dt", col("trip_start_ts").cast("timestamp")) \
        .withColumn("duration_h",
            (col("trip_end_ts") - col("trip_start_ts")) / 3600.0) \
        .withColumn("hour_of_day", hour(col("trip_start_dt"))) \
        .withColumn("day_of_week", dayofweek(col("trip_start_dt")))

    trip_agg = trips.groupBy(
        "truck_id", "start_city", "end_city",
        "hour_of_day", "day_of_week"
    ).agg(
        _round(_avg("duration_h"), 4).alias("duration_h"),
        _round(_avg("speed"), 2).alias("avg_speed_kmh"),
        _round(_max("distance_km"), 2).alias("distance_km"),
        _count("*").alias("event_count")
    )

    return trip_agg



def run_prepare_data(spark: SparkSession, date_to: str):
    print("🤖 Task 1: Preparing 90-day telemetry for ETA model training...")
    target_dt = datetime.strptime(date_to, "%Y-%m-%d")

    paths = []
    for i in range(90):
        d = (target_dt - timedelta(days=i)).strftime("%Y-%m-%d")
        paths.append(f"{S3_PATH}/event_date={d}")

    try:
        raw_df = spark.read.option("basePath", S3_PATH).parquet(*paths)
    except Exception as e:
        print(f"  [!] Multi-path read failed, falling back to full scan: {e}")
        min_date = (target_dt - timedelta(days=90)).strftime("%Y-%m-%d")
        from pyspark.sql.functions import to_date
        raw_df = spark.read.parquet(S3_PATH).filter(
            to_date(col("event_time")) >= min_date
        )

    required_cols = ["truck_id", "event_time", "start_city", "end_city",
                     "speed", "distance_km"]
    for c in required_cols:
        if c not in raw_df.columns:
            raise ValueError(f"Required column '{c}' missing from silver parquet.")

    slim_df = raw_df.select(*required_cols) \
                    .filter(col("start_city").isNotNull()) \
                    .filter(col("end_city").isNotNull()) \
                    .filter(col("start_city") != col("end_city"))

    slim_df.write.mode("overwrite").parquet(f"{ETA_STAGING_PATH}/prepared_data")
    print(f"✅ Prepared data saved. Rows: {slim_df.count()}")


def run_clean_data(spark: SparkSession):
    print("🤖 Task 2: Cleaning data and engineering trip-level features...")
    df = spark.read.parquet(f"{ETA_STAGING_PATH}/prepared_data")

    df_clean = df.dropDuplicates(["truck_id", "event_time"]) \
                 .filter((col("speed") >= 0) & (col("speed") <= 150)) \
                 .filter(col("distance_km") >= 0) \
                 .fillna(0) \
                 .repartition(10, "truck_id")

    trip_df = build_trip_features(df_clean)

    filtered = trip_df.filter(
        (col("duration_h") >= MIN_DURATION_H) &
        (col("duration_h") <= MAX_DURATION_H) &
        (col("avg_speed_kmh") > 0) &
        (col("distance_km") > 0)
    )

    corridor_counts = filtered.groupBy("start_city", "end_city") \
                               .agg(_count("*").alias("trip_count"))
    qualified = filtered.join(
        corridor_counts.filter(col("trip_count") >= MIN_TRIP_SAMPLES),
        ["start_city", "end_city"]
    ).drop("trip_count", "truck_id", "event_count")

    qualified.write.mode("overwrite").parquet(f"{ETA_STAGING_PATH}/clean_data")
    print(f"✅ Clean feature dataset saved. Rows: {qualified.count()}")


def run_split_data(spark: SparkSession):
    print("🤖 Task 3: Splitting dataset (70% train / 30% test)...")
    df = spark.read.parquet(f"{ETA_STAGING_PATH}/clean_data")

    train_df, test_df = df.randomSplit([0.7, 0.3], seed=42)
    train_df.write.mode("overwrite").parquet(f"{ETA_STAGING_PATH}/train_data")
    test_df.write.mode("overwrite").parquet(f"{ETA_STAGING_PATH}/test_data")

    print(f"✅ Split complete — Train: {train_df.count()}, Test: {test_df.count()}")


def run_train_model(spark: SparkSession):
    print("🤖 Task 4: Training GBT ETA model...")
    train_df = spark.read.parquet(f"{ETA_STAGING_PATH}/train_data")

    if train_df.count() < 10:
        raise ValueError(
            "Not enough trip samples to train a reliable ETA model. "
            "Ensure at least 90 days of silver telemetry is available."
        )

    assembler = VectorAssembler(
        inputCols=["hour_of_day", "day_of_week", "avg_speed_kmh", "distance_km"],
        outputCol="features",
        handleInvalid="skip"
    )

    gbt = GBTRegressor(
        featuresCol="features",
        labelCol="duration_h",
        maxIter=50,          # enough for convergence on small fleet data
        maxDepth=5,          # moderate depth to avoid overfitting
        stepSize=0.1,        # learning rate
        seed=42
    )

    pipeline = Pipeline(stages=[assembler, gbt])
    model = pipeline.fit(train_df)

    model.write().overwrite().save(ETA_CANDIDATE_PATH)
    print("✅ GBT ETA model trained and saved as candidate.")


def run_validate_model(spark: SparkSession):
    print("🤖 Task 5: Validating ETA model on fixed dataset + freezing to production...")

    # ── Fixed validation dataset (synthetic but realistic Moroccan corridors) ──
    try:
        val_df = spark.read.parquet(ETA_VALIDATION_PATH)
        print("  [i] Loaded existing fixed validation dataset.")
    except Exception:
        print("  [i] Creating fixed ETA validation dataset...")
        # (hour, dow, avg_speed, distance, expected_duration_h)
        data = [
            (8,  2, 90.0, 350.0, 3.9),   # Casablanca → Marrakech, Monday AM
            (14, 4, 85.0, 340.0, 4.0),   # Casablanca → Marrakech, Wednesday PM
            (7,  3, 95.0, 300.0, 3.2),   # Casablanca → Rabat, Tuesday AM
            (17, 5, 75.0, 295.0, 3.9),   # Casablanca → Rabat, Thursday rush
            (10, 6, 88.0, 560.0, 6.4),   # Casablanca → Fes, Friday AM
            (9,  2, 92.0, 550.0, 6.0),   # Casablanca → Fes, Monday AM
            (6,  3, 98.0, 230.0, 2.3),   # Rabat → Tanger, Tuesday early
            (15, 4, 80.0, 225.0, 2.8),   # Rabat → Tanger, Wednesday PM
        ]
        columns = ["hour_of_day", "day_of_week", "avg_speed_kmh",
                   "distance_km", "duration_h"]
        val_df = spark.createDataFrame(data, columns)
        val_df.write.mode("overwrite").parquet(ETA_VALIDATION_PATH)

    model = PipelineModel.load(ETA_CANDIDATE_PATH)
    predictions = model.transform(val_df)

    # Evaluate RMSE
    evaluator = RegressionEvaluator(
        labelCol="duration_h",
        predictionCol="prediction",
        metricName="rmse"
    )
    rmse = evaluator.evaluate(predictions)
    print(f"  [i] Validation RMSE: {rmse:.4f} hours (threshold: {RMSE_THRESHOLD}h)")

    print("\n📊 ETA Predictions vs Expected:")
    print("─" * 60)
    for row in predictions.select(
        "hour_of_day", "day_of_week", "distance_km",
        "duration_h", "prediction"
    ).collect():
        err = abs(row["prediction"] - row["duration_h"])
        status = "✅" if err <= 1.0 else "⚠️ "
        print(f"  {status} h={row['hour_of_day']:02d} dow={row['day_of_week']} "
              f"dist={row['distance_km']:.0f}km → "
              f"expected {row['duration_h']:.2f}h | "
              f"predicted {row['prediction']:.2f}h | "
              f"err {err:.2f}h")
    print("─" * 60)

    if rmse > RMSE_THRESHOLD:
        raise ValueError(
            f"ETA model validation failed: RMSE={rmse:.4f}h exceeds threshold "
            f"of {RMSE_THRESHOLD}h. Model not promoted to production."
        )

    print("❄️  Freezing candidate ETA model as production...")
    model.write().overwrite().save(ETA_PRODUCTION_PATH)
    print("✅ ETA model frozen to production successfully.")


# ── Entrypoint ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: job_eta_train_pipeline.py --task <task_name> [date_to]")
        sys.exit(1)

    task_name = ""
    date_to = datetime.now().strftime("%Y-%m-%d")

    args = sys.argv[1:]
    for i in range(len(args)):
        if args[i] == "--task" and i + 1 < len(args):
            task_name = args[i + 1]
        elif i == len(args) - 1 and not args[i].startswith("--"):
            date_to = args[i]

    spark = SparkSession.builder \
        .appName(f"ETA_Training_{task_name}") \
        .getOrCreate()

    try:
        if task_name == "prepare_data":
            run_prepare_data(spark, date_to)
        elif task_name == "clean_data":
            run_clean_data(spark)
        elif task_name == "split_data":
            run_split_data(spark)
        elif task_name == "train_model":
            run_train_model(spark)
        elif task_name == "validate_model":
            run_validate_model(spark)
        else:
            print(f"Unknown task: '{task_name}'. Valid tasks: "
                  "prepare_data, clean_data, split_data, train_model, validate_model")
            sys.exit(1)
    finally:
        spark.stop()
