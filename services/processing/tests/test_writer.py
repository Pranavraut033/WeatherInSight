"""
Tests for staging writer
"""
import pytest
from pyspark.sql import functions as F

import sys
sys.path.insert(0, 'src')

from writer import StagingWriter, create_writer


def test_writer_initialization():
    """Test writer can be initialized"""
    writer = StagingWriter(
        "s3a://test-bucket/staging",
        "air_temperature",
        "v1.0.0"
    )
    
    assert writer.product_type == "air_temperature"
    assert writer.dataset_version == "v1.0.0"
    assert writer.output_path == "s3a://test-bucket/staging/air_temperature/version=v1.0.0"


def test_write_parquet(spark, sample_air_temp_data, tmp_path):
    """Test writing to parquet"""
    # Add required columns
    df = sample_air_temp_data.withColumn(
        "timestamp",
        F.to_timestamp(F.col("MESS_DATUM"), "yyyyMMddHH")
    )
    df = df.withColumn("year", F.year("timestamp"))
    df = df.withColumn("month", F.month("timestamp"))
    
    # Write
    output_path = str(tmp_path / "staging/air_temperature/version=v1.0.0")
    writer = StagingWriter(
        str(tmp_path / "staging"),
        "air_temperature",
        "v1.0.0"
    )
    
    stats = writer.write(df, partition_cols=["year", "month"], mode="overwrite")
    
    assert stats["rows_written"] == 4
    assert stats["dataset_version"] == "v1.0.0"
    assert "written_at" in stats


def test_write_with_compaction(spark, sample_air_temp_data, tmp_path):
    """Test writing with compaction"""
    # Add required columns
    df = sample_air_temp_data.withColumn(
        "timestamp",
        F.to_timestamp(F.col("MESS_DATUM"), "yyyyMMddHH")
    )
    df = df.withColumn("year", F.year("timestamp"))
    df = df.withColumn("month", F.month("timestamp"))
    
    # Write with compaction
    writer = StagingWriter(
        str(tmp_path / "staging"),
        "air_temperature",
        "v1.0.0"
    )
    
    stats = writer.write_with_compaction(
        df, 
        partition_cols=["year", "month"],
        target_file_size_mb=1
    )
    
    assert stats["rows_written"] == 4


def test_write_by_station(spark, sample_air_temp_data, tmp_path):
    """Test writing partitioned by station"""
    # Add required columns
    df = sample_air_temp_data.withColumn(
        "timestamp",
        F.to_timestamp(F.col("MESS_DATUM"), "yyyyMMddHH")
    )
    df = df.withColumn("year", F.year("timestamp"))
    
    writer = StagingWriter(
        str(tmp_path / "staging"),
        "air_temperature",
        "v1.0.0"
    )
    
    stats = writer.write_by_station(df, mode="overwrite")
    
    assert stats["rows_written"] == 4
    assert stats["partition_cols"] == ["STATIONS_ID", "year"]


def test_validate_output(spark, sample_air_temp_data, tmp_path):
    """Test output validation"""
    # Prepare and write data
    df = sample_air_temp_data.withColumn(
        "timestamp",
        F.to_timestamp(F.col("MESS_DATUM"), "yyyyMMddHH")
    )
    df = df.withColumn("year", F.year("timestamp"))
    df = df.withColumn("month", F.month("timestamp"))
    
    writer = StagingWriter(
        str(tmp_path / "staging"),
        "air_temperature",
        "v1.0.0"
    )
    
    writer.write(df, partition_cols=["year", "month"], mode="overwrite")
    
    # Validate
    metrics = writer.validate_output()
    
    assert metrics["total_rows"] == 4
    assert "partitions" in metrics
    assert "distinct_stations" in metrics
    assert metrics["distinct_stations"] == 1


def test_create_writer_factory():
    """Test writer factory function"""
    writer = create_writer(
        "s3a://bucket/staging",
        "precipitation",
        "v2.0.0"
    )
    
    assert isinstance(writer, StagingWriter)
    assert writer.product_type == "precipitation"
    assert writer.dataset_version == "v2.0.0"
