"""
Tests for feature calculator functions.
"""
import pytest
from pyspark.sql import functions as F

from aggregation.src.feature_calculators import (
    calculate_temperature_features,
    calculate_precipitation_features,
    calculate_wind_features,
    calculate_pressure_features,
    calculate_humidity_features,
)


def test_calculate_temperature_features_basic(sample_temperature_data):
    """Test basic temperature feature calculation."""
    features = calculate_temperature_features(sample_temperature_data)
    
    # Should have one row per station/year/quarter
    assert features.count() == 1
    
    row = features.collect()[0]
    
    # Check basic statistics exist and are reasonable
    assert row["station_id"] == 433
    assert row["year"] == 2023
    assert row["quarter"] == 1
    assert row["temp_mean_c"] is not None
    assert row["temp_median_c"] is not None
    assert row["temp_min_c"] < row["temp_max_c"]
    assert row["temp_stddev_c"] > 0
    
    # Check observation counts
    assert row["count_observations"] > 0
    assert row["missingness_ratio"] >= 0


def test_calculate_temperature_features_degree_days(sample_temperature_data):
    """Test heating and cooling degree days calculation."""
    features = calculate_temperature_features(sample_temperature_data)
    
    row = features.collect()[0]
    
    # Should have degree days calculated
    assert row["heating_degree_days"] is not None
    assert row["cooling_degree_days"] is not None
    
    # For winter quarter, expect more heating than cooling
    assert row["heating_degree_days"] >= 0
    assert row["cooling_degree_days"] >= 0


def test_calculate_temperature_features_frost_hours(sample_temperature_data):
    """Test frost hours calculation."""
    features = calculate_temperature_features(sample_temperature_data)
    
    row = features.collect()[0]
    
    # Should have frost hours (temp < 0°C)
    assert row["frost_hours"] is not None
    assert row["frost_hours"] >= 0


def test_calculate_precipitation_features_basic(sample_precipitation_data):
    """Test basic precipitation feature calculation."""
    features = calculate_precipitation_features(sample_precipitation_data)
    
    assert features.count() == 1
    
    row = features.collect()[0]
    
    # Check basic statistics
    assert row["station_id"] == 433
    assert row["precip_total_mm"] > 0
    assert row["precip_mean_mm"] >= 0
    assert row["precip_median_mm"] >= 0
    assert row["precip_max_mm"] >= row["precip_mean_mm"]


def test_calculate_precipitation_features_wet_dry_spells(sample_precipitation_data):
    """Test wet and dry spell calculation."""
    features = calculate_precipitation_features(sample_precipitation_data)
    
    row = features.collect()[0]
    
    # Should have wet and dry hours
    assert row["wet_hours"] > 0
    assert row["dry_hours"] > 0
    assert row["wet_hours"] + row["dry_hours"] == row["count_observations"]
    
    # Should have max spell lengths
    assert row["max_wet_spell_hours"] is not None
    assert row["max_dry_spell_hours"] is not None
    assert row["max_wet_spell_hours"] > 0
    assert row["max_dry_spell_hours"] > 0


def test_calculate_precipitation_features_heavy_precip(sample_precipitation_data):
    """Test heavy precipitation hours."""
    features = calculate_precipitation_features(sample_precipitation_data)
    
    row = features.collect()[0]
    
    assert row["heavy_precip_hours"] is not None
    assert row["heavy_precip_hours"] >= 0


def test_calculate_wind_features_basic(sample_wind_data):
    """Test basic wind feature calculation."""
    features = calculate_wind_features(sample_wind_data)
    
    assert features.count() == 1
    
    row = features.collect()[0]
    
    # Check wind speed statistics
    assert row["wind_speed_mean_mps"] > 0
    assert row["wind_speed_median_mps"] > 0
    assert row["wind_speed_min_mps"] < row["wind_speed_max_mps"]
    assert row["wind_speed_stddev_mps"] >= 0


def test_calculate_wind_features_direction(sample_wind_data):
    """Test wind direction features."""
    features = calculate_wind_features(sample_wind_data)
    
    row = features.collect()[0]
    
    # Should have prevailing direction (0-360)
    assert row["prevailing_direction"] is not None
    assert 0 <= row["prevailing_direction"] < 360
    
    # Should have direction variability
    assert row["direction_variability"] is not None
    assert row["direction_variability"] >= 0


