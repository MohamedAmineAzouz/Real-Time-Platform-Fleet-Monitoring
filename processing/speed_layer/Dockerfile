# Speed Layer — Spark Structured Streaming + Cassandra
FROM spark:3.4.1-scala2.12-java11-python3-ubuntu

USER root

RUN ln -sf /usr/bin/python3 /usr/bin/python && \
    pip3 install --no-cache-dir \
        minio==7.2.7 \
        cassandra-driver==3.29.1

WORKDIR /app

COPY config/   ./config/
COPY storage/  ./storage/
COPY spark_jobs/ ./spark_jobs/
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]