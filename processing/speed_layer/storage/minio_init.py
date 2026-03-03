"""
minio_init.py
Creates the fleet-data bucket and folder skeleton on first run.
Only runs when STORAGE_BACKEND=minio (skipped for GCS).
"""

import os
import io
import sys
import time
from minio import Minio
from minio.error import S3Error

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config.storage_config import (
    STORAGE_BACKEND, MINIO_BUCKET, MINIO_ENDPOINT, MINIO_ACCESS, MINIO_SECRET
)

FOLDERS = [
    "raw/truck_events/",
    "alerts/",
    "aggregates/truck_window_stats/",
    "checkpoints/parquet_raw/",
    "checkpoints/parquet_alerts/",
    "checkpoints/aggregates/",
]


def _client() -> Minio:
    # strip http:// — minio-py expects host:port only
    endpoint = MINIO_ENDPOINT.replace("http://", "").replace("https://", "")
    return Minio(endpoint, access_key=MINIO_ACCESS, secret_key=MINIO_SECRET, secure=False)


def wait_for_minio(retries: int = 30, delay: int = 4):
    client = _client()
    for attempt in range(1, retries + 1):
        try:
            client.list_buckets()
            print("✅ MinIO is ready")
            return client
        except Exception as exc:
            print(f"⏳ MinIO not ready ({attempt}/{retries}): {exc}")
            time.sleep(delay)
    raise RuntimeError("❌ MinIO did not become ready in time")


def init_minio():
    if STORAGE_BACKEND != "minio":
        print(f"ℹ️  STORAGE_BACKEND={STORAGE_BACKEND}, skipping MinIO init")
        return

    client = wait_for_minio()

    # Create bucket
    if not client.bucket_exists(MINIO_BUCKET):
        client.make_bucket(MINIO_BUCKET)
        print(f"🪣  Created bucket: {MINIO_BUCKET}")
    else:
        print(f"🪣  Bucket exists : {MINIO_BUCKET}")

    # Create folder placeholders so the UI shows the structure
    for folder in FOLDERS:
        key = folder + ".keep"
        try:
            client.put_object(MINIO_BUCKET, key, io.BytesIO(b""), length=0)
            print(f"   📁 {folder}")
        except S3Error as exc:
            print(f"   ⚠️  {folder}: {exc}")

    print(f"\n✅ MinIO ready — browse at {MINIO_ENDPOINT.replace('9000','9001')}")


if __name__ == "__main__":
    init_minio()