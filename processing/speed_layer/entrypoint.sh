#!/bin/bash
set -e

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Fleet Speed Layer"
echo "  Storage : ${STORAGE_BACKEND:-minio}"
echo "  Cassandra: ${CASSANDRA_HOST:-cassandra}:${CASSANDRA_PORT:-9042}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Step 1: Initialize all storage backends (MinIO/GCS + Cassandra schema)
python3 /app/storage/storage_init.py

# Step 2: Resolve Maven packages (storage backend + Cassandra connector)
PACKAGES=$(python3 -c "
import sys; sys.path.insert(0, '/app')
from config.storage_config   import get_spark_packages
from config.cassandra_config import get_cassandra_package
print(get_spark_packages() + ',' + get_cassandra_package())
")
echo "▶ Spark packages: $PACKAGES"

# Step 3: Launch Spark Structured Streaming
exec /opt/spark/bin/spark-submit \
  --master "local[*]" \
  --packages "$PACKAGES" \
  /app/spark_jobs/streaming_processor.py