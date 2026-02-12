# WeatherInsight Delivery API

## Purpose
FastAPI REST service exposing quarterly weather features from curated PostgreSQL tables. Provides paginated, filterable access to temperature, precipitation, wind, pressure, and humidity data from German DWD weather stations.

## Architecture

### Components
- **FastAPI Application**: High-performance async web framework with automatic OpenAPI docs
- **SQLAlchemy ORM**: Database models and query abstraction
- **Pydantic**: Request/response validation and serialization
- **Prometheus**: Metrics collection for monitoring
- **PostgreSQL**: Connection to curated feature tables

### Endpoints

#### Health & Info
- `GET /` - API root information
- `GET /health` - Health check with database connectivity
- `GET /api/v1/info` - API configuration and available endpoints
- `GET /metrics` - Prometheus metrics

#### Stations
- `GET /api/v1/stations` - List all stations (paginated, filterable)
- `GET /api/v1/stations/{station_id}` - Get station details
- `GET /api/v1/stations/{station_id}/summary` - Station summary with product counts

#### Features
- `GET /api/v1/features/products` - List available product types
- `GET /api/v1/features/{product}/stats` - Statistics for a product
- `GET /api/v1/features/{product}` - List features with filters
- `GET /api/v1/features/{product}/stations/{station_id}` - Time series for station

**Product Types**: `temperature`, `precipitation`, `wind`, `pressure`, `humidity`

### Query Parameters

#### Pagination
- `limit` (default: 50, max: 1000) - Results per page
- `offset` (default: 0) - Results to skip

#### Filtering (Features)
- `station_id` - Filter by specific station
- `year` - Filter by specific year
- `quarter` - Filter by quarter (1-4)
- `min_year` - Minimum year (inclusive)
- `max_year` - Maximum year (inclusive)

#### Filtering (Stations)
- `is_active` - Filter by active status (true/false)
- `state` - Filter by German state name

## Project Structure

```
services/api/
├── app/
│   ├── __init__.py          # Package initialization
│   ├── main.py              # FastAPI application entry point
│   ├── config.py            # Configuration management
│   ├── database.py          # Database connection and session
│   ├── models.py            # SQLAlchemy ORM and Pydantic models
│   ├── crud.py              # Database query operations
│   └── routers/
│       ├── __init__.py
│       ├── health.py        # Health check endpoints
│       ├── stations.py      # Station metadata endpoints
│       └── features.py      # Feature data endpoints
├── tests/
│   ├── conftest.py          # Test fixtures and configuration
│   ├── test_health.py       # Health endpoint tests
│   ├── test_stations.py     # Station endpoint tests
│   └── test_features.py     # Feature endpoint tests
├── Dockerfile               # Container image
├── requirements.txt         # Python dependencies
└── README.md               # This file
```

## Data Models

### Common Fields (All Features)
- `feature_id` - Unique identifier
- `station_id`, `station_name`, `latitude`, `longitude`, `elevation_m`
- `year`, `quarter` (1-4), `quarter_start`, `quarter_end`
- `dataset_version`, `computed_at`
- `count_observations`, `count_missing`, `missingness_ratio`

### Temperature Features (14 additional)
- Statistics: `mean_temp_c`, `median_temp_c`, `min_temp_c`, `max_temp_c`, `stddev_temp_c`, `q25_temp_c`, `q75_temp_c`
- Derived: `heating_degree_days`, `cooling_degree_days`, `frost_hours`, `freeze_thaw_cycles`

### Precipitation Features (12 additional)
- Statistics: `total_precip_mm`, `mean_hourly_precip_mm`, `median_precip_mm`, `max_hourly_precip_mm`, `stddev_precip_mm`, `q75_precip_mm`, `q95_precip_mm`
- Derived: `wet_hours`, `dry_hours`, `max_dry_spell_hours`, `max_wet_spell_hours`, `heavy_precip_hours`

### Wind Features (11 additional)
- Statistics: `mean_wind_speed_ms`, `median_wind_speed_ms`, `min_wind_speed_ms`, `max_wind_speed_ms`, `stddev_wind_speed_ms`, `q75_wind_speed_ms`, `q95_wind_speed_ms`
- Derived: `gust_hours`, `calm_hours`, `prevailing_direction`, `direction_variability`

### Pressure Features (10 additional)
- Statistics: `mean_pressure_hpa`, `median_pressure_hpa`, `min_pressure_hpa`, `max_pressure_hpa`, `stddev_pressure_hpa`, `q25_pressure_hpa`, `q75_pressure_hpa`
- Derived: `pressure_range_hpa`, `high_pressure_hours`, `low_pressure_hours`

### Humidity Features (9 additional)
- Statistics: `mean_humidity_pct`, `median_humidity_pct`, `min_humidity_pct`, `max_humidity_pct`, `stddev_humidity_pct`, `q25_humidity_pct`, `q75_humidity_pct`
- Derived: `high_humidity_hours`, `low_humidity_hours`

## Development

### Local Setup

1. **Install dependencies**:
```bash
cd services/api
pip install -r requirements.txt
```

2. **Configure environment**:
```bash
export POSTGRES_HOST=localhost
export POSTGRES_PORT=5432
export POSTGRES_DB=weatherinsight
export POSTGRES_USER=weatherinsight
export POSTGRES_PASSWORD=weatherinsight123
```

