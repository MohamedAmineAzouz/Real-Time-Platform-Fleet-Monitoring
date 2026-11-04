FROM apache/airflow:3.2.1-python3.11

USER root
RUN apt-get update && apt-get install -y openjdk-17-jdk-headless curl \
    && rm -rf /var/lib/apt/lists/*

ARG SPARK_VERSION=3.5.1
ARG HADOOP_VERSION=3
RUN curl -fSL "https://archive.apache.org/dist/spark/spark-${SPARK_VERSION}/spark-${SPARK_VERSION}-bin-hadoop${HADOOP_VERSION}.tgz" \
    | tar xzf - -C /opt \
    && ln -s /opt/spark-${SPARK_VERSION}-bin-hadoop${HADOOP_VERSION} /opt/spark \
    && chmod +x /opt/spark/bin/spark-submit

RUN chmod -R 755 /opt/spark && \
    chown -R airflow:root /opt/spark

ENV PATH="/opt/spark/bin:$PATH"
ENV SPARK_HOME=/opt/spark

USER airflow
RUN pip install --no-cache-dir apache-airflow-providers-apache-spark minio
