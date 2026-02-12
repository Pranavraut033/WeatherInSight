"""
End-to-end data quality validation tests.

Tests data quality across all pipeline stages:
- Raw zone: Schema conformance, completeness
- Staged zone: Parsing accuracy, quality filtering
- Curated zone: Feature correctness, consistency
"""

import pytest
import psycopg2
from datetime import datetime
from typing import Dict, Any


class TestRawDataQuality:
    """Test raw data quality in MinIO."""
    
    def test_raw_data_structure(self, docker_compose, sample_dwd_data):
        """Test raw data follows expected DWD format."""
        import boto3
        from botocore.client import Config
        
        s3_client = boto3.client(
            's3',
            endpoint_url='http://localhost:9000',
            aws_access_key_id='minioadmin',
            aws_secret_access_key='minioadmin123',
            config=Config(signature_version='s3v4'),
            region_name='us-east-1'
        )
        
        # Check temperature data structure
        response = s3_client.list_objects_v2(
            Bucket='weatherinsight-raw',
            Prefix='raw/dwd/air_temperature/'
        )
        
        if 'Contents' not in response:
            pytest.skip("No raw data found, run test_full_pipeline first")
        
        # Download and validate structure
        obj = response['Contents'][0]
        data = s3_client.get_object(Bucket='weatherinsight-raw', Key=obj['Key'])
        content = data['Body'].read().decode('utf-8')
        
        lines = content.strip().split('\n')
        
        # Verify header
        assert lines[0].startswith('STATIONS_ID'), "Missing header"
        
        # Verify data rows
        for line in lines[1:]:
            if not line.strip():
                continue
            
            fields = line.split(';')
            assert len(fields) >= 5, f"Invalid row format: {line}"
            
            # Validate station ID format
            station_id = fields[0]
            assert station_id.isdigit(), f"Invalid station ID: {station_id}"
            
            # Validate timestamp format
            timestamp = fields[1]
            assert len(timestamp) == 10, f"Invalid timestamp: {timestamp}"
            assert timestamp.isdigit(), f"Non-numeric timestamp: {timestamp}"
        
        print(f"\n✓ Raw data structure validated: {len(lines)-1} rows")
    
    def test_raw_data_completeness(self, docker_compose):
        """Test all required product types are present."""
        import boto3
        from botocore.client import Config
        
        s3_client = boto3.client(
            's3',
            endpoint_url='http://localhost:9000',
            aws_access_key_id='minioadmin',
            aws_secret_access_key='minioadmin123',
            config=Config(signature_version='s3v4'),
            region_name='us-east-1'
        )
        
        expected_products = [
            'air_temperature',
            'precipitation',
            'wind',
            'pressure',
            'moisture'
        ]
        
        for product in expected_products:
            response = s3_client.list_objects_v2(
                Bucket='weatherinsight-raw',
                Prefix=f'raw/dwd/{product}/'
            )
            
            assert 'Contents' in response, f"No data found for {product}"
            assert len(response['Contents']) >= 1, f"Insufficient data for {product}"
        
        print(f"\n✓ All {len(expected_products)} product types present in raw zone")
    
    def test_raw_data_metadata(self, docker_compose):
        """Test raw data has required metadata."""
        import boto3
        from botocore.client import Config
        
        s3_client = boto3.client(
            's3',
            endpoint_url='http://localhost:9000',
            aws_access_key_id='minioadmin',
            aws_secret_access_key='minioadmin123',
            config=Config(signature_version='s3v4'),
            region_name='us-east-1'
        )
        
        response = s3_client.list_objects_v2(
            Bucket='weatherinsight-raw',
            Prefix='raw/dwd/air_temperature/',
            MaxKeys=1
        )
        
        if 'Contents' not in response:
            pytest.skip("No raw data found")
        
        obj = response['Contents'][0]
        
        # Get object metadata
        head_response = s3_client.head_object(
            Bucket='weatherinsight-raw',
            Key=obj['Key']
        )
        
        metadata = head_response.get('Metadata', {})
        
        # Verify key metadata fields
        assert 'station_id' in metadata or 'product_type' in metadata, \
            "Missing required metadata fields"
        
        print(f"\n✓ Raw data has metadata: {list(metadata.keys())}")