3. **Run application**:
```bash
# Development mode with auto-reload
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Production mode
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

4. **Access documentation**:
- Interactive API docs: http://localhost:8000/docs
- Alternative docs: http://localhost:8000/redoc
- OpenAPI schema: http://localhost:8000/openapi.json

### Testing

Run the test suite:
```bash
# All tests
pytest tests/ -v

# Specific test file
pytest tests/test_features.py -v

# With coverage
pytest tests/ --cov=app --cov-report=html
```

### Docker

Build and run with Docker:
```bash
# Build image
docker build -t weatherinsight-api:latest .

# Run container
docker run -d \
  --name weatherinsight-api \
  --network weatherinsight \
  -p 8000:8000 \
  -e POSTGRES_HOST=postgres \
  -e POSTGRES_PORT=5432 \
  -e POSTGRES_DB=weatherinsight \
  -e POSTGRES_USER=weatherinsight \
  -e POSTGRES_PASSWORD=weatherinsight123 \
  weatherinsight-api:latest
```

## Usage Examples

### List All Stations
```bash
curl http://localhost:8000/api/v1/stations?limit=10
```

### Get Specific Station
```bash
curl http://localhost:8000/api/v1/stations/433
```

### Get Temperature Features for 2023 Q1
```bash
curl "http://localhost:8000/api/v1/features/temperature?year=2023&quarter=1"
```

### Get Station Time Series
```bash
curl http://localhost:8000/api/v1/features/temperature/stations/433
```

### Filter by Year Range
```bash
curl "http://localhost:8000/api/v1/features/precipitation?min_year=2020&max_year=2023"
```

### Pagination
```bash
curl "http://localhost:8000/api/v1/features/wind?limit=20&offset=40"
```

## Python Client Example

```python
import requests

# Base URL
base_url = "http://localhost:8000"

# Get all stations
response = requests.get(f"{base_url}/api/v1/stations")
stations = response.json()

# Get temperature features for specific station
station_id = 433
response = requests.get(
    f"{base_url}/api/v1/features/temperature/stations/{station_id}"
)
features = response.json()

# Filter by year and quarter
params = {"year": 2023, "quarter": 1, "limit": 100}
response = requests.get(
    f"{base_url}/api/v1/features/temperature",
    params=params
)
data = response.json()
```

## Configuration

Environment variables (see `app/config.py`):

### PostgreSQL
- `POSTGRES_HOST` (default: "postgres")
- `POSTGRES_PORT` (default: 5432)
- `POSTGRES_DB` (default: "weatherinsight")
- `POSTGRES_USER` (default: "weatherinsight")
- `POSTGRES_PASSWORD` (default: "weatherinsight123")

### API Settings
- `API_TITLE` (default: "WeatherInsight API")
- `API_VERSION` (default: "1.0.0")
- `DEFAULT_PAGE_SIZE` (default: 50)
- `MAX_PAGE_SIZE` (default: 1000)

### Database Pool
- `POOL_SIZE` (default: 10)
- `MAX_OVERFLOW` (default: 20)
- `POOL_TIMEOUT` (default: 30)
- `POOL_RECYCLE` (default: 3600)

### Logging
- `LOG_LEVEL` (default: "INFO")

## Monitoring

### Prometheus Metrics

Access metrics at `/metrics`:
```bash
curl http://localhost:8000/metrics
```

**Available Metrics**:
- `weatherinsight_api_requests_total` - Total requests by method, endpoint, status
- `weatherinsight_api_request_duration_seconds` - Request latency histogram
- `weatherinsight_api_db_query_duration_seconds` - Database query duration

### Health Checks

Monitor service health:
```bash
# Simple health check
curl http://localhost:8000/health

# Expected response
{
  "status": "healthy",
  "database": "connected",
  "message": "WeatherInsight API is running"
}
```

## Performance

### SLA Targets
- API uptime: 99%
- P95 response time: <500ms for single-station queries
- P95 response time: <2s for multi-station queries
- Error rate: <5%

### Optimization
- Database queries use indexed columns (`station_id`, `year`, `quarter`)
- Connection pooling (10 connections, 20 overflow)
- Pagination enforced (max 1000 records per request)
- Connection pre-ping for reliability
- SQLAlchemy query optimization with selective field loading

## Troubleshooting

### Database Connection Failed
```bash
# Check PostgreSQL connectivity
docker exec postgres pg_isready -U weatherinsight

# Check network
docker network inspect weatherinsight
```

### Slow Queries
- Enable SQL logging: Set `echo=True` in `database.py`
- Check indexes: Ensure indexes exist on `station_id`, `year`, `quarter`
- Monitor metrics: Check `/metrics` for query duration

### Import Errors
```bash
# Ensure working directory is services/api
cd services/api

# Run with Python module syntax
python -m app.main
```

## Integration

The API service integrates with:
- **PostgreSQL**: Reads curated feature tables
- **Prometheus**: Exports metrics for monitoring
- **Grafana**: Visualizes metrics (via Prometheus)
- **Airflow**: Triggered by orchestration pipeline
- **Training Jobs**: Downstream ML model consumers

## Next Steps

1. **Add authentication**: API keys or OAuth2
2. **Add rate limiting**: Prevent abuse
3. **Add caching**: Redis for frequently accessed data
4. **Add async queries**: Use asyncpg for better performance
5. **Add GraphQL**: Alternative query interface
6. **Add webhooks**: Notify on new data availability
