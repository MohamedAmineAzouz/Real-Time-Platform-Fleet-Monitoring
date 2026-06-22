import os
import sys
from datetime import datetime, timedelta
from pyspark.sql import SparkSession, DataFrame, Window
from pyspark.sql.functions import (
    col, avg as _avg, min as _min, max as _max,
    stddev as _stddev, lit, when, unix_timestamp,
    round as _round, abs as _abs
)
from pyspark.ml import Pipeline, PipelineModel
from pyspark.ml.feature import VectorAssembler
from pyspark.ml.regression import RandomForestRegressor, RandomForestRegressionModel
from pyspark.ml.evaluation import RegressionEvaluator

LAKE_BUCKET = os.getenv("LAKE_BUCKET", "fleet-data")
LAKE_PREFIX = os.getenv("LAKE_PREFIX", "silver/truck_history")
S3_PATH = f"s3a://{LAKE_BUCKET}/{LAKE_PREFIX}"
STAGING_PATH = f"s3a://{LAKE_BUCKET}/ml_staging"
MODEL_CANDIDATE_PATH = f"s3a://{LAKE_BUCKET}/models/candidate_model"
MODEL_PRODUCTION_PATH = f"s3a://{LAKE_BUCKET}/models/production_model"
VALIDATION_DATA_PATH = f"s3a://{LAKE_BUCKET}/validation/fixed_validation_dataset"



def label_data(df: DataFrame) -> DataFrame:
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
        .withColumn("avg_speed_window", _avg("speed").over(window_spec))



def get_or_create_fixed_validation_dataset(spark: SparkSession) -> DataFrame:
    """
    Retrieves or creates a fixed validation dataset of known inputs and expected outputs (RUL)
    to act as a unit test for model verification.
    """
    try:
        return spark.read.parquet(VALIDATION_DATA_PATH)
    except Exception:
        print("  [i] Creating default fixed validation dataset...")
        # Create a tiny mock validation set with expected RUL matching the inputs
        # Expected outputs are carefully paired with input values
        data = [
            (1001, 95.0, 60.0, 50.0, 93.0, 2.0, 15.0), # Expected RUL: 15 hours
            (1002, 105.0, 85.0, 40.0, 104.0, 4.5, 3.0), # Expected RUL: 3 hours
            (1003, 75.0, 50.0, 60.0, 75.0, 0.5, 45.0)  # Expected RUL: 45 hours
        ]
        columns = ["truck_id", "engine_temp", "speed", "fuel_level", "avg_temp_window", "stddev_temp_window", "rul"]
        df = spark.createDataFrame(data, columns)
        df.write.mode("overwrite").parquet(VALIDATION_DATA_PATH)
        return df




def run_prepare_data(spark: SparkSession, date_to: str):
    print("🤖 Task 1: Preparing raw telemetry data...")
    target_dt = datetime.strptime(date_to, "%Y-%m-%d")
    paths = []
    # Read the last 30 days of data to have a robust dataset for model training
    for i in range(30):
        d = (target_dt - timedelta(days=i)).strftime("%Y-%m-%d")
        paths.append(f"{S3_PATH}/event_date={d}")

    try:
        raw_df = spark.read.option("basePath", S3_PATH).parquet(*paths)
    except Exception as e:
        print(f"  [!] Fallback: reading entire history filter: {e}")
        min_date = (target_dt - timedelta(days=30)).strftime("%Y-%m-%d")
        raw_df = spark.read.parquet(S3_PATH).filter(col("event_date") >= min_date)

    # Verify required columns exist
    required_cols = ["truck_id", "event_time", "engine_temp", "speed", "fuel_level", "alert_type"]
    for c in required_cols:
        if c not in raw_df.columns:
            raise ValueError(f"Required column '{c}' is missing from raw dataset.")

    # Write prepared data to staging
    raw_df.write.mode("overwrite").parquet(f"{STAGING_PATH}/prepared_data")
    print("✅ Prepared data successfully saved.")




def run_clean_data(spark: SparkSession):
    print("🤖 Task 2: Cleaning prepared telemetry data...")
    df = spark.read.parquet(f"{STAGING_PATH}/prepared_data")

    # Clean records
    df_clean = df.dropDuplicates() \
        .filter((col("speed") >= 0) & (col("speed") <= 150)) \
        .filter((col("fuel_level") >= 0) & (col("fuel_level") <= 100)) \
        .filter((col("engine_temp") >= 30) & (col("engine_temp") <= 150)) \
        .fillna(0)

    # Calculate labels (RUL) and features
    labeled_df = label_data(df_clean)
    feature_df = engineer_features(labeled_df).fillna(0)

    # Save clean dataset
    feature_df.write.mode("overwrite").parquet(f"{STAGING_PATH}/clean_data")
    print("✅ Data cleaning and feature engineering complete.")




