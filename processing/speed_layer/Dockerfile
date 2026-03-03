# Speed Layer — Spark Structured Streaming
# Official Apache Spark image (bitnami/spark was removed from Docker Hub Sep 2025)
FROM spark:3.4.1-scala2.12-java11-python3-ubuntu

USER root

# Install Python deps for init scripts
RUN ln -sf /usr/bin/python3 /usr/bin/python && \
    pip3 install --no-cache-dir minio==7.2.7

WORKDIR /app

COPY storage/  ./storage/
COPY spark_jobs/ ./spark_jobs/
COPY config/ ./config/
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]