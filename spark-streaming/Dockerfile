FROM eclipse-temurin:17-jre-jammy

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Install Python and curl
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        python3 python3-pip curl procps && \
    ln -sf /usr/bin/python3 /usr/bin/python && \
    rm -rf /var/lib/apt/lists/*

# Install PySpark (includes spark-submit in PATH)
RUN pip install pyspark==3.5.0

# Pre-download Kafka and PostgreSQL connector JARs
RUN mkdir -p /opt/spark-extra-jars && \
    curl -fL "https://repo1.maven.org/maven2/org/apache/spark/spark-sql-kafka-0-10_2.12/3.5.0/spark-sql-kafka-0-10_2.12-3.5.0.jar" \
         -o /opt/spark-extra-jars/spark-sql-kafka.jar && \
    curl -fL "https://repo1.maven.org/maven2/org/apache/spark/spark-token-provider-kafka-0-10_2.12/3.5.0/spark-token-provider-kafka-0-10_2.12-3.5.0.jar" \
         -o /opt/spark-extra-jars/spark-token-provider-kafka.jar && \
    curl -fL "https://repo1.maven.org/maven2/org/apache/kafka/kafka-clients/3.4.1/kafka-clients-3.4.1.jar" \
         -o /opt/spark-extra-jars/kafka-clients.jar && \
    curl -fL "https://repo1.maven.org/maven2/org/apache/commons/commons-pool2/2.11.1/commons-pool2-2.11.1.jar" \
         -o /opt/spark-extra-jars/commons-pool2.jar && \
    curl -fL "https://repo1.maven.org/maven2/org/postgresql/postgresql/42.7.3/postgresql-42.7.3.jar" \
         -o /opt/spark-extra-jars/postgresql.jar

COPY spark_job.py   /opt/spark-app/spark_job.py
COPY entrypoint.sh  /opt/spark-app/entrypoint.sh
RUN chmod +x /opt/spark-app/entrypoint.sh

ENTRYPOINT ["/opt/spark-app/entrypoint.sh"]
