import os

# ----------------------------
# Kafka
# ----------------------------
KAFKA_BROKER = os.getenv("KAFKA_BROKER", "kafka:9092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "truck-gps")

# ----------------------------
# Cassandra
# ----------------------------
CASSANDRA_HOST = os.getenv("CASSANDRA_HOST","cassandra")
CASSANDRA_PORT = os.getenv("CASSANDRA_PORT", "9042")
CASSANDRA_KEYSPACE = os.getenv("CASSANDRA_KEYSPACE","fleet_1")
CASSANDRA_TABLE = "truck_latest"
TRUCK_HISTORY_TABLE = "truck_history"
ALERTS_TABLE = "alerts"

# ----------------------------
# Thresholds
# ----------------------------
SPEED_THRESHOLD = 120.0
TEMP_THRESHOLD = 100.0
FUEL_LOW = 20.0


# ----------------------------
# Storage Backend
# minio | gcs
# ----------------------------
STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "minio").lower()
LAKE_BUCKET = os.getenv("LAKE_BUCKET", "fleet-data")
LAKE_PREFIX = os.getenv("LAKE_PREFIX","silver/truck_history")

# MinIO
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT","http://minio:9000")
MINIO_ROOT_USER = os.getenv("MINIO_ROOT_USER", "minioadmin")
MINIO_ROOT_PASSWORD = os.getenv("MINIO_ROOT_PASSWORD","minioadmin")

# GCS
GCS_KEYFILE = os.getenv("GCS_KEYFILE","/keys/gcs.json")