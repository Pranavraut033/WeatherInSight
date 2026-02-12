"""
Tests for DWD parser
"""
import pytest
from pyspark.sql.types import IntegerType, FloatType, StringType

import sys
sys.path.insert(0, 'src')

from parser import DWDParser, SCHEMA_DEFINITIONS, create_parser


def test_schema_definitions():
    """Test that all expected product types have schemas"""
    expected_products = [
        "air_temperature",
        "precipitation", 
        "wind",
        "pressure",
        "moisture",
        "cloud_cover"
    ]
    
    for product in expected_products:
        assert product in SCHEMA_DEFINITIONS
        schema = SCHEMA_DEFINITIONS[product]
        assert "STATIONS_ID" in [f.name for f in schema.fields]
        assert "MESS_DATUM" in [f.name for f in schema.fields]


def test_parser_initialization(spark):
    """Test parser can be initialized"""
    parser = DWDParser(spark, "air_temperature")
    assert parser.product_type == "air_temperature"
    assert parser.schema is not None


def test_parser_invalid_product(spark):
    """Test parser rejects invalid product type"""
    with pytest.raises(ValueError):
        DWDParser(spark, "invalid_product")


def test_parse_air_temperature_data(spark, sample_air_temp_data, tmp_path):
    """Test parsing air temperature data"""
    # Write sample data to CSV
    csv_path = str(tmp_path / "air_temp.csv")
    sample_air_temp_data.write.csv(
        csv_path, 
        sep=";", 
        header=True,
        mode="overwrite"
    )
    
    # Parse it
    parser = DWDParser(spark, "air_temperature")
    df = parser.parse_file(csv_path)
    
    # Verify
    assert df.count() == 4
    assert "timestamp" in df.columns
    assert "_source_file" in df.columns
    assert "_parsed_at" in df.columns


def test_validate_data(spark, sample_air_temp_data):
    """Test data validation"""
    parser = DWDParser(spark, "air_temperature")
    
    # Add timestamp column
    from pyspark.sql import functions as F
    df = sample_air_temp_data.withColumn(
        "timestamp",
        F.to_timestamp(F.col("MESS_DATUM"), "yyyyMMddHH")
    )
    
    metrics = parser.validate_data(df)
    
    assert metrics["total_rows"] == 4
    assert metrics["distinct_stations"] == 1
    assert "date_range" in metrics


def test_create_parser_factory(spark):
    """Test parser factory function"""
    parser = create_parser(spark, "precipitation")
    assert isinstance(parser, DWDParser)
    assert parser.product_type == "precipitation"
