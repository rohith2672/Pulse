import os
from pathlib import Path

import pytest
from pyspark.sql import SparkSession

SPARK_APP_DIR = str(Path(__file__).resolve().parents[1])


@pytest.fixture(scope="session")
def spark():
    # Python UDF workers run in separate processes and must be able to import
    # the app modules (validation, anomaly, spark_job).
    os.environ["PYTHONPATH"] = os.pathsep.join(
        p for p in (SPARK_APP_DIR, os.environ.get("PYTHONPATH")) if p
    )
    session = (
        SparkSession.builder
        .master("local[2]")
        .appName("pulse-tests")
        .config("spark.sql.shuffle.partitions", "2")
        .config("spark.ui.enabled", "false")
        .config("spark.sql.session.timeZone", "UTC")
        .getOrCreate()
    )
    session.sparkContext.setLogLevel("ERROR")
    yield session
    session.stop()