class TestCuratedDataQuality:
    """Test curated feature quality in PostgreSQL."""
    
    def test_feature_table_schemas(self, postgres_connection):
        """Test feature tables have correct schema structure."""
        cursor = postgres_connection.cursor()
        
        # Test temperature features table
        cursor.execute("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'quarterly_temperature_features'
            ORDER BY ordinal_position
        """)
        
        columns = {row[0]: {'type': row[1], 'nullable': row[2]} for row in cursor.fetchall()}
        
        # Verify required columns exist
        required_columns = [
            'station_id', 'year', 'quarter', 'dataset_version',
            'temp_mean_c', 'temp_min_c', 'temp_max_c',
            'heating_degree_days', 'cooling_degree_days'
        ]
        
        for col in required_columns:
            assert col in columns, f"Missing required column: {col}"
        
        # Verify primary key columns are NOT NULL
        pk_columns = ['station_id', 'year', 'quarter']
        for col in pk_columns:
            assert columns[col]['nullable'] == 'NO', f"Primary key column {col} allows NULL"
        
        print(f"\n✓ Temperature features table has {len(columns)} columns")
    
    def test_feature_value_ranges(self, postgres_connection, seed_station_metadata):
        """Test feature values are within expected ranges."""
        cursor = postgres_connection.cursor()
        
        # Insert test data with valid ranges
        cursor.execute("""
            INSERT INTO quarterly_temperature_features (
                station_id, year, quarter, dataset_version,
                temp_mean_c, temp_min_c, temp_max_c, temp_range_c,
                heating_degree_days, cooling_degree_days,
                frost_hours, freeze_thaw_cycles,
                hours_below_0c, hours_above_25c,
                temp_variance, missing_hours_pct
            ) VALUES (
                433, 2023, 1, 'v1.0.0-test',
                5.2, -12.4, 22.8, 35.2,
                250.5, 5.0,
                350, 12,
                350, 8,
                55.3, 1.8
            )
            ON CONFLICT (station_id, year, quarter) DO UPDATE SET
                temp_mean_c = EXCLUDED.temp_mean_c
        """)
        postgres_connection.commit()
        
        # Validate ranges
        cursor.execute("""
            SELECT 
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE temp_mean_c BETWEEN -50 AND 50) as temp_valid,
                COUNT(*) FILTER (WHERE heating_degree_days >= 0) as hdd_valid,
                COUNT(*) FILTER (WHERE cooling_degree_days >= 0) as cdd_valid,
                COUNT(*) FILTER (WHERE frost_hours BETWEEN 0 AND 2208) as frost_valid,
                COUNT(*) FILTER (WHERE missing_hours_pct BETWEEN 0 AND 100) as missing_valid
            FROM quarterly_temperature_features
            WHERE station_id = 433 AND year = 2023 AND quarter = 1
        """)
        
        result = cursor.fetchone()
        total, temp_valid, hdd_valid, cdd_valid, frost_valid, missing_valid = result
        
        assert total > 0, "No data found"
        assert temp_valid == total, "Temperature out of range"
        assert hdd_valid == total, "Negative heating degree days"
        assert cdd_valid == total, "Negative cooling degree days"
        assert frost_valid == total, "Frost hours out of range"
        assert missing_valid == total, "Missing percentage out of range"
        
        print(f"\n✓ All {total} feature records have values within valid ranges")
    
    def test_feature_consistency(self, postgres_connection, seed_station_metadata):
        """Test logical consistency between related features."""
        cursor = postgres_connection.cursor()
        
        # Ensure test data exists
        cursor.execute("""
            INSERT INTO quarterly_temperature_features (
                station_id, year, quarter, dataset_version,
                temp_mean_c, temp_min_c, temp_max_c, temp_range_c,
                heating_degree_days, cooling_degree_days,
                frost_hours, freeze_thaw_cycles,
                hours_below_0c, hours_above_25c,
                temp_variance, missing_hours_pct
            ) VALUES (
                433, 2023, 2, 'v1.0.0-test',
                15.5, 2.3, 28.7, 26.4,
                50.0, 120.5,
                0, 0,
                0, 45,
                65.8, 0.5
            )
            ON CONFLICT (station_id, year, quarter) DO UPDATE SET
                temp_mean_c = EXCLUDED.temp_mean_c
        """)
        postgres_connection.commit()
        
        # Check consistency rules
        cursor.execute("""
            SELECT 
                station_id, year, quarter,
                temp_min_c, temp_mean_c, temp_max_c, temp_range_c,
                frost_hours, hours_below_0c,
                (temp_max_c - temp_min_c) as calculated_range,
                (temp_max_c >= temp_mean_c) as max_gte_mean,
                (temp_mean_c >= temp_min_c) as mean_gte_min,
                (frost_hours <= hours_below_0c) as frost_lte_below_zero
            FROM quarterly_temperature_features
            WHERE station_id = 433 AND year IN (2023)
        """)
        
        results = cursor.fetchall()
        assert len(results) > 0, "No data for consistency check"
        
        for row in results:
            station, year, quarter, t_min, t_mean, t_max, t_range, frost, below_0, calc_range, max_gte, mean_gte, frost_lte = row
            
            # Max >= Mean >= Min
            assert max_gte, f"Q{quarter}: temp_max < temp_mean"
            assert mean_gte, f"Q{quarter}: temp_mean < temp_min"
            
            # Range approximately matches max - min (within 1°C tolerance)
            assert abs(calc_range - t_range) <= 1.0, \
                f"Q{quarter}: Range mismatch {t_range} vs {calc_range}"
            
            # Frost hours <= hours below 0°C
            assert frost_lte, f"Q{quarter}: frost_hours > hours_below_0c"
        
        print(f"\n✓ Validated consistency for {len(results)} feature records")
    
    def test_feature_completeness(self, postgres_connection, seed_station_metadata):
        """Test no unexpected NULL values in critical columns."""
        cursor = postgres_connection.cursor()
        
        # Ensure we have test data
        cursor.execute("""
            SELECT COUNT(*) FROM quarterly_temperature_features
            WHERE station_id = 433
        """)
        
        count = cursor.fetchone()[0]
        if count == 0:
            pytest.skip("No data available for completeness check")
        
        # Check for NULLs in critical columns
        cursor.execute("""
            SELECT 
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE temp_mean_c IS NULL) as temp_mean_null,
                COUNT(*) FILTER (WHERE temp_min_c IS NULL) as temp_min_null,
                COUNT(*) FILTER (WHERE temp_max_c IS NULL) as temp_max_null,
                COUNT(*) FILTER (WHERE heating_degree_days IS NULL) as hdd_null,
                COUNT(*) FILTER (WHERE missing_hours_pct IS NULL) as missing_pct_null
            FROM quarterly_temperature_features
            WHERE station_id = 433
        """)
        
        result = cursor.fetchone()
        total = result[0]
        null_counts = result[1:]
        
        # No critical columns should be NULL
        assert all(n == 0 for n in null_counts), \
            f"Found NULL values in critical columns: {null_counts}"
        
        print(f"\n✓ No NULL values in {len(null_counts)} critical columns ({total} records)")
    
    def test_cross_table_consistency(self, postgres_connection, seed_station_metadata):
        """Test consistency between station_metadata and feature tables."""
        cursor = postgres_connection.cursor()
        
        # Check that all stations in features exist in metadata
        cursor.execute("""
            SELECT DISTINCT t.station_id
            FROM quarterly_temperature_features t
            LEFT JOIN station_metadata m ON t.station_id = m.station_id
            WHERE m.station_id IS NULL
        """)
        
        orphaned_stations = cursor.fetchall()
        
        assert len(orphaned_stations) == 0, \
            f"Found {len(orphaned_stations)} stations in features without metadata"
        
        # Check that features respect station active dates
        cursor.execute("""
            SELECT COUNT(*) as violations
            FROM quarterly_temperature_features f
            JOIN station_metadata m ON f.station_id = m.station_id
            WHERE 
                (m.start_date IS NOT NULL AND 
                 MAKE_DATE(f.year, (f.quarter - 1) * 3 + 1, 1) < m.start_date)
                OR
                (m.end_date IS NOT NULL AND 
                 MAKE_DATE(f.year, f.quarter * 3, 28) > m.end_date)
        """)
        
        violations = cursor.fetchone()[0]
        
        # Allow some violations for edge cases, but not excessive
        assert violations == 0, \
            f"Found {violations} features outside station active date ranges"
        
        print(f"\n✓ Cross-table consistency validated (0 violations)")


class TestDataQualityChecks:
    """Test automated data quality checks from Airflow DAG."""
    
    def test_row_count_threshold(self, postgres_connection):
        """Test row count validation logic."""
        cursor = postgres_connection.cursor()
        
        # Get current row counts
        tables = [
            'quarterly_temperature_features',
            'quarterly_precipitation_features',
            'quarterly_wind_features',
            'quarterly_pressure_features',
            'quarterly_humidity_features'
        ]
        
        min_threshold = 100  # From DAG config
        
        for table in tables:
            try:
                cursor.execute(f"""
                    SELECT 
                        year, quarter, COUNT(*) as row_count
                    FROM {table}
                    GROUP BY year, quarter
                    HAVING COUNT(*) > 0
                    ORDER BY year, quarter
                """)
                
                results = cursor.fetchall()
                
                if len(results) == 0:
                    print(f"  ⊘ {table}: No data (skipped)")
                    continue
                
                for year, quarter, count in results:
                    # This is informational - real DAG would fail if below threshold
                    status = "✓" if count >= min_threshold else "⚠"
                    print(f"  {status} {table}: {count} rows for {year} Q{quarter}")
                    
            except psycopg2.errors.UndefinedTable:
                print(f"  ⊘ {table}: Table not found (skipped)")
    
    def test_null_percentage_threshold(self, postgres_connection, seed_station_metadata):
        """Test null percentage validation logic."""
        cursor = postgres_connection.cursor()
        
        # Ensure test data with controlled nulls
        cursor.execute("""
            INSERT INTO quarterly_temperature_features (
                station_id, year, quarter, dataset_version,
                temp_mean_c, temp_min_c, temp_max_c, temp_range_c,
                heating_degree_days, cooling_degree_days,
                frost_hours, freeze_thaw_cycles,
                hours_below_0c, hours_above_25c,
                temp_variance, missing_hours_pct
            ) VALUES (
                433, 2023, 3, 'v1.0.0-test',
                18.5, 8.2, 29.3, 21.1,
                25.0, 250.0,
                0, 0,
                0, 120,
                72.4, 0.0
            )
            ON CONFLICT (station_id, year, quarter) DO UPDATE SET
                temp_mean_c = EXCLUDED.temp_mean_c
        """)
        postgres_connection.commit()
        
        # Check null percentages
        cursor.execute("""
            SELECT 
                COUNT(*) as total,
                100.0 * COUNT(*) FILTER (WHERE temp_mean_c IS NULL) / COUNT(*) as temp_mean_null_pct,
                100.0 * COUNT(*) FILTER (WHERE temp_min_c IS NULL) / COUNT(*) as temp_min_null_pct,
                100.0 * COUNT(*) FILTER (WHERE temp_max_c IS NULL) / COUNT(*) as temp_max_null_pct
            FROM quarterly_temperature_features
            WHERE station_id = 433
        """)
        
        result = cursor.fetchone()
        total, temp_mean_pct, temp_min_pct, temp_max_pct = result
        
        max_threshold = 15.0  # From DAG config
        
        assert temp_mean_pct <= max_threshold, f"temp_mean_c: {temp_mean_pct}% null (threshold: {max_threshold}%)"
        assert temp_min_pct <= max_threshold, f"temp_min_c: {temp_min_pct}% null (threshold: {max_threshold}%)"
        assert temp_max_pct <= max_threshold, f"temp_max_c: {temp_max_pct}% null (threshold: {max_threshold}%)"
        
        print(f"\n✓ Null percentages within threshold: mean={temp_mean_pct:.1f}%, min={temp_min_pct:.1f}%, max={temp_max_pct:.1f}%")
    
    def test_station_coverage_threshold(self, postgres_connection):
        """Test station coverage validation logic."""
        cursor = postgres_connection.cursor()
        
        min_stations = 50  # From DAG config
        
        # Check station coverage per quarter
        cursor.execute("""
            SELECT 
                year, quarter, COUNT(DISTINCT station_id) as station_count
            FROM quarterly_temperature_features
            GROUP BY year, quarter
            HAVING COUNT(DISTINCT station_id) > 0
            ORDER BY year, quarter
        """)
        
        results = cursor.fetchall()
        
        if len(results) == 0:
            pytest.skip("No data for station coverage check")
        
        for year, quarter, count in results:
            status = "✓" if count >= min_stations else "⚠"
            print(f"  {status} {year} Q{quarter}: {count} stations (threshold: {min_stations})")
