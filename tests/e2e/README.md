# End-to-End Tests

Comprehensive end-to-end tests for the complete WeatherInsight pipeline.

## Overview

These tests validate the entire system from ingestion through the API:

1. **test_full_pipeline.py** - Complete pipeline flow (ingestion → processing → aggregation → API)
2. **test_data_quality.py** - Data quality validation across raw/staged/curated zones
3. **test_api_integration.py** - API integration tests with real PostgreSQL data

## Prerequisites

### Services Required
All tests require a running Docker Compose stack:

```bash
docker compose up -d
```

The following services must be healthy:
- PostgreSQL (port 5432)
- MinIO (port 9000)
- FastAPI (port 8000)
- Prometheus (port 9090)
- Grafana (port 3002)

### Python Dependencies
```bash
pip install pytest requests boto3 psycopg2-binary
```

## Running Tests

### Run All E2E Tests
```bash
cd tests/e2e
pytest -v
```

### Run Specific Test Suite
```bash
pytest test_full_pipeline.py -v
pytest test_data_quality.py -v
pytest test_api_integration.py -v
```

### Run Specific Test
```bash
pytest test_full_pipeline.py::TestFullPipeline::test_01_ingestion_service -v
```

### Keep Services Running After Tests
By default, the Docker Compose stack is left running after tests complete. To tear down:

```bash
export E2E_TEARDOWN=true
pytest -v
```

Or manually:
```bash
docker compose down -v
```

## Test Architecture

### Fixtures (conftest.py)

#### Session-Scoped
- **docker_compose**: Manages Docker Compose stack lifecycle
- **postgres_connection**: Provides database connection
- **sample_dwd_data**: Generates realistic DWD data for testing

#### Function-Scoped
- **clean_database**: Truncates feature tables before each test
- **seed_station_metadata**: Inserts test station (ID 433 - Erfurt)
- **api_client**: Provides API base URL

### Test Data

Tests use **station 433 (Erfurt-Weimar)** with synthetic data:
- **Date range**: 2023-01-01 to 2023-01-07 (one week)
- **Products**: temperature, precipitation, wind, pressure, moisture
- **Granularity**: Hourly observations (168 hours)
- **Pattern**: Realistic winter weather with diurnal cycles

Generated data includes:
- Temperature: -5°C to +10°C with daily variation
- Precipitation: Intermittent rain events
- Wind: Prevailing westerly winds (2-6 m/s)
- Pressure: High pressure system (1015-1023 hPa)
- Humidity: 70-95% inversely related to temperature

## Test Coverage

### Pipeline Flow (test_full_pipeline.py)
✅ Ingestion service uploads raw data to MinIO  
✅ Processing service accesses raw data  
✅ Aggregation service creates feature tables  
✅ API health check and database connectivity  
✅ API stations endpoint returns seeded data  
✅ API products endpoint lists all 5 types  
✅ API OpenAPI documentation accessible  
✅ API Prometheus metrics endpoint  
✅ Prometheus scraping configured targets  
✅ Grafana health and datasources  
✅ End-to-end data flow (DB → API → Response)  
✅ Pipeline resilience and error handling  
✅ API input validation  
✅ Database connection pooling under load  

**Total: 14 tests**

### Data Quality (test_data_quality.py)
✅ Raw data structure conforms to DWD format  
✅ All product types present in raw zone  
✅ Raw data has required metadata  
✅ Feature table schemas correct  
✅ Feature values within expected ranges  
✅ Logical consistency (max >= mean >= min)  
✅ No unexpected NULLs in critical columns  
✅ Cross-table consistency (station metadata)  
✅ Row count threshold validation  
✅ Null percentage threshold validation  
✅ Station coverage threshold validation  

**Total: 11 tests**

