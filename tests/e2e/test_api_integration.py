"""
API integration tests with real database.

Tests API behavior with actual PostgreSQL data:
- All endpoints with various query parameters
- Pagination edge cases
- Filter combinations
- Error handling
- Performance characteristics
"""

import pytest
import requests
from typing import List, Dict


class TestAPIStationsIntegration:
    """Test stations endpoints with real database."""
    
    def test_list_stations_pagination(self, api_client, seed_station_metadata):
        """Test station listing with pagination."""
        # Get first page
        response = requests.get(
            f"{api_client}/api/v1/stations",
            params={'limit': 5, 'offset': 0}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert 'items' in data
        assert 'total' in data
        assert 'limit' in data
        assert 'offset' in data
        
        assert len(data['items']) <= 5
        assert data['limit'] == 5
        assert data['offset'] == 0
        
        print(f"\n✓ Pagination works: {len(data['items'])} items, {data['total']} total")
    
    def test_get_station_detail(self, api_client, seed_station_metadata):
        """Test getting specific station details."""
        response = requests.get(f"{api_client}/api/v1/stations/433")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data['station_id'] == 433
        assert data['name'] == 'Erfurt-Weimar'
        assert data['state'] == 'Thüringen'
        assert data['is_active'] is True
        assert 'latitude' in data
        assert 'longitude' in data
        assert 'elevation_m' in data
        
        print(f"\n✓ Station detail: {data['name']} at ({data['latitude']}, {data['longitude']})")
    
    def test_station_not_found(self, api_client):
        """Test handling of non-existent station."""
        response = requests.get(f"{api_client}/api/v1/stations/99999")
        
        assert response.status_code == 404
        data = response.json()
        
        assert 'detail' in data
        
        print(f"\n✓ Station not found handled correctly: {data['detail']}")
    
    def test_station_summary(self, api_client, seed_station_metadata, postgres_connection):
        """Test station summary with feature counts."""
        # Insert sample features for summary
        cursor = postgres_connection.cursor()
        
        cursor.execute("""
            INSERT INTO quarterly_temperature_features (
                station_id, year, quarter, dataset_version,
                temp_mean_c, temp_min_c, temp_max_c, temp_range_c,
                heating_degree_days, cooling_degree_days,
                frost_hours, freeze_thaw_cycles,
                hours_below_0c, hours_above_25c,
                temp_variance, missing_hours_pct
            ) VALUES 
                (433, 2023, 1, 'v1.0.0', 2.5, -5.2, 12.1, 17.3, 320.0, 0.0, 400, 10, 400, 0, 42.1, 1.5),
                (433, 2023, 2, 'v1.0.0', 8.3, -1.5, 18.9, 20.4, 180.0, 15.0, 50, 2, 50, 5, 55.2, 0.8)
            ON CONFLICT (station_id, year, quarter) DO NOTHING
        """)
        postgres_connection.commit()
        
        response = requests.get(f"{api_client}/api/v1/stations/433/summary")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data['station_id'] == 433
        assert 'feature_counts' in data
        assert data['feature_counts']['temperature'] >= 2
        
        print(f"\n✓ Station summary: {data['feature_counts']}")


class TestAPIFeaturesIntegration:
    """Test features endpoints with real database."""
    
    def test_list_temperature_features(self, api_client, postgres_connection, seed_station_metadata):
        """Test listing temperature features."""
        # Ensure we have data
        cursor = postgres_connection.cursor()
        cursor.execute("""
            INSERT INTO quarterly_temperature_features (
                station_id, year, quarter, dataset_version,
                temp_mean_c, temp_min_c, temp_max_c, temp_range_c,
                heating_degree_days, cooling_degree_days,
                frost_hours, freeze_thaw_cycles,
                hours_below_0c, hours_above_25c,
                temp_variance, missing_hours_pct
            ) VALUES (
                433, 2023, 1, 'v1.0.0',
                3.2, -8.5, 15.2, 23.7,
                300.5, 0.0,
                380, 12,
                380, 0,
                48.3, 2.0
            )
            ON CONFLICT (station_id, year, quarter) DO UPDATE SET
                temp_mean_c = EXCLUDED.temp_mean_c
        """)
        postgres_connection.commit()
        
        response = requests.get(f"{api_client}/api/v1/features/temperature")
        
        assert response.status_code == 200
        data = response.json()
        
        assert 'items' in data
        assert 'total' in data
        assert data['total'] >= 1
        
        if len(data['items']) > 0:
            item = data['items'][0]
            assert 'station_id' in item
            assert 'year' in item
            assert 'quarter' in item
            assert 'temp_mean_c' in item
            assert 'heating_degree_days' in item
        
        print(f"\n✓ Temperature features: {data['total']} records")
    
    def test_filter_by_station(self, api_client, postgres_connection, seed_station_metadata):
        """Test filtering features by station ID."""
        # Ensure station 433 has data
        cursor = postgres_connection.cursor()
        cursor.execute("""
            INSERT INTO quarterly_temperature_features (
                station_id, year, quarter, dataset_version,
                temp_mean_c, temp_min_c, temp_max_c, temp_range_c,
                heating_degree_days, cooling_degree_days,
                frost_hours, freeze_thaw_cycles,
                hours_below_0c, hours_above_25c,
                temp_variance, missing_hours_pct
            ) VALUES (
                433, 2023, 2, 'v1.0.0',
                9.5, 0.2, 20.3, 20.1,
                150.0, 30.0,
                20, 1,
                20, 10,
                58.7, 0.5
            )
            ON CONFLICT (station_id, year, quarter) DO UPDATE SET
                temp_mean_c = EXCLUDED.temp_mean_c
        """)
        postgres_connection.commit()
        
        response = requests.get(
            f"{api_client}/api/v1/features/temperature",
            params={'station_id': 433}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # All items should be for station 433
        assert all(item['station_id'] == 433 for item in data['items'])
        
        print(f"\n✓ Station filter: {len(data['items'])} records for station 433")
    
    def test_filter_by_year_quarter(self, api_client, postgres_connection, seed_station_metadata):
        """Test filtering by year and quarter."""
        cursor = postgres_connection.cursor()
        cursor.execute("""
            INSERT INTO quarterly_temperature_features (
                station_id, year, quarter, dataset_version,
                temp_mean_c, temp_min_c, temp_max_c, temp_range_c,
                heating_degree_days, cooling_degree_days,
                frost_hours, freeze_thaw_cycles,
                hours_below_0c, hours_above_25c,
                temp_variance, missing_hours_pct
            ) VALUES (
                433, 2023, 3, 'v1.0.0',
                17.8, 7.5, 28.2, 20.7,
                15.0, 200.0,
                0, 0,
                0, 95,
                68.4, 0.2
            )
            ON CONFLICT (station_id, year, quarter) DO UPDATE SET
                temp_mean_c = EXCLUDED.temp_mean_c
        """)
        postgres_connection.commit()
        
        response = requests.get(
            f"{api_client}/api/v1/features/temperature",
            params={'year': 2023, 'quarter': 3}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # All items should match filter
        for item in data['items']:
            assert item['year'] == 2023
            assert item['quarter'] == 3
        
        print(f"\n✓ Year/quarter filter: {len(data['items'])} records for 2023 Q3")
    
    def test_filter_by_year_range(self, api_client, postgres_connection, seed_station_metadata):
        """Test filtering by year range."""
        cursor = postgres_connection.cursor()
        
        # Insert multiple years
        for year in [2021, 2022, 2023]:
            cursor.execute("""
                INSERT INTO quarterly_temperature_features (
                    station_id, year, quarter, dataset_version,
                    temp_mean_c, temp_min_c, temp_max_c, temp_range_c,
                    heating_degree_days, cooling_degree_days,
                    frost_hours, freeze_thaw_cycles,
                    hours_below_0c, hours_above_25c,
                    temp_variance, missing_hours_pct
                ) VALUES (
                    433, %s, 1, 'v1.0.0',
                    2.0, -10.0, 14.0, 24.0,
                    330.0, 0.0,
                    420, 15,
                    420, 0,
                    45.0, 1.0
                )
                ON CONFLICT (station_id, year, quarter) DO UPDATE SET
                    temp_mean_c = EXCLUDED.temp_mean_c
            """, (year,))
        
        postgres_connection.commit()
        
        response = requests.get(
            f"{api_client}/api/v1/features/temperature",
            params={'min_year': 2022, 'max_year': 2023}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # All items should be within range
        for item in data['items']:
            assert 2022 <= item['year'] <= 2023
        
        print(f"\n✓ Year range filter: {len(data['items'])} records for 2022-2023")
    
    def test_station_time_series(self, api_client, postgres_connection, seed_station_metadata):
        """Test getting time series for specific station."""
        cursor = postgres_connection.cursor()
        
        # Insert time series data
        quarters = [(2023, 1), (2023, 2), (2023, 3), (2023, 4)]
        for year, quarter in quarters:
            cursor.execute("""
                INSERT INTO quarterly_temperature_features (
                    station_id, year, quarter, dataset_version,
                    temp_mean_c, temp_min_c, temp_max_c, temp_range_c,
                    heating_degree_days, cooling_degree_days,
                    frost_hours, freeze_thaw_cycles,
                    hours_below_0c, hours_above_25c,
                    temp_variance, missing_hours_pct
                ) VALUES (
                    433, %s, %s, 'v1.0.0',
                    5.0 + (%s * 5.0), -5.0, 15.0 + (%s * 5.0), 20.0,
                    300.0 - (%s * 50.0), %s * 20.0,
                    350 - (%s * 80), 10 - (%s * 2),
                    350 - (%s * 80), %s * 25,
                    50.0, 1.0
                )
                ON CONFLICT (station_id, year, quarter) DO UPDATE SET
                    temp_mean_c = EXCLUDED.temp_mean_c
            """, (year, quarter, quarter, quarter, quarter, quarter, quarter, quarter, quarter, quarter))
        
        postgres_connection.commit()
        
        response = requests.get(
            f"{api_client}/api/v1/features/temperature/stations/433"
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data['station_id'] == 433
        assert 'time_series' in data
        assert len(data['time_series']) >= 4
        
        # Verify chronological order
        years_quarters = [(item['year'], item['quarter']) for item in data['time_series']]
        assert years_quarters == sorted(years_quarters)
        
        print(f"\n✓ Time series: {len(data['time_series'])} quarters for station 433")
    
    def test_all_product_types(self, api_client):
        """Test that all product endpoints are accessible."""
        products = ['temperature', 'precipitation', 'wind', 'pressure', 'humidity']
        
        for product in products:
            response = requests.get(f"{api_client}/api/v1/features/{product}")
            
            assert response.status_code == 200, f"Product {product} failed"
            data = response.json()
            
            assert 'items' in data
            assert 'total' in data
            
            print(f"  ✓ {product}: {data['total']} records")
        
        print(f"\n✓ All {len(products)} product types accessible")
    
    def test_feature_statistics(self, api_client, postgres_connection, seed_station_metadata):
        """Test feature statistics endpoint."""
        # Ensure we have data
        cursor = postgres_connection.cursor()
        cursor.execute("""
            INSERT INTO quarterly_temperature_features (
                station_id, year, quarter, dataset_version,
                temp_mean_c, temp_min_c, temp_max_c, temp_range_c,
                heating_degree_days, cooling_degree_days,
                frost_hours, freeze_thaw_cycles,
                hours_below_0c, hours_above_25c,
                temp_variance, missing_hours_pct
            ) VALUES (
                433, 2023, 4, 'v1.0.0',
                4.5, -6.2, 16.8, 23.0,
                280.0, 5.0,
                320, 14,
                320, 2,
                52.1, 1.2
            )
            ON CONFLICT (station_id, year, quarter) DO UPDATE SET
                temp_mean_c = EXCLUDED.temp_mean_c
        """)
        postgres_connection.commit()
        
        response = requests.get(f"{api_client}/api/v1/features/temperature/stats")
        
        assert response.status_code == 200
        data = response.json()
        
        assert 'product_type' in data
        assert 'total_records' in data
        assert 'station_count' in data
        assert 'year_range' in data
        
        print(f"\n✓ Statistics: {data['total_records']} records, {data['station_count']} stations")


class TestAPIPerformance:
    """Test API performance characteristics."""
    
    def test_response_time_headers(self, api_client):
        """Test that response time headers are included."""
        response = requests.get(f"{api_client}/api/v1/stations?limit=10")
        
        assert response.status_code == 200
        assert 'X-Response-Time' in response.headers
        assert 'X-Request-ID' in response.headers
        
        response_time = response.headers['X-Response-Time']
        request_id = response.headers['X-Request-ID']
        
        print(f"\n✓ Response headers: time={response_time}, request_id={request_id}")
    
    def test_pagination_limit_enforcement(self, api_client):
        """Test that pagination limits are enforced."""
        # Request more than max limit
        response = requests.get(
            f"{api_client}/api/v1/stations",
            params={'limit': 10000}  # Way above typical max
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Should be capped at max limit (typically 1000)
        assert data['limit'] <= 1000
        assert len(data['items']) <= data['limit']
        
        print(f"\n✓ Limit enforcement: requested 10000, got {data['limit']}")
    
    def test_concurrent_requests(self, api_client):
        """Test API handles concurrent requests."""
        import concurrent.futures
        
        def make_request(endpoint):
            response = requests.get(f"{api_client}{endpoint}")
            return response.status_code == 200, response.elapsed.total_seconds()
        
        endpoints = [
            "/api/v1/stations?limit=10",
            "/api/v1/features/temperature?limit=10",
            "/api/v1/features/precipitation?limit=10",
            "/api/v1/features/wind?limit=10",
            "/api/v1/features/pressure?limit=10",
        ]
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            results = list(executor.map(make_request, endpoints))
        
        successes = [r[0] for r in results]
        times = [r[1] for r in results]
        
        assert all(successes), f"Only {sum(successes)}/{len(successes)} requests succeeded"
        
        avg_time = sum(times) / len(times)
        max_time = max(times)
        
        print(f"\n✓ Concurrent requests: {len(results)} requests, avg={avg_time:.3f}s, max={max_time:.3f}s")


class TestAPIErrorHandling:
    """Test API error handling."""
    
    def test_invalid_station_id_type(self, api_client):
        """Test handling of invalid station ID data type."""
        response = requests.get(f"{api_client}/api/v1/stations/not_a_number")
        
        assert response.status_code == 422  # Validation error
        
        print(f"\n✓ Invalid station ID rejected with 422")
    
    def test_invalid_query_parameters(self, api_client):
        """Test handling of invalid query parameters."""
        # Invalid quarter (should be 1-4)
        response = requests.get(
            f"{api_client}/api/v1/features/temperature",
            params={'quarter': 5}
        )
        
        assert response.status_code == 422
        
        # Invalid limit (negative)
        response = requests.get(
            f"{api_client}/api/v1/stations",
            params={'limit': -10}
        )
        
        assert response.status_code == 422
        
        print(f"\n✓ Invalid query parameters rejected")
    
    def test_unknown_product_type(self, api_client):
        """Test handling of unknown product type."""
        response = requests.get(f"{api_client}/api/v1/features/invalid_product")
        
        assert response.status_code == 404
        
        print(f"\n✓ Unknown product type returns 404")
    
    def test_malformed_requests(self, api_client):
        """Test handling of malformed requests."""
        # Missing required path parameter (caught by routing)
        response = requests.get(f"{api_client}/api/v1/features/")
        
        # Should either redirect or return 404
        assert response.status_code in [404, 307]  # 307 is redirect
        
        print(f"\n✓ Malformed requests handled gracefully")
