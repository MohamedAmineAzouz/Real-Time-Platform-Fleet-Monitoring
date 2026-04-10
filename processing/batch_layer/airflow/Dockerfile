FROM apache/airflow:3.1.8

USER root

# Install Java 17 + procps (needed by spark-submit's ps calls)
RUN apt-get update && apt-get install -y --no-install-recommends \
        openjdk-17-jdk-headless \
        procps \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
# Add Spark bin to PATH using Dockerfile ENV (expands correctly unlike Compose)
ENV PATH="${JAVA_HOME}/bin:/opt/spark/bin:/opt/spark/sbin:${PATH}"

USER airflow

RUN pip install --no-cache-dir \
    apache-airflow-providers-apache-spark \
    apache-airflow-providers-standard \
    boto3 \
    google-cloud-storage \
    cassandra-driver