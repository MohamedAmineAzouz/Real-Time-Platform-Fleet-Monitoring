# Use Python 3.11 as the base image
FROM python:3.11-slim-bullseye

# Install OpenJDK (Spark requires Java)
RUN apt-get update && apt-get install -y openjdk-11-jre-headless procps curl && rm -rf /var/lib/apt/lists/*

# Set Spark version and install
ENV SPARK_VERSION=3.5.1
RUN curl -O https://archive.apache.org/dist/spark/spark-${SPARK_VERSION}/spark-${SPARK_VERSION}-bin-hadoop3.tgz \
    && tar -xzf spark-${SPARK_VERSION}-bin-hadoop3.tgz -C /opt/ \
    && mv /opt/spark-${SPARK_VERSION}-bin-hadoop3 /opt/spark \
    && rm spark-${SPARK_VERSION}-bin-hadoop3.tgz

ENV SPARK_HOME=/opt/spark
ENV PATH=$PATH:$SPARK_HOME/bin
ENV PYSPARK_PYTHON=python3
