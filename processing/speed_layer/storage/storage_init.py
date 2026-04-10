"""
storage_init.py
─────────────────────────────────────────────────────────────────────────────
Initializes ALL storage backends before Spark starts:
  1. MinIO  — create bucket + folder skeleton
     (or GCS — verify bucket exists)
  2. Cassandra — create keyspace + tables

Safe to re-run on every container restart (all ops are idempotent).
─────────────────────────────────────────────────────────────────────────────
"""

import io
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from config.storage_config import (
    STORAGE_BACKEND,
    MINIO_BUCKET, MINIO_ENDPOINT, MINIO_ACCESS, MINIO_SECRET,
    GCS_BUCKET, GCS_KEY_FILE,
    PATHS,
)

FOLDERS = [
    "raw/truck_events/",
    "alerts/",
    "aggregates/truck_window_stats/",
    "checkpoints/parquet_raw/",
    "checkpoints/parquet_alerts/",
    "checkpoints/aggregates/",
    "checkpoints/cassandra_latest/",
    "checkpoints/cassandra_history/",
    "checkpoints/cassandra_alerts/",
]


# ── MinIO ──────────────────────────────────────────────────────────────────────

def _minio_client():
    from minio import Minio
    endpoint = MINIO_ENDPOINT.replace("http://", "").replace("https://", "")
    return Minio(endpoint, access_key=MINIO_ACCESS, secret_key=MINIO_SECRET, secure=False)


def _wait_for_minio(retries=30, delay=4):
    client = _minio_client()
    for attempt in range(1, retries + 1):
        try:
            client.list_buckets()
            print("✅ MinIO is ready")
            return client
        except Exception as exc:
            print(f"⏳ MinIO not ready ({attempt}/{retries}): {exc}")
            time.sleep(delay)
    raise RuntimeError("❌ MinIO did not become ready in time")


def _init_minio():
    from minio.error import S3Error
    client = _wait_for_minio()

    if not client.bucket_exists(MINIO_BUCKET):
        client.make_bucket(MINIO_BUCKET)
        print(f"🪣  Created bucket : {MINIO_BUCKET}")
    else:
        print(f"🪣  Bucket exists  : {MINIO_BUCKET}")

    for folder in FOLDERS:
        try:
            client.put_object(MINIO_BUCKET, folder + ".keep", io.BytesIO(b""), length=0)
            print(f"   📁 {folder}")
        except S3Error as exc:
            print(f"   ⚠️  {folder}: {exc}")

    console_url = MINIO_ENDPOINT.replace(":9000", ":9001")
    print(f"✅ MinIO ready — {console_url}  (bucket: {MINIO_BUCKET})")


# ── GCS ────────────────────────────────────────────────────────────────────────

def _init_gcs():
    try:
        from google.cloud import storage as gcs
    except ImportError:
        raise RuntimeError(
            "google-cloud-storage is not installed. "
            "Add it to requirements.txt when using STORAGE_BACKEND=gcs."
        )
 
    client = gcs.Client()
    bucket = client.bucket(GCS_BUCKET)
 
    if not bucket.exists():
        raise RuntimeError(
            f"❌ GCS bucket '{GCS_BUCKET}' does not exist. "
            "Create it in the GCP Console first."
        )
    print(f"🪣  GCS bucket verified : gs://{GCS_BUCKET}")


    for folder in FOLDERS:
        blob = bucket.blob(folder + ".keep")
        if not blob.exists():
            blob.upload_from_string(b"")
            print(f"   📁 {folder}")
        else:
            print(f"   ✓  {folder} (exists)")
 
    print(f"✅ GCS ready — gs://{GCS_BUCKET}")
 



# ── Public entry point ─────────────────────────────────────────────────────────

def init_storage():
    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  Storage Initialization")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    # Step 1: Object store (MinIO or GCS)
    print(f"\n[1/2] Object Store: {STORAGE_BACKEND.upper()}")
    if STORAGE_BACKEND == "gcs":
        _init_gcs()
    else:
        _init_minio()

    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  All storage backends ready")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")


if __name__ == "__main__":
    init_storage()