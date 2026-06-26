import os
import sys
from datetime import datetime
from pyspark.sql import SparkSession, DataFrame, Window
from pyspark.sql.functions import (
    col, avg as _avg, min as _min, max as _max,
    stddev as _stddev, lit, when, row_number, round as _round
)
from pyspark.ml import PipelineModel

CASSANDRA_KEYSPACE = os.getenv("CASSANDRA_KEYSPACE", "fleet")
LAKE_BUCKET = os.getenv("LAKE_BUCKET", "fleet-data")
LAKE_PREFIX = os.getenv("LAKE_PREFIX", "silver/truck_history")
S3_PATH = f"s3a://{LAKE_BUCKET}/{LAKE_PREFIX}"
MODEL_PRODUCTION_PATH = f"s3a://{LAKE_BUCKET}/models/production_model"


def engineer_features(df: DataFrame) -> DataFrame:
    window_spec = Window.partitionBy("truck_id").orderBy("event_time").rowsBetween(-20, 0)
    return df \
        .withColumn("avg_temp_window", _avg("engine_temp").over(window_spec)) \
        .withColumn("stddev_temp_window", _stddev("engine_temp").over(window_spec)) \
        .withColumn("avg_speed_window", _avg("speed").over(window_spec)) \
        .fillna(0)


def run_job(spark: SparkSession, date_from: str, date_to: str):
    print(f"🤖 Starting Daily ML-Based Maintenance Prediction: {date_from}")

    spark.conf.set("spark.sql.shuffle.partitions", "10")
    spark.conf.set("spark.sql.files.maxPartitionBytes", "256mb")

    # 1. LOAD TODAY'S TELEMETRY DATA
    current_path = f"{S3_PATH}/event_date={date_from}"
    print(f"  [i] Reading telemetry from: {current_path}")
    try:
        current_data = spark.read.parquet(current_path).repartition(10)
    except Exception as e:
        print(f"  [!] Today's folder not found or error reading: {e}. Skipping prediction.")
        return

    # 2. FEATURE ENGINEERING
    print("  [1/3] Engineering features...")
    current_features = engineer_features(current_data)
    
    # Isolate latest telemetry record for each truck
    latest_telemetry = current_features.withColumn("rn", row_number().over(
        Window.partitionBy("truck_id").orderBy(col("event_time").desc())
    )).filter(col("rn") == 1).drop("rn")

    # 3. LOAD PRODUCTION MODEL & RUN INFERENCE
    print(f"  [2/3] Loading production model from {MODEL_PRODUCTION_PATH}...")
    try:
        model = PipelineModel.load(MODEL_PRODUCTION_PATH)
    except Exception as e:
        print(f"  [!] Critical error: Could not load production model. Has the monthly training run? Error: {e}")
        raise e

    print("  [3/3] Predicting RUL for current fleet...")
    final_predictions = model.transform(latest_telemetry)

    results = final_predictions.select(
        col("truck_id"),
        _round(col("prediction"), 2).alias("predicted_rul_hours"),
        when(col("prediction") < 24, lit("HIGH"))
        .when(col("prediction") < 72, lit("MEDIUM"))
        .otherwise(lit("LOW")).alias("priority"),
        lit(datetime.now().strftime("%Y-%m-%d %H:%M:%S")).alias("stat_date")
    )

    # 4. SAVE TO CASSANDRA
    print(f"  [i] Saving results to Cassandra keyspace: {CASSANDRA_KEYSPACE}...")
    results.write \
        .format("org.apache.spark.sql.cassandra") \
        .mode("append") \
        .options(table="batch_maintenance_prediction", keyspace=CASSANDRA_KEYSPACE) \
        .save()

    print("✅ Daily Predictive Maintenance Inference Finished successfully.")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: job_maintenance_prediction.py <date_from> <date_to>")
        sys.exit(1)
    spark = SparkSession.builder.appName("MaintenancePredictionInference").getOrCreate()
    run_job(spark, sys.argv[1], sys.argv[2])
    spark.stop()