def test_calculate_wind_features_gust_calm(sample_wind_data):
    """Test gust and calm hours."""
    features = calculate_wind_features(sample_wind_data)
    
    row = features.collect()[0]
    
    assert row["gust_hours"] is not None
    assert row["calm_hours"] is not None
    assert row["gust_hours"] >= 0
    assert row["calm_hours"] >= 0


def test_calculate_pressure_features_basic(sample_pressure_data):
    """Test basic pressure feature calculation."""
    features = calculate_pressure_features(sample_pressure_data)
    
    assert features.count() == 1
    
    row = features.collect()[0]
    
    # Check pressure statistics (in Pa)
    assert row["pressure_mean_pa"] > 100000  # Around 1000 hPa
    assert row["pressure_median_pa"] > 100000
    assert row["pressure_min_pa"] < row["pressure_max_pa"]
    assert row["pressure_stddev_pa"] > 0


def test_calculate_pressure_features_range(sample_pressure_data):
    """Test pressure range calculation."""
    features = calculate_pressure_features(sample_pressure_data)
    
    row = features.collect()[0]
    
    assert row["pressure_range_pa"] is not None
    assert row["pressure_range_pa"] > 0
    assert row["pressure_range_pa"] == row["pressure_max_pa"] - row["pressure_min_pa"]


def test_calculate_pressure_features_high_low_hours(sample_pressure_data):
    """Test high and low pressure hours."""
    features = calculate_pressure_features(sample_pressure_data)
    
    row = features.collect()[0]
    
    assert row["high_pressure_hours"] is not None
    assert row["low_pressure_hours"] is not None
    assert row["high_pressure_hours"] >= 0
    assert row["low_pressure_hours"] >= 0


def test_calculate_humidity_features_basic(sample_humidity_data):
    """Test basic humidity feature calculation."""
    features = calculate_humidity_features(sample_humidity_data)
    
    assert features.count() == 1
    
    row = features.collect()[0]
    
    # Check humidity statistics
    assert row["humidity_mean_pct"] > 0
    assert row["humidity_median_pct"] > 0
    assert row["humidity_min_pct"] < row["humidity_max_pct"]
    assert row["humidity_stddev_pct"] >= 0
    
    # Humidity should be in valid range (0-100%)
    assert 0 <= row["humidity_min_pct"] <= 100
    assert 0 <= row["humidity_max_pct"] <= 100


def test_calculate_humidity_features_high_low_hours(sample_humidity_data):
    """Test high and low humidity hours."""
    features = calculate_humidity_features(sample_humidity_data)
    
    row = features.collect()[0]
    
    assert row["high_humidity_hours"] is not None
    assert row["low_humidity_hours"] is not None
    assert row["high_humidity_hours"] >= 0
    assert row["low_humidity_hours"] >= 0


def test_feature_calculators_handle_nulls(spark):
    """Test that feature calculators handle null values correctly."""
    # Create data with some nulls
    data = [
        {
            "STATIONS_ID": 433,
            "year": 2023,
            "quarter": 1,
            "month": 1,
            "day": 1,
            "hour": h,
            "TT_TU": 10.0 if h % 2 == 0 else None,
            "RF_TU": 75.0,
            "quality_acceptable": True,
            "dataset_version": "v1.0.0"
        }
        for h in range(24)
    ]
    
    df = spark.createDataFrame(data)
    features = calculate_temperature_features(df)
    
    row = features.collect()[0]
    
    # Should calculate statistics only on non-null values
    assert row["temp_mean_c"] == 10.0
    assert row["count_observations"] == 12  # Half are non-null
    assert row["count_missing"] == 12


def test_feature_calculators_quality_filter(spark, sample_temperature_data):
    """Test that feature calculators filter by quality_acceptable."""
    # Add some non-acceptable records
    bad_data = sample_temperature_data.withColumn(
        "quality_acceptable",
        F.when(F.col("hour") < 6, False).otherwise(True)
    )
    
    features = calculate_temperature_features(bad_data)
    
    row = features.collect()[0]
    
    # Should have fewer observations (only quality_acceptable=True)
    total_hours = 91 * 24  # 91 days
    excluded_hours = 91 * 6  # 6 hours per day excluded
    expected_observations = total_hours - excluded_hours
    
    assert row["count_observations"] == expected_observations
