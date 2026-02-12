# WeatherInsight Testing Strategy

## Overview

This document outlines the comprehensive testing strategy for the WeatherInsight data pipeline, covering unit tests, integration tests, end-to-end tests, and performance testing.

## Test Pyramid

WeatherInsight follows the test pyramid principle with a focus on fast, isolated unit tests at the base and fewer, slower integration and E2E tests at the top.

### Test Distribution

```
           /\
          /  \    E2E Tests (42 tests)
         /    \   - Full pipeline flows
        /------\  - API integration
       /        \ - Data quality validation
      /          \
     / Integration\ (50+ tests)  
    /     Tests    \- Service boundaries
   /                \- Database interactions
  /------------------\
 /                    \
/   Unit Tests (100+)  \ - Business logic
------------------------  - Feature calculators
                          - Parsers & cleaners
                          - API endpoints
```

### Current Test Coverage

| Component | Unit Tests | Integration Tests | E2E Tests | Total |
|-----------|------------|-------------------|-----------|-------|
| API Service | 31 | 17 | 14 | 62 |
| Ingestion | 15 | 5 | 3 | 23 |
| Processing | 25 | 8 | 3 | 36 |
| Aggregation | 23 | 0 | 3 | 26 |
| Metadata | 12 | 0 | 0 | 12 |
| **Total** | **106** | **30** | **23** | **159** |

**Overall Coverage**: ~85% of critical paths

## Unit Testing

### Purpose
Test individual functions and classes in isolation with mocked dependencies.

### Tools
- **pytest**: Test runner and framework
- **unittest.mock**: Mocking external dependencies
- **pytest-asyncio**: Async test support

### Patterns

#### Service Unit Tests
```python
# services/api/tests/test_features.py
def test_list_temperature_features(client, sample_features):
    """Test listing temperature features with pagination."""
    response = client.get("/api/v1/features/temperature?limit=10")
    
    assert response.status_code == 200
    data = response.json()
    assert len(data['items']) <= 10
    assert 'total' in data
```

#### Spark Job Unit Tests
```python
# services/processing/tests/test_parser.py
def test_parse_temperature_data(spark_session, sample_dwd_data):
    """Test parsing DWD temperature data format."""
    df = parse_temperature_file(spark_session, sample_dwd_data)
    
    assert df.count() > 0
    assert 'temperature_c' in df.columns
    assert df.filter(col('temperature_c').isNull()).count() < df.count() * 0.1
```

### Running Unit Tests
```bash
# Run all unit tests
pytest -v

# Run specific service tests
cd services/api
pytest tests/ -v

# Run with coverage
pytest --cov=app --cov-report=html

# Run tests matching pattern
pytest -k "test_temperature" -v
```

## Integration Testing

### Purpose
Test interactions between components, database queries, and external service calls.

### Patterns

#### Database Integration Tests
```python
# services/api/tests/test_api_integration.py
def test_feature_query_with_filters(postgres_connection, seed_data):
    """Test querying features with multiple filters."""
    cursor = postgres_connection.cursor()
    cursor.execute("""
        SELECT COUNT(*) FROM quarterly_temperature_features
        WHERE station_id = 433 AND year = 2023
    """)
    count = cursor.fetchone()[0]
    
    response = client.get(
        "/api/v1/features/temperature",
        params={'station_id': 433, 'year': 2023}
    )
    
    assert response.json()['total'] == count
```

#### MinIO Integration Tests
```python
# services/ingestion/tests/test_integration.py
@pytest.mark.integration
def test_upload_to_minio(s3_client):
    """Test uploading raw data to MinIO."""
    if not os.getenv("RUN_INTEGRATION_TESTS"):
        pytest.skip("Integration tests disabled")
    
    s3_client.put_object(
        Bucket='weatherinsight-raw',
        Key='test/sample.txt',
        Body=b'test data'
    )
    
    obj = s3_client.get_object(
        Bucket='weatherinsight-raw',
        Key='test/sample.txt'
    )
    
    assert obj['Body'].read() == b'test data'
```

### Running Integration Tests
```bash
# Enable integration tests
export RUN_INTEGRATION_TESTS=true

# Run integration tests only
pytest -m integration -v

# Run with Docker Compose stack
docker compose up -d
pytest -m integration -v
docker compose down -v
```

## End-to-End Testing

### Purpose
Validate complete workflows from data ingestion through API delivery using real services.

### Test Suites

#### 1. Full Pipeline Tests (14 tests)
**File**: `tests/e2e/test_full_pipeline.py`

Tests complete data flow:
1. Ingestion: Upload sample DWD data to MinIO
2. Processing: Parse and stage data
3. Aggregation: Compute quarterly features
4. API: Query features via REST endpoints

**Key Tests**:
- `test_01_ingestion_service` - Raw data upload
- `test_04_api_service_health` - API connectivity
- `test_09_monitoring_prometheus` - Metrics scraping
- `test_11_end_to_end_data_flow` - Complete pipeline

#### 2. Data Quality Tests (11 tests)
**File**: `tests/e2e/test_data_quality.py`

Validates data quality at all stages:
- Raw data structure conformance
- Feature value ranges
- Logical consistency (max >= mean >= min)
- Cross-table referential integrity
- Quality threshold validations

**Key Tests**:
- `test_feature_value_ranges` - Value validation
- `test_feature_consistency` - Logical relationships
- `test_cross_table_consistency` - Foreign keys

#### 3. API Integration Tests (17 tests)
**File**: `tests/e2e/test_api_integration.py`

Tests API with real database:
- All endpoints with various parameters
- Pagination edge cases
- Filter combinations
- Concurrent request handling
- Error responses

