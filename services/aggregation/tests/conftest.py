"""
Pytest configuration and fixtures for aggregation service tests.
"""
import pytest
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from datetime import datetime


@pytest.fixture(scope="session")
def spark():
    """Create a Spark session for testing."""
    spark = (
        SparkSession.builder
        .appName("WeatherInsight-Aggregation-Tests")
        .master("local[2]")
        .config("spark.sql.shuffle.partitions", "2")
        .getOrCreate()
    )
    
    yield spark
    
    spark.stop()


@pytest.fixture
def sample_temperature_data(spark):
    """Create sample hourly temperature data for testing."""
    data = []
    
    # Create 91 days of hourly data for Q1 (Jan-Mar)
    for day in range(1, 92):  # 91 days
        for hour in range(24):
            # Simulate daily temperature cycle
            temp = 10 + 5 * (hour - 12) / 12  # Peaks at noon, drops at night
            
            # Add some variation by day
            temp += (day % 10) - 5
            
            # Add some frost hours
            if hour < 6 or hour > 20:
                temp -= 3
            
            data.append({
                "STATIONS_ID": 433,
                "timestamp": datetime(2023, 1, 1 + (day - 1) // 31, ((day - 1) % 31) + 1, hour),
                "year": 2023,
                "quarter": 1,
                "month": 1 + (day - 1) // 31,
                "day": ((day - 1) % 31) + 1,
                "hour": hour,
                "TT_TU": temp,
                "RF_TU": 75.0,
                "quality_acceptable": True,
                "dataset_version": "v1.0.0",
                "_source_file": "test.txt",
                "_parsed_at": datetime.utcnow(),
                "_cleaned_at": datetime.utcnow(),
                "_outlier_flag": False
            })
    
    return spark.createDataFrame(data)


@pytest.fixture
def sample_precipitation_data(spark):
    """Create sample hourly precipitation data for testing."""
    data = []
    
    # Create data with wet and dry spells
    for day in range(1, 92):
        for hour in range(24):
            # Simulate wet spells every 7 days
            if day % 7 < 3:  # 3 days wet, 4 days dry
                precip = 0.5 if hour % 3 == 0 else 0.1  # Some hours with more rain
            else:
                precip = 0.0
            
            data.append({
                "STATIONS_ID": 433,
                "timestamp": datetime(2023, 1, 1 + (day - 1) // 31, ((day - 1) % 31) + 1, hour),
                "year": 2023,
                "quarter": 1,
                "month": 1 + (day - 1) // 31,
                "day": ((day - 1) % 31) + 1,
                "hour": hour,
                "R1": precip,
                "RS_IND": 1 if precip > 0 else 0,
                "quality_acceptable": True,
                "dataset_version": "v1.0.0",
                "_source_file": "test.txt",
                "_parsed_at": datetime.utcnow(),
                "_cleaned_at": datetime.utcnow()
            })
    
    return spark.createDataFrame(data)


@pytest.fixture
def sample_wind_data(spark):
    """Create sample hourly wind data for testing."""
    data = []
    
    for day in range(1, 92):
        for hour in range(24):
            # Simulate varying wind speeds and directions
            wind_speed = 5.0 + (hour % 12) * 0.5  # Varies through day
            direction = (hour * 15) % 360  # Rotates through compass
            
            data.append({
                "STATIONS_ID": 433,
                "timestamp": datetime(2023, 1, 1 + (day - 1) // 31, ((day - 1) % 31) + 1, hour),
                "year": 2023,
                "quarter": 1,
                "month": 1 + (day - 1) // 31,
                "day": ((day - 1) % 31) + 1,
                "hour": hour,
                "F": wind_speed,
                "D": direction,
                "quality_acceptable": True,
                "dataset_version": "v1.0.0",
                "_source_file": "test.txt",
                "_parsed_at": datetime.utcnow(),
                "_cleaned_at": datetime.utcnow()
            })
    
    return spark.createDataFrame(data)


@pytest.fixture
def sample_pressure_data(spark):
    """Create sample hourly pressure data for testing."""
    data = []
    
    for day in range(1, 92):
        for hour in range(24):
            # Simulate pressure variations
            pressure = 101300 + (day % 20 - 10) * 100  # Varies between 100300 and 102300 Pa
            
            data.append({
                "STATIONS_ID": 433,
                "timestamp": datetime(2023, 1, 1 + (day - 1) // 31, ((day - 1) % 31) + 1, hour),
                "year": 2023,
                "quarter": 1,
                "month": 1 + (day - 1) // 31,
                "day": ((day - 1) % 31) + 1,
                "hour": hour,
                "P_pa": pressure,
                "quality_acceptable": True,
                "dataset_version": "v1.0.0",
                "_source_file": "test.txt",
                "_parsed_at": datetime.utcnow(),
                "_cleaned_at": datetime.utcnow()
            })
    
    return spark.createDataFrame(data)


@pytest.fixture
def sample_humidity_data(spark):
    """Create sample hourly humidity data for testing."""
    data = []
    
    for day in range(1, 92):
        for hour in range(24):
            # Simulate humidity variations (inverse of temperature pattern)
            humidity = 70 - (hour - 12) * 2  # Higher at night, lower at noon
            humidity = max(30, min(95, humidity))  # Clamp to reasonable range
            
            data.append({
                "STATIONS_ID": 433,
                "timestamp": datetime(2023, 1, 1 + (day - 1) // 31, ((day - 1) % 31) + 1, hour),
                "year": 2023,
                "quarter": 1,
                "month": 1 + (day - 1) // 31,
                "day": ((day - 1) % 31) + 1,
                "hour": hour,
                "RF_TU": humidity,
                "TF_TU": 5.0,  # Dew point
                "quality_acceptable": True,
                "dataset_version": "v1.0.0",
                "_source_file": "test.txt",
                "_parsed_at": datetime.utcnow(),
                "_cleaned_at": datetime.utcnow()
            })
    
    return spark.createDataFrame(data)


@pytest.fixture
def sample_station_metadata(spark):
    """Create sample station metadata."""
    data = [
        {
            "station_id": 433,
            "name": "Test Station",
            "latitude": 52.5200,
            "longitude": 13.4050,
            "elevation_m": 45.0
        }
    ]
    
    return spark.createDataFrame(data)
