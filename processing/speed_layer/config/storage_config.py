"""
storage_config.py
─────────────────────────────────────────────────────────────────────────────
Single source of truth for storage backend configuration.

TO MIGRATE FROM MINIO → GOOGLE CLOUD STORAGE:
  Change STORAGE_BACKEND = "minio"  →  STORAGE_BACKEND = "gcs"
  Set GCS_BUCKET and GOOGLE_APPLICATION_CREDENTIALS env vars.
  That's it. No other file needs to change.
─────────────────────────────────────────────────────────────────────────────
"""

import os

# ── Toggle here to switch backends ────────────────────────────────────────────
STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "minio")   # "minio" | "gcs"

# ── MinIO settings ────────────────────────────────────────────────────────────
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://minio:9000")
MINIO_ACCESS   = os.getenv("MINIO_ACCESS",   "minioadmin")
MINIO_SECRET   = os.getenv("MINIO_SECRET",   "minioadmin")
MINIO_BUCKET   = os.getenv("MINIO_BUCKET",   "fleet-data")

# ── GCS settings (used only when STORAGE_BACKEND=gcs) ────────────────────────
GCS_BUCKET     = os.getenv("GCS_BUCKET",     "your-gcs-bucket")
GCS_KEY_FILE   = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "/secrets/gcp-key.json")

# ── Derived: bucket name and path prefix ─────────────────────────────────────
if STORAGE_BACKEND == "gcs":
    BUCKET       = GCS_BUCKET
    PATH_PREFIX  = f"gs://{BUCKET}"
else:
    BUCKET       = MINIO_BUCKET
    PATH_PREFIX  = f"s3a://{BUCKET}"

# ── Data Lake paths ───────────────────────────────────────────────────────────
PATHS = {
    "raw_events":    f"{PATH_PREFIX}/raw/truck_events/",
    "alerts":        f"{PATH_PREFIX}/alerts/",
    "aggregates":    f"{PATH_PREFIX}/aggregates/truck_window_stats/",
    "checkpoints":   f"{PATH_PREFIX}/checkpoints/",
}


def get_spark_storage_conf() -> dict:
    """
    Returns Spark hadoop config dict for the active backend.
    Passed directly to SparkConf — no if/else anywhere else in the codebase.
    """
    if STORAGE_BACKEND == "gcs":
        return {
            "spark.hadoop.fs.gs.impl":
                "com.google.cloud.hadoop.fs.gcs.GoogleHadoopFileSystem",
            "spark.hadoop.fs.AbstractFileSystem.gs.impl":
                "com.google.cloud.hadoop.fs.gcs.GoogleHadoopFS",
            "spark.hadoop.google.cloud.auth.service.account.enable": "true",
            "spark.hadoop.google.cloud.auth.service.account.json.keyfile":
                GCS_KEY_FILE,
        }
    else:  # minio
        return {
            "spark.hadoop.fs.s3a.endpoint":            MINIO_ENDPOINT,
            "spark.hadoop.fs.s3a.access.key":          MINIO_ACCESS,
            "spark.hadoop.fs.s3a.secret.key":          MINIO_SECRET,
            "spark.hadoop.fs.s3a.path.style.access":   "true",
            "spark.hadoop.fs.s3a.impl":
                "org.apache.hadoop.fs.s3a.S3AFileSystem",
            "spark.hadoop.fs.s3a.aws.credentials.provider":
                "org.apache.hadoop.fs.s3a.SimpleAWSCredentialsProvider",
            # Performance tuning for MinIO
            "spark.hadoop.fs.s3a.connection.ssl.enabled":       "false",
            "spark.hadoop.fs.s3a.fast.upload":                  "true",
            "spark.hadoop.fs.s3a.multipart.size":               "67108864",  # 64MB
            "spark.hadoop.fs.s3a.block.size":                   "33554432",  # 32MB
        }


def get_spark_packages() -> str:
    """Maven packages to pass to spark-submit --packages."""
    common = (
        "org.apache.spark:spark-sql-kafka-0-10_2.12:3.4.1"
    )
    if STORAGE_BACKEND == "gcs":
        return f"{common},com.google.cloud.bigdataoss:gcs-connector:hadoop3-2.2.17"
    else:
        return (
            f"{common},"
            "org.apache.hadoop:hadoop-aws:3.3.4,"
            "com.amazonaws:aws-java-sdk-bundle:1.12.262"
        )


def print_config():
    print(f"  Backend  : {STORAGE_BACKEND.upper()}")
    print(f"  Bucket   : {BUCKET}")
    for k, v in PATHS.items():
        print(f"  {k:<14}: {v}")