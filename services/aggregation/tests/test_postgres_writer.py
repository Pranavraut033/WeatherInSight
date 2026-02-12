"""
Tests for PostgreSQL writer functionality.
"""
import pytest
from unittest.mock import Mock, MagicMock, patch
from pyspark.sql import functions as F

from aggregation.src.config import AggregationConfig
from aggregation.src.postgres_writer import PostgresWriter


def test_table_map():
    """Test product type to table name mapping."""
    assert PostgresWriter.TABLE_MAP["air_temperature"] == "quarterly_temperature_features"
    assert PostgresWriter.TABLE_MAP["precipitation"] == "quarterly_precipitation_features"
    assert PostgresWriter.TABLE_MAP["wind"] == "quarterly_wind_features"
    assert PostgresWriter.TABLE_MAP["pressure"] == "quarterly_pressure_features"
    assert PostgresWriter.TABLE_MAP["moisture"] == "quarterly_humidity_features"


def test_unknown_product_type_raises_error():
    """Test that unknown product types raise ValueError."""
    config = AggregationConfig()
    writer = PostgresWriter(config)
    
    with pytest.raises(ValueError, match="Unknown product type"):
        writer.delete_existing_features(
            product_type="unknown",
            station_id=None,
            year=2023,
            quarter=1,
            dataset_version="v1.0.0"
        )


@patch('aggregation.src.postgres_writer.psycopg2.connect')
def test_delete_existing_features_all_stations(mock_connect):
    """Test deleting features for all stations."""
    config = AggregationConfig()
    writer = PostgresWriter(config)
    
    # Mock database connection
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.rowcount = 5
    mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = Mock(return_value=False)
    mock_connect.return_value.__enter__ = Mock(return_value=mock_conn)
    mock_connect.return_value.__exit__ = Mock(return_value=False)
    
    # Delete for all stations
    writer.delete_existing_features(
        product_type="air_temperature",
        station_id=None,
        year=2023,
        quarter=1,
        dataset_version="v1.0.0"
    )
    
    # Verify SQL was executed
    mock_cursor.execute.assert_called_once()
    sql_call = mock_cursor.execute.call_args[0][0]
    params = mock_cursor.execute.call_args[0][1]
    
    assert "DELETE FROM quarterly_temperature_features" in sql_call
    assert "WHERE year = %s" in sql_call
    assert "AND quarter = %s" in sql_call
    assert params == (2023, 1, "v1.0.0")
    
    mock_conn.commit.assert_called_once()


@patch('aggregation.src.postgres_writer.psycopg2.connect')
def test_delete_existing_features_single_station(mock_connect):
    """Test deleting features for a specific station."""
    config = AggregationConfig()
    writer = PostgresWriter(config)
    
    # Mock database connection
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.rowcount = 1
    mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = Mock(return_value=False)
    mock_connect.return_value.__enter__ = Mock(return_value=mock_conn)
    mock_connect.return_value.__exit__ = Mock(return_value=False)
    
    # Delete for specific station
    writer.delete_existing_features(
        product_type="precipitation",
        station_id=433,
        year=2023,
        quarter=2,
        dataset_version="v1.0.0"
    )
    
    # Verify SQL was executed with station filter
    mock_cursor.execute.assert_called_once()
    sql_call = mock_cursor.execute.call_args[0][0]
    params = mock_cursor.execute.call_args[0][1]
    
    assert "DELETE FROM quarterly_precipitation_features" in sql_call
    assert "WHERE station_id = %s" in sql_call
    assert params == (433, 2023, 2, "v1.0.0")


def test_write_features_basic(spark, sample_temperature_data, sample_station_metadata):
    """Test basic feature writing flow."""
    config = AggregationConfig()
    writer = PostgresWriter(config)
    
    # Create a simple features DataFrame
    from aggregation.src.feature_calculators import calculate_temperature_features
    
    features_df = calculate_temperature_features(sample_temperature_data)
    
    # Join with metadata
    features_df = features_df.join(
        sample_station_metadata,
        on="station_id",
        how="left"
    ).withColumn("quarter_start", F.lit("2023-01-01 00:00:00").cast("timestamp"))
    
    # Mock the delete and JDBC write operations
    with patch.object(writer, 'delete_existing_features') as mock_delete:
        with patch.object(features_df.write, 'jdbc') as mock_jdbc:
            row_count = writer.write_features(
                features_df=features_df,
                product_type="air_temperature",
                year=2023,
                quarter=1,
                dataset_version="v1.0.0",
                mode="append"
            )
            
            # Verify delete was called
            mock_delete.assert_called_once_with(
                product_type="air_temperature",
                station_id=None,
                year=2023,
                quarter=1,
                dataset_version="v1.0.0"
            )
            
            # Verify JDBC write was called
            mock_jdbc.assert_called_once()
            call_kwargs = mock_jdbc.call_args[1]
            
            assert call_kwargs["table"] == "quarterly_temperature_features"
            assert call_kwargs["mode"] == "append"
            assert "user" in call_kwargs["properties"]
            
            # Should return row count
            assert row_count == 1


def test_write_features_overwrite_mode(spark, sample_temperature_data):
    """Test that overwrite mode skips deletion."""
    config = AggregationConfig()
    writer = PostgresWriter(config)
    
    from aggregation.src.feature_calculators import calculate_temperature_features
    features_df = calculate_temperature_features(sample_temperature_data)
    
    with patch.object(writer, 'delete_existing_features') as mock_delete:
        with patch.object(features_df.write, 'jdbc'):
            writer.write_features(
                features_df=features_df,
                product_type="air_temperature",
                year=2023,
                quarter=1,
                dataset_version="v1.0.0",
                mode="overwrite"
            )
            
            # Delete should NOT be called in overwrite mode
            mock_delete.assert_not_called()
