#!/bin/bash
set -e

# Build a comma-separated list of all pre-downloaded JARs
EXTRA_JARS=$(ls /opt/spark-extra-jars/*.jar | paste -sd ',' -)

exec spark-submit \
  --jars          "$EXTRA_JARS" \
  --master        "local[2]" \
  --conf          "spark.sql.shuffle.partitions=4" \
  --conf          "spark.streaming.stopGracefullyOnShutdown=true" \
  /opt/spark-app/spark_job.py "$@"
