import time

from pyspark.sql.functions import col, lit, row_number, to_date
from pyspark.sql.window import Window

from config import *
from storage_backend import get_storage_uri


LAKE_PATH = get_storage_uri()


def write_to_cassandra(batch_df, batch_id: int):
    """
    Write one latest row per truck to truck_latest, and keep the full micro-batch
    for truck_history and alerts.
    """
    t0 = time.time()

    if batch_df.rdd.isEmpty():
        return

    columns = [
        "truck_id", "processed_at", "event_time",
        "latitude", "longitude", "speed", "fuel_level", "engine_temp",
        "driver_id", "start_city", "end_city", "odometer_km",
        "refueling", "refuel_city", "anomaly", "theft", "theft_amount",
        "distance_km", "fuel_used", "fuel_consumption_rate", "high_consumption",
        "fuel_consumed_trip", "fuel_consumed_l", "fuel_refueled",
        "alert_type", "is_alert",
        "in_maintenance", "maintenance_type", "maintenance_desc",
    ]

    base_df = (
        batch_df
        .withColumn("fuel_used", lit(0.0))
        .withColumn("fuel_consumption_rate", lit(0.0))
        .withColumn("high_consumption", lit(False))
    )

    latest_window = Window.partitionBy("truck_id").orderBy(
        col("event_time").desc(),
        col("processed_at").desc(),
    )

    latest_df = (
        base_df
        .withColumn("row_num", row_number().over(latest_window))
        .filter(col("row_num") == 1)
        .drop("row_num")
        .select(columns)
    )
    history_df = base_df.select(columns)

    # 1. Update truck_latest (Live Map)
    (latest_df.write
        .format("org.apache.spark.sql.cassandra")
        .mode("append")
        .options(table=CASSANDRA_TABLE, keyspace=CASSANDRA_KEYSPACE)
        .save()
    )

    # 2. Update truck_history (24h lines)
    (history_df.write
        .format("org.apache.spark.sql.cassandra")
        .mode("append")
        .options(table=TRUCK_HISTORY_TABLE, keyspace=CASSANDRA_KEYSPACE)
        .save()
    )

    # 3. Update alerts
    alert_columns = [
        "truck_id", "alert_type", "processed_at", "event_time",
        "latitude", "longitude", "speed", "fuel_level", "engine_temp",
        "driver_id", "anomaly", "theft", "theft_amount",
        "distance_km", "fuel_consumption_rate", "fuel_consumed_trip", "fuel_consumed_l", "fuel_refueled",
        "in_maintenance", "maintenance_type", "maintenance_desc",
    ]

    alerts_df = (
        history_df
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

    print(f"[Real-time batch #{batch_id:05d}] Cassandra Updated ({time.time() - t0:.2f}s)")
