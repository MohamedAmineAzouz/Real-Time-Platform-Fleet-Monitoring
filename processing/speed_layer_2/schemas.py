from pyspark.sql.types import *

def get_truck_schema():

    return StructType([
        StructField("truck_id", IntegerType()),
        StructField("latitude", DoubleType()),
        StructField("longitude", DoubleType()),
        StructField("speed", DoubleType()),
        StructField("fuel_level", DoubleType()),
        StructField("engine_temp", DoubleType()),
        StructField("driver_id", StringType()),
        StructField("start_city", StringType()),
        StructField("end_city", StringType()),
        StructField("odometer_km", DoubleType()),
        StructField("refueling", BooleanType()),
        StructField("refuel_city", StringType()),
        StructField("anomaly", StringType()),
        StructField("theft", BooleanType()),
        StructField("theft_amount", DoubleType()),
        StructField("fuel_consumed_trip", DoubleType()),
        StructField("fuel_consumed_l", DoubleType()),
        StructField("fuel_refueled", DoubleType()),
        StructField("distance_km", DoubleType()),
        StructField("timestamp", StringType()),
        StructField("in_maintenance", BooleanType()),
        StructField("maintenance_type", StringType()),
        StructField("maintenance_desc", StringType()),
    ])