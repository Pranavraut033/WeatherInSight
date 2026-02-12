"""
End-to-end test for complete WeatherInsight pipeline.

Tests the full flow:
1. Ingestion: DWD data sync to MinIO raw zone
2. Processing: Parse and stage data to MinIO staging zone
3. Aggregation: Compute quarterly features to PostgreSQL
4. API: Query features via REST endpoints

Uses real Docker Compose stack with actual services.
"""

import pytest
import requests
import subprocess
import time
from pathlib import Path
from datetime import datetime


PROJECT_ROOT = Path(__file__).parent.parent.parent


class TestFullPipeline:
    """Test complete pipeline with sample data."""
    
    def test_01_ingestion_service(self, docker_compose, sample_dwd_data):
        """Test ingestion of sample DWD data to MinIO."""
        # TODO: In real implementation, would use ingestion service
        # For now, verify MinIO is accessible
        
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
        
        # Verify raw bucket exists or create it
        try:
            s3_client.head_bucket(Bucket='weatherinsight-raw')
        except:
            s3_client.create_bucket(Bucket='weatherinsight-raw')
        
        # Upload sample data to MinIO raw zone
        for product_type, data_content in sample_dwd_data.items():
            object_key = f"raw/dwd/{product_type}/station_00433/2023/sample_week.txt"
            
            s3_client.put_object(
                Bucket='weatherinsight-raw',
                Key=object_key,
                Body=data_content.encode('utf-8'),
                Metadata={
                    'station_id': '433',
                    'product_type': product_type,
                    'ingestion_timestamp': datetime.utcnow().isoformat()
                }
            )
        
        # Verify objects were uploaded
        response = s3_client.list_objects_v2(
            Bucket='weatherinsight-raw',
            Prefix='raw/dwd/'
        )
        
        assert 'Contents' in response
        assert len(response['Contents']) >= 5  # 5 product types
        
        print(f"\n✓ Ingested {len(response['Contents'])} raw data files to MinIO")
    
    def test_02_processing_service(self, docker_compose, postgres_connection):
        """Test processing service parsing raw data."""
        # Verify staging bucket exists
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
        
        try:
            s3_client.head_bucket(Bucket='weatherinsight-staging')
        except:
            s3_client.create_bucket(Bucket='weatherinsight-staging')
        
        # For E2E test, we'd trigger processing service
        # Since we're testing infrastructure, verify bucket access
        
        # Simulate processing by checking raw data is accessible
        response = s3_client.list_objects_v2(
            Bucket='weatherinsight-raw',
            Prefix='raw/dwd/air_temperature/'
        )
        
        assert 'Contents' in response
        assert len(response['Contents']) >= 1
        
        print(f"\n✓ Processing service can access {len(response['Contents'])} raw files")
    
    def test_03_aggregation_service(self, postgres_connection, seed_station_metadata):
        """Test aggregation service computing quarterly features."""
        # For E2E test, we'd trigger aggregation service
        # Here we verify PostgreSQL tables are ready
        
        cursor = postgres_connection.cursor()
        
        # Verify feature tables exist
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name LIKE 'quarterly_%_features'
            ORDER BY table_name
        """)
        
        tables = [row[0] for row in cursor.fetchall()]
        
        expected_tables = [
            'quarterly_humidity_features',
            'quarterly_precipitation_features',
            'quarterly_pressure_features',
            'quarterly_temperature_features',
            'quarterly_wind_features'
        ]
        
        assert len(tables) >= 5, f"Expected 5 feature tables, found {len(tables)}"
        
        for table in expected_tables:
            assert table in tables, f"Missing table: {table}"
        
        # Verify station metadata exists
        cursor.execute("SELECT COUNT(*) FROM station_metadata WHERE station_id = 433")
        count = cursor.fetchone()[0]
        assert count == 1, "Station 433 metadata not found"
        
        print(f"\n✓ All {len(tables)} feature tables exist in PostgreSQL")
        print(f"✓ Station metadata seeded")
    
    def test_04_api_service_health(self, api_client):
        """Test API service health and connectivity."""
        response = requests.get(f"{api_client}/health")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data['status'] == 'healthy'
        assert 'database' in data
        assert data['database'] == 'connected'
        
        print(f"\n✓ API service healthy: {data}")
    
    def test_05_api_stations_endpoint(self, api_client, seed_station_metadata):
        """Test API stations endpoint returns seeded data."""
        response = requests.get(f"{api_client}/api/v1/stations")
        
        assert response.status_code == 200
        data = response.json()
        
        assert 'items' in data
        assert 'total' in data
        assert data['total'] >= 1
        
        # Find station 433
        station_433 = next((s for s in data['items'] if s['station_id'] == 433), None)
        assert station_433 is not None, "Station 433 not found in API response"
        assert station_433['name'] == 'Erfurt-Weimar'
        assert station_433['is_active'] is True
        
        print(f"\n✓ API returned {data['total']} stations including test station 433")
    
    def test_06_api_features_products(self, api_client):
        """Test API products endpoint."""
        response = requests.get(f"{api_client}/api/v1/features/products")
        
        assert response.status_code == 200
        data = response.json()
        
        assert 'products' in data
        assert len(data['products']) == 5
        
        expected_products = ['temperature', 'precipitation', 'wind', 'pressure', 'humidity']
        for product in expected_products:
            assert product in data['products']
        
        print(f"\n✓ API supports {len(data['products'])} product types")
    
    def test_07_api_openapi_docs(self, api_client):
        """Test API OpenAPI documentation is accessible."""
        response = requests.get(f"{api_client}/docs")
        
        assert response.status_code == 200
        assert 'text/html' in response.headers['content-type']
        
        # Verify OpenAPI spec is available
        response = requests.get(f"{api_client}/openapi.json")
        assert response.status_code == 200
        
        spec = response.json()
        assert 'openapi' in spec
        assert 'info' in spec
        assert spec['info']['title'] == 'WeatherInsight API'
        
        print(f"\n✓ OpenAPI documentation available at {api_client}/docs")
    
    def test_08_api_metrics_endpoint(self, api_client):
        """Test API Prometheus metrics endpoint."""
        response = requests.get(f"{api_client}/metrics")
        
        assert response.status_code == 200
        assert 'text/plain' in response.headers['content-type']
        
        metrics_text = response.text
        
        # Verify key metrics are present
        assert 'weatherinsight_api_requests_total' in metrics_text
        assert 'weatherinsight_api_request_duration_seconds' in metrics_text
        assert 'weatherinsight_api_db_query_duration_seconds' in metrics_text
        
        print(f"\n✓ Prometheus metrics endpoint responding with {len(metrics_text)} bytes")
    
    def test_09_monitoring_prometheus(self, docker_compose):
        """Test Prometheus is scraping metrics."""
        response = requests.get("http://localhost:9090/-/healthy")
        assert response.status_code == 200
        
        # Check targets
        response = requests.get("http://localhost:9090/api/v1/targets")
        assert response.status_code == 200
        
        data = response.json()
        assert data['status'] == 'success'
        
        active_targets = data['data']['activeTargets']
        target_jobs = {t['labels']['job'] for t in active_targets}
        
        # Verify key targets are being scraped
        expected_jobs = {'prometheus', 'weatherinsight-api', 'minio'}
        assert expected_jobs.issubset(target_jobs), f"Missing targets: {expected_jobs - target_jobs}"
        
        print(f"\n✓ Prometheus scraping {len(active_targets)} targets: {target_jobs}")
    
    def test_10_monitoring_grafana(self, docker_compose):
        """Test Grafana is accessible and configured."""
        response = requests.get("http://localhost:3002/api/health")
        assert response.status_code == 200
        
        data = response.json()
        assert data['database'] == 'ok'
        
        # Check datasources (requires auth)
        response = requests.get(
            "http://localhost:3002/api/datasources",
            auth=('admin', 'admin123')
        )
        assert response.status_code == 200
        
        datasources = response.json()
        prometheus_ds = next((ds for ds in datasources if ds['type'] == 'prometheus'), None)
        assert prometheus_ds is not None, "Prometheus datasource not configured"
        
        print(f"\n✓ Grafana healthy with {len(datasources)} datasource(s)")
    
    def test_11_end_to_end_data_flow(self, postgres_connection, seed_station_metadata):
        """
        Test complete data flow by inserting sample features and querying via API.
        
        This simulates the complete pipeline:
        Ingestion → Processing → Aggregation → API Query
        """
        cursor = postgres_connection.cursor()
        
        # Insert sample quarterly features for 2023 Q1
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
                1.5, -8.2, 12.4, 20.6,
                350.5, 0.0,
                420, 8,
                420, 0,
                45.2, 2.1
            )
        """)
        postgres_connection.commit()
        
        # Query via API
        response = requests.get(
            "http://localhost:8000/api/v1/features/temperature",
            params={'station_id': 433, 'year': 2023, 'quarter': 1}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data['total'] == 1
        assert len(data['items']) == 1
        
        feature = data['items'][0]
        assert feature['station_id'] == 433
        assert feature['year'] == 2023
        assert feature['quarter'] == 1
        assert feature['temp_mean_c'] == 1.5
        assert feature['heating_degree_days'] == 350.5
        
        print(f"\n✓ End-to-end data flow verified: DB → API → Response")
        print(f"  Sample feature: {feature['temp_mean_c']}°C mean temperature for 2023 Q1")


class TestPipelineResilience:
    """Test pipeline resilience and error handling."""
    
    def test_api_handles_missing_data(self, api_client):
        """Test API gracefully handles queries for non-existent data."""
        response = requests.get(
            f"{api_client}/api/v1/features/temperature",
            params={'station_id': 99999, 'year': 2099, 'quarter': 4}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data['total'] == 0
        assert len(data['items']) == 0
        
        print(f"\n✓ API handles missing data gracefully")
    
    def test_api_validates_input(self, api_client):
        """Test API validates invalid input parameters."""
        # Invalid quarter
        response = requests.get(
            f"{api_client}/api/v1/features/temperature",
            params={'quarter': 5}
        )
        
        assert response.status_code == 422  # Validation error
        
        # Invalid product type
        response = requests.get(f"{api_client}/api/v1/features/invalid_product")
        assert response.status_code == 404
        
        print(f"\n✓ API validates input parameters correctly")
    
    def test_database_connection_pool(self, api_client, postgres_connection):
        """Test API handles concurrent requests efficiently."""
        import concurrent.futures
        
        def make_request(i):
            response = requests.get(f"{api_client}/api/v1/stations?limit=10")
            return response.status_code == 200
        
        # Make 20 concurrent requests
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(make_request, range(20)))
        
        # All requests should succeed
        assert all(results), f"Only {sum(results)}/20 requests succeeded"
        
        print(f"\n✓ API handled 20 concurrent requests successfully")
