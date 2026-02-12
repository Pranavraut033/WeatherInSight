import pytest
from pyspark.sql import SparkSession


@pytest.fixture(scope="session")
def spark():
    """Create Spark session for tests"""
    spark = (
        SparkSession.builder
        .appName("WeatherInsight-Processing-Tests")
        .master("local[2]")
        .config("spark.sql.shuffle.partitions", "2")
        .getOrCreate()
    )
    
    yield spark
    
    spark.stop()


@pytest.fixture
def sample_air_temp_data(spark):
    """Sample air temperature data for testing"""
    data = [
        (433, "2023010100", 3, -2.4, 87.0),
        (433, "2023010101", 3, -2.8, 89.0),
        (433, "2023010102", 3, -999.0, 90.0),  # Missing temp
        (433, "2023010103", 2, -3.0, 88.0),    # Low quality
    ]
    
    columns = ["STATIONS_ID", "MESS_DATUM", "QN_9", "TT_TU", "RF_TU"]
    
    return spark.createDataFrame(data, columns)


@pytest.fixture
def sample_precip_data(spark):
    """Sample precipitation data for testing"""
    data = [
        (1766, "2023010100", 3, 0.5, 1, 6),
        (1766, "2023010101", 3, 0.0, 0, 0),
        (1766, "2023010102", 3, -999.0, -999, -999),  # All missing
        (1766, "2023010103", 3, 2.5, 1, 6),
    ]
    
    columns = ["STATIONS_ID", "MESS_DATUM", "QN_8", "R1", "RS_IND", "WRTR"]
    
    return spark.createDataFrame(data, columns)
