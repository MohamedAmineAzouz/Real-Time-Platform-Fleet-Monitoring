from pyspark.sql import SparkSession
from pyspark.sql.functions import ( col, lit, when, from_json, current_timestamp, to_timestamp, to_date, expr)
from config import *
from schemas import get_truck_schema
from cassandra_writer import write_to_cassandra
from storage_backend import (
   configure_storage,
   ensure_bucket_exists
)


def create_spark_session():

    builder = (
        SparkSession.builder
        .appName("FleetSpeedLayer")
        .config("spark.cassandra.connection.host", CASSANDRA_HOST)
        .config("spark.cassandra.connection.port", CASSANDRA_PORT)
    )

    builder = configure_storage(
        builder
    )

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



def main():
    ensure_bucket_exists()

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
    )

    with_alerts = classify_alert(enriched)

    query = (
      with_alerts.writeStream
      .foreachBatch( write_to_cassandra)
      .outputMode("append")
      .option( "checkpointLocation", "/tmp/checkpoints/truck_latest" )
      .trigger(processingTime="2 seconds")
      .start()
    )

    print(
      "Streaming started..."
    )

    query.awaitTermination()



if __name__ == "__main__":
    main()
