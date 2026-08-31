from pyspark.sql import SparkSession
from pyspark.sql.functions import ( col, lit, when, from_json, current_timestamp, to_timestamp, to_date, expr)
from config import *
from schemas import get_truck_schema
from cassandra_writer import write_to_cassandra
from storage_backend import (
   configure_storage,
   ensure_bucket_exists,
   get_storage_uri
)

import os

def create_spark_session():
    remote_host = os.getenv("REMOTE_HOST", "spark-master")
    builder = (
        SparkSession.builder
        .appName("FleetSpeedLayer")
        .master(f"spark://{remote_host}:7077")
        .config("spark.cassandra.connection.host", CASSANDRA_HOST)
        .config("spark.cassandra.connection.port", CASSANDRA_PORT)
        .config("spark.jars.ivy", "/home/spark/.ivy2")
        .config("spark.cores.max", "6")
    )
    builder = configure_storage(builder)
    return builder.getOrCreate()

def classify_alert(df):
    return (
      df
      .withColumn(
        "alert_type",
        when(col("speed") > SPEED_THRESHOLD, lit("OVERSPEED"))
        .when(col("engine_temp") > TEMP_THRESHOLD, lit("OVERHEAT"))
        .when(col("theft")==True,lit("FUEL_THEFT"))
        .when(col("fuel_level") < FUEL_LOW,lit("LOW_FUEL"))
        .otherwise(lit("NORMAL"))
      )
      .withColumn("is_alert", col("alert_type")!="NORMAL")
    )

def write_to_minio_lake(batch_df, batch_id):
    LAKE_PATH = get_storage_uri()

    if batch_df.isEmpty():
        return
    try:
        (
            batch_df.write
            .mode("append")
            .partitionBy("event_date")
            .parquet(LAKE_PATH)
        )
        print(f"✅ Data Lake: {batch_df.count()} lignes écrites dans MinIO (Batch {batch_id})")
    except Exception as e:
        print(f"❌ Erreur écriture MinIO Data Lake: {e}")


def main():
    ensure_bucket_exists()
    # LAKE_PATH = get_storage_uri()

    spark = create_spark_session()
    spark.sparkContext.setLogLevel("WARN")

    schema = get_truck_schema()

    kafka_df = (
      spark.readStream
      .format("kafka")
      .option("kafka.bootstrap.servers", KAFKA_BROKER)
      .option("subscribe", KAFKA_TOPIC )
      .load()
    )

    parsed = (
      kafka_df
      .selectExpr("CAST(value AS STRING) as json_str")
      .select(from_json( col("json_str"), schema).alias("data"))
      .select("data.*")
    )

    enriched = (
      parsed
      .withColumn("processed_at", current_timestamp() + expr("INTERVAL 1 HOUR"))
      .withColumn("event_time", to_timestamp("timestamp"))
      .withColumn("event_date", to_date("event_time"))
      .withColumn("distance_km", col("distance_km"))
      # Add constant columns for lake consistency
      .withColumn("fuel_used", lit(0.0))
      .withColumn("fuel_consumption_rate", lit(0.0))
      .withColumn("high_consumption", lit(False))
    )

    with_alerts = classify_alert(enriched)

    # ── QUERY 1: Real-time Cassandra (Trigger: 2s) ──────────────────────────
    query_cas = (
      with_alerts.writeStream
      .foreachBatch(write_to_cassandra)
      .outputMode("append")
      .option("checkpointLocation", "/tmp/checkpoints/cassandra")
      .trigger(processingTime="2 seconds")
      .start()
    )

    # ── QUERY 2: Data Lake MinIO (Trigger: 5m) ─────────────────────────────
    query_lake = (
      with_alerts.writeStream
      .foreachBatch(write_to_minio_lake)
      .outputMode("append")
      .option("checkpointLocation", "/tmp/checkpoints/lake_batch")
      .trigger(processingTime="5 minutes")
      .start()
    )

    print("🚀 Streaming Sinks Started: Cassandra (2s) & Data Lake (5m)")
    spark.streams.awaitAnyTermination()

if __name__ == "__main__":
    main()