**Key Tests**:
- `test_filter_by_year_range` - Complex filtering
- `test_concurrent_requests` - Load handling
- `test_api_validates_input` - Input validation

### Running E2E Tests
```bash
# Start all services
docker compose up -d

# Run all E2E tests
cd tests/e2e
pytest -v

# Run specific test suite
pytest test_full_pipeline.py -v

# Keep services running after tests
export E2E_TEARDOWN=false
pytest -v

# Teardown after tests
export E2E_TEARDOWN=true
pytest -v
```

### E2E Test Execution Time
- **test_full_pipeline.py**: ~60s
- **test_data_quality.py**: ~30s
- **test_api_integration.py**: ~45s
- **Total**: ~2-3 minutes

## Performance Testing

### Load Testing

Use **Locust** or **k6** for load testing the API:

```python
# tests/performance/locustfile.py
from locust import HttpUser, task, between

class WeatherInsightUser(HttpUser):
    wait_time = between(1, 3)
    
    @task(3)
    def list_stations(self):
        self.client.get("/api/v1/stations?limit=50")
    
    @task(2)
    def get_temperature_features(self):
        self.client.get(
            "/api/v1/features/temperature",
            params={'year': 2023, 'quarter': 1}
        )
    
    @task(1)
    def get_station_detail(self):
        self.client.get("/api/v1/stations/433")
```

**Run load test**:
```bash
locust -f tests/performance/locustfile.py --host=http://localhost:8000 --users 100 --spawn-rate 10
```

### Performance Benchmarks

Target performance metrics:

| Endpoint | P50 Latency | P95 Latency | P99 Latency | Throughput |
|----------|-------------|-------------|-------------|------------|
| `/stations` | <100ms | <200ms | <500ms | 100 req/s |
| `/features/*` | <200ms | <500ms | <1s | 50 req/s |
| `/stations/{id}` | <50ms | <100ms | <200ms | 200 req/s |

### Database Query Performance
```sql
-- Check slow queries
SELECT query, mean_exec_time, calls
FROM pg_stat_statements
WHERE mean_exec_time > 1000  -- > 1 second
ORDER BY mean_exec_time DESC
LIMIT 10;
```

## Continuous Integration

### GitHub Actions Workflow

```yaml
name: CI Pipeline

on: [push, pull_request]

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Run unit tests
        run: |
          pip install -r services/api/requirements.txt pytest
          pytest services/api/tests/ -v
  
  integration-tests:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_PASSWORD: test
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    steps:
      - uses: actions/checkout@v3
      - name: Run integration tests
        run: |
          export RUN_INTEGRATION_TESTS=true
          pytest -m integration -v
  
  e2e-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Start services
        run: docker compose up -d
      - name: Wait for health
        run: sleep 60
      - name: Run E2E tests
        run: |
          cd tests/e2e
          pytest -v
      - name: Teardown
        if: always()
        run: docker compose down -v
```

## Test Data Management

### Fixtures

Comprehensive fixtures in `tests/e2e/conftest.py`:

```python
@pytest.fixture(scope="session")
def sample_dwd_data() -> Dict[str, List[str]]:
    """Generate realistic DWD data for testing."""
    return {
        "air_temperature": generate_temperature_data(...),
        "precipitation": generate_precipitation_data(...),
        ...
    }
```

### Test Database

- Use in-memory SQLite for API unit tests
- Use PostgreSQL test container for integration tests
- Use Docker Compose stack for E2E tests

### Data Cleanup

```python
@pytest.fixture
def clean_database(postgres_connection):
    """Clean feature tables before each test."""
    cursor = postgres_connection.cursor()
    for table in FEATURE_TABLES:
        cursor.execute(f"TRUNCATE TABLE {table} CASCADE")
    postgres_connection.commit()
    yield
    postgres_connection.rollback()
```

## Best Practices

### 1. Test Naming
- Use descriptive names: `test_feature_does_specific_thing`
- Group related tests in classes: `TestTemperatureFeatures`

### 2. Test Independence
- Each test should be runnable independently
- Use fixtures for setup/teardown
- Avoid test interdependencies

### 3. Assertions
- Use specific assertions: `assert value == expected`
- Add helpful failure messages: `assert count > 0, f"Expected data, got {count}"`

### 4. Mocking
- Mock external dependencies (HTTP calls, file I/O)
- Don't mock the system under test
- Use realistic mock data

### 5. Test Coverage
- Aim for >80% code coverage
- Focus on critical paths first
- Don't sacrifice quality for coverage percentage

## Troubleshooting

### Common Issues

#### 1. Database Connection Failures
```bash
# Check PostgreSQL is running
docker compose ps postgres

# Verify connection
docker exec postgres psql -U weatherinsight -d weatherinsight -c "SELECT 1"
```

#### 2. MinIO Access Issues
```bash
# Check MinIO health
curl http://localhost:9000/minio/health/live

# List buckets
docker exec minio mc ls minio/
```

#### 3. Test Timeouts
Increase timeouts in `conftest.py`:
```python
def wait_for_services(timeout: int = 300):  # 5 minutes
    ...
```

#### 4. Flaky Tests
- Add retries for network-dependent tests
- Use proper wait conditions instead of fixed sleeps
- Increase health check intervals

## Related Documentation

- [E2E Test README](../tests/e2e/README.md) - Detailed E2E test guide
- [API Documentation](../services/api/README.md) - API endpoint reference
- [Monitoring Guide](./MONITORING_GUIDE.md) - Observability setup
- [Runbook](./runbook.md) - Operational procedures
