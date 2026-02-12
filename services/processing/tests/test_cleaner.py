"""
Tests for data cleaner
"""
import pytest
from pyspark.sql import functions as F

import sys
sys.path.insert(0, 'src')

from cleaner import DataCleaner, create_cleaner, MISSING_VALUES


def test_cleaner_initialization():
    """Test cleaner can be initialized"""
    cleaner = DataCleaner("air_temperature", quality_threshold=5)
    assert cleaner.product_type == "air_temperature"
    assert cleaner.quality_threshold == 5


def test_handle_missing_values(spark, sample_air_temp_data):
    """Test missing value handling"""
    cleaner = DataCleaner("air_temperature")
    
    # Clean data
    df = cleaner._handle_missing_values(sample_air_temp_data)
    
    # Check that -999 was converted to null
    missing_rows = df.filter(F.col("TT_TU").isNull())
    assert missing_rows.count() == 1


def test_filter_by_quality(spark, sample_air_temp_data):
    """Test quality flag filtering"""
    cleaner = DataCleaner("air_temperature", quality_threshold=5)
    
    # Add timestamp for processing
    df = sample_air_temp_data.withColumn(
        "timestamp",
        F.to_timestamp(F.col("MESS_DATUM"), "yyyyMMddHH")
    )
    
    df = cleaner._filter_by_quality(df)
    
    # Check quality_acceptable column added
    assert "quality_acceptable" in df.columns
    
    # Should have 3 acceptable (QN_9 >= 5 means only row with QN_9=3 passes? 
    # Actually, threshold 5 means >= 5, so QN_9=3 should be False
    low_quality = df.filter(F.col("quality_acceptable") == False).count()
    assert low_quality == 4  # All have QN_9=3 or 2


def test_normalize_units(spark, sample_air_temp_data):
    """Test unit normalization"""
    cleaner = DataCleaner("air_temperature")
    
    # Add timestamp
    df = sample_air_temp_data.withColumn(
        "timestamp",
        F.to_timestamp(F.col("MESS_DATUM"), "yyyyMMddHH")
    )
    
    df = cleaner._normalize_units(df)
    
    # Check time components added
    assert "year" in df.columns
    assert "month" in df.columns
    assert "day" in df.columns
    assert "hour" in df.columns
    
    # Verify values
    row = df.first()
    assert row["year"] == 2023
    assert row["month"] == 1
    assert row["day"] == 1


def test_detect_outliers_temperature(spark, sample_air_temp_data):
    """Test outlier detection for temperature"""
    cleaner = DataCleaner("air_temperature")
    
    # Add timestamp
    df = sample_air_temp_data.withColumn(
        "timestamp",
        F.to_timestamp(F.col("MESS_DATUM"), "yyyyMMddHH")
    )
    
    df = cleaner._detect_outliers(df)
    
    # Check outlier flag added
    assert "has_outlier" in df.columns
    
    # Our sample data should have no outliers (temps are normal)
    outliers = df.filter(F.col("has_outlier") == True).count()
    assert outliers == 0


def test_detect_outliers_with_extreme_value(spark):
    """Test outlier detection with extreme values"""
    # Create data with extreme temperature
    data = [
        (433, "2023010100", 3, 100.0, 50.0),  # Extreme temp
        (433, "2023010101", 3, -70.0, 90.0),  # Extreme temp
    ]
    columns = ["STATIONS_ID", "MESS_DATUM", "QN_9", "TT_TU", "RF_TU"]
    df = spark.createDataFrame(data, columns)
    
    # Add timestamp
    df = df.withColumn(
        "timestamp",
        F.to_timestamp(F.col("MESS_DATUM"), "yyyyMMddHH")
    )
    
    cleaner = DataCleaner("air_temperature")
    df = cleaner._detect_outliers(df)
    
    # Both rows should be flagged as outliers
    outliers = df.filter(F.col("has_outlier") == True).count()
    assert outliers == 2


def test_full_cleaning_pipeline(spark, sample_air_temp_data):
    """Test complete cleaning pipeline"""
    cleaner = DataCleaner("air_temperature", quality_threshold=3)
    
    # Add timestamp
    df = sample_air_temp_data.withColumn(
        "timestamp",
        F.to_timestamp(F.col("MESS_DATUM"), "yyyyMMddHH")
    )
    
    # Run full pipeline
    df = cleaner.clean(df)
    
    # Verify all expected columns exist
    expected_cols = [
        "quality_acceptable",
        "has_outlier",
        "cleaned_at",
        "product_type",
        "year",
        "month"
    ]
    
    for col in expected_cols:
        assert col in df.columns


def test_compute_quality_metrics(spark, sample_air_temp_data):
    """Test quality metrics computation"""
    cleaner = DataCleaner("air_temperature", quality_threshold=3)
    
    # Add timestamp
    df = sample_air_temp_data.withColumn(
        "timestamp",
        F.to_timestamp(F.col("MESS_DATUM"), "yyyyMMddHH")
    )
    
    # Clean and compute metrics
    df = cleaner.clean(df)
    metrics = cleaner.compute_quality_metrics(df)
    
    assert "total_rows" in metrics
    assert "rows_with_outliers" in metrics
    assert "rows_acceptable_quality" in metrics
    assert "missingness" in metrics
    
    assert metrics["total_rows"] == 4


def test_create_cleaner_factory():
    """Test cleaner factory function"""
    cleaner = create_cleaner("precipitation", quality_threshold=7)
    assert isinstance(cleaner, DataCleaner)
    assert cleaner.product_type == "precipitation"
    assert cleaner.quality_threshold == 7