### API Integration (test_api_integration.py)
✅ Station listing with pagination  
✅ Station detail by ID  
✅ Station not found handling  
✅ Station summary with feature counts  
✅ List temperature features  
✅ Filter by station ID  
✅ Filter by year and quarter  
✅ Filter by year range  
✅ Station time series (chronological)  
✅ All 5 product type endpoints  
✅ Feature statistics  
✅ Response time headers  
✅ Pagination limit enforcement  
✅ Concurrent request handling  
✅ Invalid input validation  
✅ Unknown product type handling  
✅ Malformed request handling  

**Total: 17 tests**

**Grand Total: 42 E2E tests**

## Test Execution Time

Typical execution times:
- **test_full_pipeline.py**: ~60s (includes service health checks)
- **test_data_quality.py**: ~30s (database queries)
- **test_api_integration.py**: ~45s (API calls and concurrent tests)

**Total runtime**: ~2-3 minutes

## Continuous Integration

### GitHub Actions Example
```yaml
name: E2E Tests

on: [push, pull_request]

jobs:
  e2e:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v3
      
      - name: Start Docker Compose
        run: docker compose up -d
      
      - name: Wait for services
        run: sleep 30
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          pip install pytest requests boto3 psycopg2-binary
      
      - name: Run E2E tests
        run: |
          cd tests/e2e
          pytest -v --tb=short
      
      - name: Tear down
        if: always()
        run: docker compose down -v
```

## Troubleshooting

### Services Not Healthy
If tests fail due to service health checks:

```bash
# Check service status
docker compose ps

# Check service logs
docker compose logs postgres
docker compose logs api
docker compose logs minio

# Restart services
docker compose restart
```

### Database Connection Errors
```bash
# Verify PostgreSQL is accepting connections
docker exec postgres psql -U weatherinsight -d weatherinsight -c "SELECT 1"

# Check if tables exist
docker exec postgres psql -U weatherinsight -d weatherinsight -c "\dt"
```

### MinIO Connection Errors
```bash
# Verify MinIO is accessible
curl http://localhost:9000/minio/health/live

# Check buckets
docker exec minio mc ls minio/
```

### API Not Responding
```bash
# Check API health
curl http://localhost:8000/health

# Check API logs
docker compose logs api

# Restart API
docker compose restart api
```

### Tests Timing Out
Increase timeouts in `conftest.py`:

```python
def wait_for_services(timeout: int = 300):  # Increase from 180s
    ...
```

## Test Data Cleanup

Tests use the `clean_database` fixture to truncate tables before each test. To manually clean:

```bash
docker exec postgres psql -U weatherinsight -d weatherinsight << 'SQL'
TRUNCATE TABLE quarterly_temperature_features CASCADE;
TRUNCATE TABLE quarterly_precipitation_features CASCADE;
TRUNCATE TABLE quarterly_wind_features CASCADE;
TRUNCATE TABLE quarterly_pressure_features CASCADE;
TRUNCATE TABLE quarterly_humidity_features CASCADE;
TRUNCATE TABLE station_metadata CASCADE;
SQL
```

## Adding New Tests

### Test Structure
```python
class TestNewFeature:
    """Test description."""
    
    def test_something(self, api_client, postgres_connection, seed_station_metadata):
        """Test specific behavior."""
        # Arrange - set up test data
        cursor = postgres_connection.cursor()
        cursor.execute("INSERT INTO ...")
        postgres_connection.commit()
        
        # Act - perform action
        response = requests.get(f"{api_client}/endpoint")
        
        # Assert - verify results
        assert response.status_code == 200
        data = response.json()
        assert data['field'] == expected_value
        
        print(f"\n✓ Test passed: {result}")
```

### Best Practices
1. Use descriptive test names: `test_feature_does_specific_thing`
2. Always clean up data with fixtures or transactions
3. Print informative success messages
4. Test both success and failure cases
5. Use realistic test data patterns
6. Document expected behavior in docstrings

## Related Documentation

- [Testing Strategy](../../docs/TESTING_STRATEGY.md) - Overall testing approach
- [API Documentation](../../services/api/README.md) - API endpoint reference
- [Runbook](../../docs/runbook.md) - Operational procedures
- [Data Contracts](../../docs/data-contracts/) - Schema definitions
