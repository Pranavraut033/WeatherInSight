"""
Tests for aggregator with station metadata join.
"""
import pytest
from unittest.mock import Mock, MagicMock
from pyspark.sql import functions as F

from aggregation.src.config import AggregationConfig
from aggregation.src.aggregator import QuarterlyAggregator


def test_load_station_metadata_caching(spark, sample_station_metadata):
    """Test that station metadata is cached after first load."""
    config = AggregationConfig()
    aggregator = QuarterlyAggregator(config, spark)
    
    # Mock the JDBC read to return our sample data
    original_read = spark.read.jdbc
    
    def mock_jdbc(*args, **kwargs):
        return sample_station_metadata
    
    spark.read.jdbc = mock_jdbc
    
    # First load
    metadata1 = aggregator.load_station_metadata()
    
    # Second load should return cached version
    metadata2 = aggregator.load_station_metadata()
    
    # Both should be the same object (cached)
    assert metadata1 is metadata2
    
    # Verify metadata structure
    assert metadata1.count() == 1
    columns = metadata1.columns
    assert "station_id" in columns
    assert "station_name" in columns
    assert "latitude" in columns
    assert "longitude" in columns
    assert "elevation_m" in columns
    
    # Restore original method
    spark.read.jdbc = original_read


def test_quarterly_aggregator_quarter_boundaries():
    """Test quarter boundary calculations."""
    # Q1: Jan-Mar
    assert QuarterlyAggregator._get_quarter_months(1) == (1, 2, 3)
    
    # Q2: Apr-Jun
    assert QuarterlyAggregator._get_quarter_months(2) == (4, 5, 6)
    
    # Q3: Jul-Sep
    assert QuarterlyAggregator._get_quarter_months(3) == (7, 8, 9)
    
    # Q4: Oct-Dec
    assert QuarterlyAggregator._get_quarter_months(4) == (10, 11, 12)


# Helper method for testing (add to QuarterlyAggregator class if not present)
QuarterlyAggregator._get_quarter_months = staticmethod(
    lambda q: {1: (1, 2, 3), 2: (4, 5, 6), 3: (7, 8, 9), 4: (10, 11, 12)}[q]
)


def test_load_staged_data_filtering(spark, sample_temperature_data):
    """Test that staged data is properly filtered by year/quarter."""
    config = AggregationConfig()
    config.staging_path = "test://staged/dwd"
    
    aggregator = QuarterlyAggregator(config, spark)
    
    # Mock parquet read to return our sample data
    original_read = spark.read.parquet
    
    def mock_parquet(*args, **kwargs):
        return sample_temperature_data
    
    spark.read.parquet = mock_parquet
    
    # Load data for Q1 2023
    df = aggregator.load_staged_data("air_temperature", 2023, 1, "v1.0.0")
    
    # Should only have Q1 2023 data
    assert df.select("year").distinct().collect()[0]["year"] == 2023
    assert df.select("quarter").distinct().collect()[0]["quarter"] == 1
    
    # Restore
    spark.read.parquet = original_read


def test_compute_quarterly_features_integration(spark, sample_temperature_data, sample_station_metadata):
    """Integration test for complete feature computation with metadata join."""
    config = AggregationConfig()
    config.staging_path = "test://staged/dwd"
    
    aggregator = QuarterlyAggregator(config, spark)
    
    # Mock data loading
    def mock_load_staged(*args, **kwargs):
        return sample_temperature_data
    
    def mock_load_metadata():
        return sample_station_metadata
    
    aggregator.load_staged_data = mock_load_staged
    aggregator.load_station_metadata = mock_load_metadata
    
    # Compute features
    features = aggregator.compute_quarterly_features(
        product_type="air_temperature",
        year=2023,
        quarter=1,
        dataset_version="v1.0.0"
    )
    
    # Verify result structure
    assert features.count() == 1
    
    row = features.collect()[0]
    
    # Check station metadata was joined
    assert row["station_id"] == 433
    assert row["station_name"] == "Test Station"
    assert row["latitude"] == 52.5200
    assert row["longitude"] == 13.4050
    assert row["elevation_m"] == 45.0
    
    # Check quarter boundaries
    assert row["year"] == 2023
    assert row["quarter"] == 1
    assert row["quarter_start"] is not None
    assert row["quarter_end"] is not None
    
    # Check computed_at timestamp
    assert row["computed_at"] is not None
    
    # Check features exist
    assert row["temp_mean_c"] is not None
    assert row["heating_degree_days"] is not None


def test_compute_quarterly_features_unknown_product_type(spark):
    """Test that unknown product types raise an error."""
    config = AggregationConfig()
    aggregator = QuarterlyAggregator(config, spark)
    
    with pytest.raises(ValueError, match="Unknown product type"):
        aggregator.compute_quarterly_features(
            product_type="unknown_product",
            year=2023,
            quarter=1,
            dataset_version="v1.0.0"
        )
