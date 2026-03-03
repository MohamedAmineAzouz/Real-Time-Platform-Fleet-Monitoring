#!/bin/bash
set -e

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Fleet Speed Layer"
echo "  Backend: ${STORAGE_BACKEND:-minio}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Step 1: Init MinIO bucket (skipped automatically if STORAGE_BACKEND=gcs)
python3 /app/storage/minio_init.py

# Step 2: Resolve Maven packages from storage_config
PACKAGES=$(python3 -c "
import sys; sys.path.insert(0,'/app')
from config.storage_config import get_spark_packages
print(get_spark_packages())
")
echo "▶ Spark packages: $PACKAGES"

# Step 3: Launch Spark Structured Streaming
exec /opt/spark/bin/spark-submit \
  --master "local[*]" \
  --packages "$PACKAGES" \
  --conf "spark.sql.streaming.checkpointLocation=placeholder" \
  /app/spark_jobs/streaming_processor.py