# FROM apache/airflow:3.2.1

# # Install Java + tools
# USER root

# RUN apt-get update && apt-get install -y \
#     openjdk-17-jdk-headless \
#     curl \
#     procps \
#     && rm -rf /var/lib/apt/lists/*

# # Install Spark
# ARG SPARK_VERSION=3.5.1
# ARG HADOOP_VERSION=3

# RUN curl -fSL "https://archive.apache.org/dist/spark/spark-${SPARK_VERSION}/spark-${SPARK_VERSION}-bin-hadoop${HADOOP_VERSION}.tgz" \
#     | tar xzf - -C /opt \
#     && ln -s /opt/spark-${SPARK_VERSION}-bin-hadoop${HADOOP_VERSION} /opt/spark

# # Install Cassandra Connector jars
# RUN mkdir -p /opt/spark/jars && \
#     curl -L -o /opt/spark/jars/spark-cassandra-connector_2.12-3.4.1.jar \
#     https://repo1.maven.org/maven2/com/datastax/spark/spark-cassandra-connector_2.12/3.4.1/spark-cassandra-connector_2.12-3.4.1.jar && \
#     curl -L -o /opt/spark/jars/java-driver-core-4.15.0.jar \
#     https://repo1.maven.org/maven2/com/datastax/oss/java-driver-core/4.15.0/java-driver-core-4.15.0.jar

# # Permissions
# RUN chmod +x /opt/spark/bin/spark-submit

# # Environment
# ENV SPARK_HOME=/opt/spark
# ENV PATH="/opt/spark/bin:${PATH}"

# # Python packages
# USER airflow

# RUN pip install --no-cache-dir \
#     apache-airflow-providers-apache-spark \
#     minio \
#     pyspark==3.5.1


FROM apache/airflow:3.2.1

# Install Java (required for Spark)
USER root
RUN apt-get update && apt-get install -y openjdk-17-jdk-headless curl \
    && rm -rf /var/lib/apt/lists/*

# Install Spark
ARG SPARK_VERSION=3.5.1
ARG HADOOP_VERSION=3
RUN curl -fSL "https://archive.apache.org/dist/spark/spark-${SPARK_VERSION}/spark-${SPARK_VERSION}-bin-hadoop${HADOOP_VERSION}.tgz" \
    | tar xzf - -C /opt \
    && ln -s /opt/spark-${SPARK_VERSION}-bin-hadoop${HADOOP_VERSION} /opt/spark \
    && chmod +x /opt/spark/bin/spark-submit

RUN chmod -R 755 /opt/spark && \
    chown -R airflow:root /opt/spark

# Add Spark to PATH
ENV PATH="/opt/spark/bin:$PATH"
ENV SPARK_HOME=/opt/spark

# Install Python deps
USER airflow
RUN pip install --no-cache-dir apache-airflow-providers-apache-spark minio