def run_split_data(spark: SparkSession):
    print("🤖 Task 3: Splitting dataset into training (70%) and testing (30%)...")
    df = spark.read.parquet(f"{STAGING_PATH}/clean_data")

    train_df, test_df = df.randomSplit([0.7, 0.3], seed=42)

    train_df.write.mode("overwrite").parquet(f"{STAGING_PATH}/train_data")
    test_df.write.mode("overwrite").parquet(f"{STAGING_PATH}/test_data")
    print(f"✅ Data split finished. Train size: {train_df.count()}, Test size: {test_df.count()}")




def run_train_model(spark: SparkSession):
    print("🤖 Task 4: Training model...")
    train_df = spark.read.parquet(f"{STAGING_PATH}/train_data")

    if train_df.count() < 5:
        raise ValueError("Not enough failure data in training set to build a model.")

    assembler = VectorAssembler(
        inputCols=["engine_temp", "speed", "fuel_level", "avg_temp_window", "stddev_temp_window"],
        outputCol="features", handleInvalid="skip"
    )
    rf = RandomForestRegressor(featuresCol="features", labelCol="rul", numTrees=20)
    pipeline = Pipeline(stages=[assembler, rf])
    model = pipeline.fit(train_df)

    # Save model as candidate
    model.write().overwrite().save(MODEL_CANDIDATE_PATH)
    print("✅ Model trained and saved as candidate.")




def run_evaluate_model(spark: SparkSession):
    print("🤖 Task 5: Evaluating model accuracy...")
    test_df = spark.read.parquet(f"{STAGING_PATH}/test_data")
    model = PipelineModel.load(MODEL_CANDIDATE_PATH)

    predictions = model.transform(test_df)

    # Calculate MAPE (Mean Absolute Percentage Error) to determine accuracy (1 - MAPE)
    # To avoid division by zero, we filter out actual RUL = 0
    mape_df = predictions.filter(col("rul") > 0).withColumn(
        "percentage_error",
        _abs(col("prediction") - col("rul")) / col("rul")
    )
    
    mean_mape = mape_df.select(_avg("percentage_error")).collect()[0][0]
    if mean_mape is None:
        mean_mape = 0.0

    accuracy = 1.0 - mean_mape
    accuracy_percentage = accuracy * 100.0

    print(f"  [i] Calculated Model Accuracy: {accuracy_percentage:.2f}%")

    if accuracy_percentage < 90.0:
        raise ValueError(f"Model evaluation failed: Accuracy is {accuracy_percentage:.2f}%, which is below the 90.0% threshold.")

    print("✅ Evaluation passed. Model meets quality standard.")





def run_validate_model(spark: SparkSession):
    print("🤖 Task 6: Validating model on fixed dataset...")
    val_df = get_or_create_fixed_validation_dataset(spark)
    model = PipelineModel.load(MODEL_CANDIDATE_PATH)

    predictions = model.transform(val_df)

    # Check each prediction's error. Maximum allowed is 10%
    error_checked = predictions.withColumn(
        "error_pct",
        _abs(col("prediction") - col("rul")) / col("rul")
    )

    failures = error_checked.filter(col("error_pct") > 0.10).collect()

    if len(failures) > 0:
        for row in failures:
            print(f"  [!] Fail: Truck {row['truck_id']}: Expected RUL {row['rul']} hrs, Predicted {row['prediction']:.2f} hrs (Error: {row['error_pct']*100:.2f}%)")
        raise ValueError(f"Model validation failed: {len(failures)} predictions exceeded the 10% allowed error margin.")

    print("✅ Validation on fixed dataset passed.")

    # Freeze candidate model into production
    print("❄️ Freezing candidate model as the official production model...")
    model.write().overwrite().save(MODEL_PRODUCTION_PATH)
    print("✅ Model frozen successfully.")




if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: job_train_pipeline.py --task <task_name> [date_to]")
        sys.exit(1)

    task_name = ""
    date_to = datetime.now().strftime("%Y-%m-%d")

    # Simple argument parsing
    args = sys.argv[1:]
    for i in range(len(args)):
        if args[i] == "--task" and i + 1 < len(args):
            task_name = args[i+1]
        elif i == len(args) - 1 and not args[i].startswith("--"):
            date_to = args[i]

    spark = SparkSession.builder.appName(f"MLTraining_{task_name}").getOrCreate()

    try:
        if task_name == "prepare_data":
            run_prepare_data(spark, date_to)
        elif task_name == "clean_data":
            run_clean_data(spark)
        elif task_name == "split_data":
            run_split_data(spark)
        elif task_name == "train_model":
            run_train_model(spark)
        elif task_name == "evaluate_model":
            run_evaluate_model(spark)
        elif task_name == "validate_model":
            run_validate_model(spark)
        else:
            print(f"Unknown task: {task_name}")
            sys.exit(1)
    finally:
        spark.stop()
