"""
config/spark_config.py
─────────────────────────────────────────────────────────────────────────────
Spark session builder for batch mode.
Loads storage + Cassandra/BigQuery packages based on STORAGE_BACKEND.
─────────────────────────────────────────────────────────────────────────────
"""

import os
from batch_config.batch_config import STORAGE_BACKEND, CASSANDRA_HOST, CASSANDRA_PORT

# ── Maven packages per backend ─────────────────────────────────────────────────
_PACKAGES = {
    "dev": ",".join([
        "com.datastax.spark:spark-cassandra-connector_2.12:3.4.1",
        "org.apache.hadoop:hadoop-aws:3.3.4",
        "com.amazonaws:aws-java-sdk-bundle:1.12.262",
    ]),
    "staging": ",".join([
        "com.google.cloud.spark:spark-bigquery-with-dependencies_2.12:0.34.0",
        "com.google.cloud.bigdataoss:gcs-connector:hadoop3-2.2.17",
    ]),
    "prod": ",".join([
        "com.google.cloud.spark:spark-bigquery-with-dependencies_2.12:0.34.0",
        "com.google.cloud.bigdataoss:gcs-connector:hadoop3-2.2.17",
    ]),
}


def get_packages() -> str:
    return _PACKAGES.get(STORAGE_BACKEND, _PACKAGES["dev"])


def get_spark_conf() -> dict:
    """
    Returns Spark configuration dict for the current backend.
    Applied to SparkSession.builder before .getOrCreate().
    """
    conf = {
        "spark.sql.shuffle.partitions": "32",   # small fleet — don't over-partition
        "spark.sql.adaptive.enabled":   "true",
    }

    if STORAGE_BACKEND == "minio":
        # MinIO (S3-compatible) settings
        minio_endpoint = os.getenv("MINIO_ENDPOINT", "http://minio:9000")
        minio_access   = os.getenv("MINIO_ACCESS",   "minioadmin")
        minio_secret   = os.getenv("MINIO_SECRET",   "minioadmin")
        conf.update({
            "spark.hadoop.fs.s3a.endpoint":               minio_endpoint,
            "spark.hadoop.fs.s3a.access.key":             minio_access,
            "spark.hadoop.fs.s3a.secret.key":             minio_secret,
            "spark.hadoop.fs.s3a.path.style.access":      "true",
            "spark.hadoop.fs.s3a.impl":                   "org.apache.hadoop.fs.s3a.S3AFileSystem",
            "spark.hadoop.fs.s3a.aws.credentials.provider": "org.apache.hadoop.fs.s3a.SimpleAWSCredentialsProvider",
            "spark.hadoop.fs.s3a.connection.ssl.enabled":       "false",
            "spark.hadoop.fs.s3a.fast.upload":                  "true",
            "spark.hadoop.fs.s3a.multipart.size":               "67108864",  # 64MB
            "spark.hadoop.fs.s3a.block.size":                   "33554432",  # 32MB
            # Cassandra connector
            "spark.cassandra.connection.host":             CASSANDRA_HOST,
            "spark.cassandra.connection.port":             CASSANDRA_PORT,
            "spark.cassandra.output.consistency.level":    "LOCAL_ONE",
            "spark.cassandra.output.concurrent.writes":      "32",
            "spark.cassandra.output.batch.grouping.key":     "partition",
            "spark.cassandra.output.batch.size.rows":        "1000",
            "spark.cassandra.connection.keepAliveMS":        "60000",
            "spark.cassandra.output.batch.size.bytes":    "1024",
        })

    else:
        # GCS settings
        gcs_credentials = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
        conf.update({
            "spark.hadoop.fs.gs.impl":                        "com.google.cloud.hadoop.fs.gcs.GoogleHadoopFileSystem",
            "spark.hadoop.google.cloud.auth.service.account.enable": "true",
            "spark.hadoop.google.cloud.auth.service.account.json.keyfile": gcs_credentials,
        })

    return conf