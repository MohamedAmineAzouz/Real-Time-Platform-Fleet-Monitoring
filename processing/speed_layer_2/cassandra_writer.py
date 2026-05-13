import time
from pyspark.sql.functions import (lit, col, to_date)
from config import *
from storage_backend import get_storage_uri


LAKE_PATH = get_storage_uri()


def write_to_cassandra(batch_df, batch_id: int):
    """
    Write latest state per truck to Cassandra.
    Uses dropDuplicates to keep latest record per truck (streaming-compatible).
    Also inserts into truck_history (all records) and alerts (alert records only).
    """
    t0 = time.time()

    if batch_df.rdd.isEmpty():
        print(f"[batch #{batch_id:05d}] ⚠️  Empty batch")
        return

    deduped = batch_df.dropDuplicates(["truck_id"])
    
    # Select only the columns needed for truck_latest, truck_history
    columns = [
        "truck_id", "processed_at", "event_time",
        "latitude", "longitude", "speed", "fuel_level", "engine_temp",
        "driver_id", "start_city", "end_city", "odometer_km",
        "refueling", "refuel_city", "anomaly", "theft", "theft_amount",
        "distance_km", "fuel_used", "fuel_consumption_rate", "high_consumption",
        "fuel_consumed_trip", "fuel_consumed_l", "fuel_refueled",
        "alert_type", "is_alert",
        "in_maintenance", "maintenance_type", "maintenance_desc"
    ]


    # Add placeholder metrics (real calculations done in batch layer)
    final_df = (deduped
        .withColumn("fuel_used",             lit(0.0))
        .withColumn("fuel_consumption_rate", lit(0.0))
        .withColumn("high_consumption",      lit(False))
        .select(columns)
    )

    # Write to truck_latest
    (final_df.write
        .format("org.apache.spark.sql.cassandra")
        .mode("append")
        .options(table=CASSANDRA_TABLE, keyspace=CASSANDRA_KEYSPACE)
        .save()
    )

    # Write ALL records to truck_history
    history_df = final_df.select(columns)
    (history_df.write
        .format("org.apache.spark.sql.cassandra")
        .mode("append")
        .options(table=TRUCK_HISTORY_TABLE, keyspace=CASSANDRA_KEYSPACE)
        .save()
    )

    # Write only alert records to alerts table
    alert_columns = [
        "truck_id", "alert_type", "processed_at", "event_time",
        "latitude", "longitude", "speed", "fuel_level", "engine_temp",
        "driver_id", "anomaly", "theft", "theft_amount",
        "distance_km", "fuel_consumption_rate", "fuel_consumed_trip", "fuel_consumed_l", "fuel_refueled",
        "in_maintenance", "maintenance_type", "maintenance_desc"
    ]
    
    alerts_df = (final_df
        .filter(col("is_alert") == True)
        .select(alert_columns)
    )

    if not alerts_df.rdd.isEmpty():
        (alerts_df.write
            .format("org.apache.spark.sql.cassandra")
            .mode("append")
            .options(table=ALERTS_TABLE, keyspace=CASSANDRA_KEYSPACE)
            .save()
        )
    
    # Data Lake
    final_df_with_date = final_df.withColumn("event_date", to_date(col("event_time")))
    (
      final_df_with_date.write
      .mode("append")
      .partitionBy("event_date")
      .parquet(
          LAKE_PATH
      )
    )

    count = final_df.count()
    alert_count = alerts_df.count() if not alerts_df.rdd.isEmpty() else 0
    
    print(f"[batch #{batch_id:05d}] ✅ Wrote {count} truck(s) to {CASSANDRA_KEYSPACE}.{CASSANDRA_TABLE}, "
          f"{count} to {TRUCK_HISTORY_TABLE}, {alert_count} alerts to {ALERTS_TABLE}  ({time.time()-t0:.2f}s)")
