# MinIO → Google Cloud Storage Migration

## TL;DR — 3 steps, zero code changes

---

### Step 1 — Copy your data (once)

```bash
# Using GCS Transfer Service (recommended for large data)
# GCP Console → Storage Transfer → from S3-compatible source

# Or with gsutil for smaller datasets
gsutil -m rsync -r  s3://fleet-data/  gs://your-gcs-bucket/
```

---

### Step 2 — Flip one env var in docker-compose.yml

```yaml
# BEFORE
STORAGE_BACKEND: minio

# AFTER
STORAGE_BACKEND: gcs
GCS_BUCKET:      your-gcs-bucket
# GOOGLE_APPLICATION_CREDENTIALS: /secrets/gcp-key.json

# Uncomment the volumes section in the service:
# volumes:
#   - ./gcp-key.json:/secrets/gcp-key.json:ro
```

---

### Step 3 — Reset checkpoints (required)

MinIO and GCS checkpoints are not compatible. Delete them and let Spark rebuild:

```bash
gsutil -m rm -r gs://your-gcs-bucket/checkpoints/
```

Then restart: `docker compose up --build`

---

## What changes vs what stays the same

| | MinIO | GCS |
|---|---|---|
| `STORAGE_BACKEND` | `minio` | `gcs` |
| Path prefix | `s3a://` | `gs://` |
| Auth | access key + secret | service-account JSON |
| Spark package | `hadoop-aws` + `aws-java-sdk` | `gcs-connector` |
| **Streaming logic** | ✅ unchanged | ✅ unchanged |
| **Anomaly detection** | ✅ unchanged | ✅ unchanged |
| **Parquet schema** | ✅ unchanged | ✅ unchanged |
| **Kafka config** | ✅ unchanged | ✅ unchanged |

All logic lives in `streaming_processor.py` — untouched.  
All backend switching lives in `storage/storage_config.py`.