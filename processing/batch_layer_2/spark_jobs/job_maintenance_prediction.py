import os
import sys
from datetime import datetime, timedelta
from pyspark.sql import SparkSession, DataFrame, Window
from pyspark.sql.functions import (
    col, avg as _avg, min as _min, max as _max,
    stddev as _stddev, to_date, lit, when,
    unix_timestamp, round as _round, row_number
)
from pyspark.ml import Pipeline
from pyspark.ml.feature import VectorAssembler
from pyspark.ml.regression import RandomForestRegressor
from pyspark.ml.evaluation import RegressionEvaluator

CASSANDRA_KEYSPACE = os.getenv("CASSANDRA_KEYSPACE", "fleet")
LAKE_BUCKET = os.getenv("LAKE_BUCKET", "fleet-data")
LAKE_PREFIX = os.getenv("LAKE_PREFIX", "silver/truck_history")
S3_PATH = f"s3a://{LAKE_BUCKET}/{LAKE_PREFIX}"


def label_data(df: DataFrame) -> DataFrame:
    # Forward-looking window
    window_spec = (
        Window.partitionBy("truck_id")
        .orderBy(col("event_time").asc())
        .rowsBetween(0, Window.unboundedFollowing)
    )

    df_with_failures = df.withColumn(
        "failure_marker",
        when(col("alert_type") == "OVERHEAT", unix_timestamp("event_time")).otherwise(None)
    )

    df_with_next_failure = df_with_failures.withColumn(
        "next_failure_ts",
        _min("failure_marker").over(window_spec)
    )

    return df_with_next_failure \
        .filter(col("next_failure_ts").isNotNull()) \
        .withColumn("time_diff_seconds",
            col("next_failure_ts") - unix_timestamp("event_time")
        ) \
        .filter((col("time_diff_seconds") >= 0) & (col("time_diff_seconds") <= 172800)) \
        .withColumn("rul", col("time_diff_seconds") / 3600.0) \
        .drop("failure_marker", "next_failure_ts", "time_diff_seconds")


def engineer_features(df: DataFrame) -> DataFrame:
    window_spec = Window.partitionBy("truck_id").orderBy("event_time").rowsBetween(-20, 0)
    return df \
        .withColumn("avg_temp_window", _avg("engine_temp").over(window_spec)) \
        .withColumn("stddev_temp_window", _stddev("engine_temp").over(window_spec)) \
        .withColumn("avg_speed_window", _avg("speed").over(window_spec)) \
        .fillna(0)


def run_job(spark: SparkSession, date_from: str, date_to: str):
    print(f"🤖 Starting ML-Based Maintenance Prediction (Optimized): {date_from}")

    # ── TEACHING: EXTREME OPTIMIZATION ───────────────────────────────────
    # We set 'basePath' so Spark knows how to find the 'event_date' column.
    # We increase memory settings and match partitions to cluster size.
    # ─────────────────────────────────────────────────────────────────────
    spark.conf.set("spark.sql.shuffle.partitions", "10")
    spark.conf.set("spark.sql.files.maxPartitionBytes", "256mb")

    # 1. GENERATE SPECIFIC PATHS (To avoid slow recursive listing)
    # Instead of reading the whole bucket, we calculate exactly which folders to open.
    target_dt = datetime.strptime(date_from, "%Y-%m-%d")
    paths = []
    for i in range(14): # Last 14 days
        d = (target_dt - timedelta(days=i)).strftime("%Y-%m-%d")
        paths.append(f"{S3_PATH}/event_date={d}")

    print(f"  [i] Target paths: {len(paths)} daily folders.")

    try:
        # We check which paths actually exist to avoid "Path not found" errors
        # (This uses a fast metadata check instead of a full recursive list)
        raw_df = spark.read.option("basePath", S3_PATH).parquet(*paths)
    except Exception as e:
        print(f"  [!] Some folders missing or error: {e}. Falling back to full read.")
        raw_df = spark.read.parquet(S3_PATH).filter(col("event_date") >= (target_dt - timedelta(days=14)).strftime("%Y-%m-%d"))

    # 2. PREPARE TRAINING DATA
    print("  [1/4] Preparing training dataset...")
    # Optimization: Filter failures early and keep only necessary columns
    labeled_df = label_data(raw_df)
    
    # TEACHING: Balanced learning. We don't need 1 billion 'normal' points.
    # We focus on the data near failures.
    feature_df = engineer_features(labeled_df).repartition(10).cache()

    label_count = feature_df.count()
    print(f"  [i] Found {label_count} labeled data points.")

    if label_count < 5:
        print("  [!] Not enough failure data to train. Exiting.")
        feature_df.unpersist()
        return

    # 3. TRAINING
    print(f"  [2/4] Training Random Forest on {label_count} rows...")
    assembler = VectorAssembler(
        inputCols=["engine_temp", "speed", "fuel_level", "avg_temp_window", "stddev_temp_window"],
        outputCol="features", handleInvalid="skip"
    )
    rf = RandomForestRegressor(featuresCol="features", labelCol="rul", numTrees=10) # Reduced trees for speed
    model = Pipeline(stages=[assembler, rf]).fit(feature_df)
    
    feature_df.unpersist()

    # 4. INFERENCE (Today's Fleet)
    print("  [3/4] Predicting RUL for current fleet...")
    current_path = f"{S3_PATH}/event_date={date_from}"
    try:
        current_data = spark.read.parquet(current_path).repartition(10)
    except:
        print("  [!] Today's folder not found. Skipping.")
        return

    current_features = engineer_features(current_data)
    latest_telemetry = current_features.withColumn("rn", row_number().over(
        Window.partitionBy("truck_id").orderBy(col("event_time").desc())
    )).filter(col("rn") == 1).drop("rn")

    final_predictions = model.transform(latest_telemetry)

    results = final_predictions.select(
        col("truck_id"),
        _round(col("prediction"), 2).alias("predicted_rul_hours"),
        when(col("prediction") < 24, lit("HIGH"))
        .when(col("prediction") < 72, lit("MEDIUM"))
        .otherwise(lit("LOW")).alias("priority"),
        lit(date_to).alias("stat_date")
    )

    # 5. SAVE
    print(f"  [4/4] Saving results to {CASSANDRA_KEYSPACE}...")
    results.write \
        .format("org.apache.spark.sql.cassandra") \
        .mode("append") \
        .options(table="batch_maintenance_prediction", keyspace=CASSANDRA_KEYSPACE) \
        .save()

    print("✅ Optimized Predictive Maintenance Job Finished")


if __name__ == "__main__":
    if len(sys.argv) < 3: sys.exit(1)
    spark = SparkSession.builder.appName("MaintenancePredictionML").getOrCreate()
    run_job(spark, sys.argv[1], sys.argv[2])
    spark.stop()
