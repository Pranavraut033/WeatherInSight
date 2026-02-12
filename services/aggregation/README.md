# WeatherInsight Aggregation Service

Computes quarterly statistical features from staged parquet data and writes to PostgreSQL curated feature tables.

## Overview

The Aggregation Service is part of the WeatherInsight data pipeline, responsible for:

- Reading cleaned/staged hourly weather observations from MinIO (S3)
- Computing quarterly statistical features for 5 weather product types
- Joining with station metadata for denormalized feature tables
- Writing curated features to PostgreSQL
- Tracking dataset versions and lineage through the metadata service

## Architecture

```
┌─────────────┐
│  MinIO/S3   │
│   Staged    │◄─── Parquet files partitioned by year/month
│   Parquet   │
└──────┬──────┘
       │
       │ Read by product/year/quarter
       ▼
┌─────────────────────┐
│  QuarterlyAggregator│
│  ┌────────────────┐ │
│  │ Feature Calcs  │ │◄─── Temperature, Precip, Wind, Pressure, Humidity
│  └────────────────┘ │
│  ┌────────────────┐ │
│  │ Metadata Join  │ │◄─── Station info (name, lat/lon, elevation)
│  └────────────────┘ │
└──────┬──────────────┘
       │
       │ Quarterly features
       ▼
┌─────────────────┐
│ PostgresWriter  │
│  ┌───────────┐  │
│  │ Upsert    │  │◄─── Delete existing + Append
│  │ Logic     │  │
│  └───────────┘  │
└──────┬──────────┘
       │
       ▼
┌──────────────────────┐
│   PostgreSQL         │
│  Curated Tables:     │
│  • temperature       │
│  • precipitation     │
│  • wind              │
│  • pressure          │
│  • humidity          │
└──────────────────────┘
```

## Components

### 1. Configuration (`config.py`)

Manages environment configuration:
- **S3/MinIO**: Endpoint, credentials, staging bucket
- **PostgreSQL**: Host, credentials, JDBC URL builder
- **Spark**: App name, master, performance tuning

### 2. Feature Calculators (`feature_calculators.py`)

Five specialized calculators, one per product type:

#### Temperature Features
- Basic stats: mean, median, min, max, stddev, quartiles
- Heating Degree Days (HDD): sum of max(18°C - daily_mean, 0)
- Cooling Degree Days (CDD): sum of max(daily_mean - 18°C, 0)
- Frost hours: hours with temp < 0°C
- Freeze-thaw cycles: days crossing 0°C

#### Precipitation Features
- Basic stats: total, mean, median, max, stddev, percentiles
- Wet/dry hours: count of hours with/without precipitation
- Wet/dry spells: maximum consecutive hours
- Heavy precipitation hours: hours > 2.5mm/hour

#### Wind Features
- Speed stats: mean, median, min, max, stddev, percentiles
- Gust hours: hours > 10.8 m/s (Beaufort 6)
- Calm hours: hours < 0.3 m/s
- Prevailing direction: most frequent 16-bin compass direction
- Direction variability: circular standard deviation

#### Pressure Features
- Pressure stats: mean, median, min, max, stddev, quartiles (in Pa)
- Pressure range: max - min
- High/low pressure hours: > 102000 Pa / < 99000 Pa

#### Humidity Features
- Humidity stats: mean, median, min, max, stddev, quartiles (%)
- High/low humidity hours: > 80% / < 30%

All calculators include:
- Quality filtering (`quality_acceptable == True`)
- Observation counts and missingness ratio
- Grouping by station, year, quarter

### 3. Quarterly Aggregator (`aggregator.py`)

Main aggregation logic:
- `load_station_metadata()`: Reads from PostgreSQL, broadcasts for efficient joins
- `load_staged_data()`: Reads parquet filtered by product/year/quarter
- `compute_quarterly_features()`: Orchestrates calculation + metadata join

Adds to each feature record:
- Station metadata (name, lat/lon, elevation)
- Quarter boundaries (start/end timestamps)
- Computed timestamp

### 4. PostgreSQL Writer (`postgres_writer.py`)

Handles writing to curated tables:
- **Product → Table mapping**: Maps product types to PostgreSQL table names
- **Upsert logic**: Deletes existing records for (station, year, quarter, version) before appending
- **JDBC writes**: Uses Spark DataFrame `.write.jdbc()` for bulk inserts
- **Metrics collection**: Returns row counts

### 5. Orchestrator (`orchestrator.py`)

Pipeline coordination and CLI:
- **Spark session setup**: Configures S3, PostgreSQL JDBC, broadcast thresholds
- **Dataset versioning**: Creates curated dataset versions with lineage to staged data
- **Status tracking**: Updates metadata service with PROCESSING → AVAILABLE/FAILED
- **Metrics collection**: Row counts, processing time, quality metrics
- **CLI interface**: Argparse-based command-line tool

## Supported Product Types

| Product Type       | Source Column(s)      | Curated Table                      |
|--------------------|-----------------------|------------------------------------|
| `air_temperature`  | TT_TU, RF_TU          | `quarterly_temperature_features`   |
| `precipitation`    | R1, RS_IND            | `quarterly_precipitation_features` |
| `wind`             | F, D                  | `quarterly_wind_features`          |
| `pressure`         | P_pa, P0_pa           | `quarterly_pressure_features`      |
| `moisture`         | RF_TU, TF_TU          | `quarterly_humidity_features`      |

## Usage

### Docker (Recommended)

Build the image:
```bash
cd services/aggregation
docker build -t weatherinsight-aggregation:latest .
```

Run aggregation for a specific product/quarter:
```bash
docker run --rm \
  --network new-project_weatherinsight \
  -e MINIO_ENDPOINT=http://minio:9000 \
  -e MINIO_ROOT_USER=minioadmin \
  -e MINIO_ROOT_PASSWORD=minioadmin123 \
  -e POSTGRES_HOST=postgres \
  -e POSTGRES_USER=weatherinsight \
  -e POSTGRES_PASSWORD=weatherinsight123 \
  weatherinsight-aggregation:latest \
  python src/orchestrator.py air_temperature 2023 1 v1.0.0
```

### Local Development

Install dependencies:
```bash
pip install -r requirements.txt
```

Run aggregation:
```bash
cd services/aggregation
python src/orchestrator.py air_temperature 2023 1 v1.0.0
```

### Python API

```python
from aggregation.src.config import AggregationConfig
from aggregation.src.orchestrator import AggregationOrchestrator

config = AggregationConfig()
orchestrator = AggregationOrchestrator(config)

try:
    orchestrator.setup_components()
    
    metrics = orchestrator.run_aggregation(
        product_type="air_temperature",
        year=2023,
        quarter=1,
        staged_dataset_version="v1.0.0",
        curated_dataset_version="2023Q1_v1"
    )
    
    print(f"Status: {metrics['status']}")
    print(f"Features written: {metrics['written_count']}")
    
finally:
    orchestrator.cleanup()
```

Factory functions for common use cases:
```python
from aggregation.src.orchestrator import (
    create_temperature_aggregation,
    create_precipitation_aggregation,
    create_wind_aggregation,
    create_pressure_aggregation,
    create_humidity_aggregation,
)

metrics = create_temperature_aggregation(year=2023, quarter=1, staged_version="v1.0.0")
```

## Configuration

Environment variables:

| Variable              | Default                  | Description                     |
|-----------------------|--------------------------|---------------------------------|
| `S3_ENDPOINT`         | `http://minio:9000`      | MinIO/S3 endpoint               |
| `S3_ACCESS_KEY`       | `minioadmin`             | S3 access key                   |
| `S3_SECRET_KEY`       | `minioadmin123`          | S3 secret key                   |
| `STAGING_BUCKET`      | `weatherinsight-staging` | Bucket for staged parquet       |
| `POSTGRES_HOST`       | `postgres`               | PostgreSQL hostname             |
| `POSTGRES_PORT`       | `5432`                   | PostgreSQL port                 |
| `POSTGRES_DB`         | `weatherinsight`         | Database name                   |
| `POSTGRES_USER`       | `weatherinsight`         | Database user                   |
| `POSTGRES_PASSWORD`   | `weatherinsight123`      | Database password               |
| `SPARK_APP_NAME`      | `WeatherInsight-Aggregation` | Spark application name      |
| `SPARK_MASTER`        | `local[*]`               | Spark master URL                |
| `REPARTITION_COUNT`   | `10`                     | Partitions for aggregation      |
| `BROADCAST_THRESHOLD_MB` | `10`                  | Broadcast join threshold (MB)   |

## Testing

Run unit tests:
```bash
cd services/aggregation
pip install -r requirements.txt pytest
pytest tests/ -v
```

Test coverage includes:
- Feature calculator accuracy (23 tests)
- Station metadata join and caching
- Quarter boundary calculations
- Upsert logic and deletion
- Quality filtering and null handling
- PostgreSQL writer with mocked connections

### Test Fixtures

- `sample_temperature_data`: 91 days × 24 hours with daily temperature cycles
- `sample_precipitation_data`: Wet/dry spell patterns
- `sample_wind_data`: Varying wind speeds and directions
- `sample_pressure_data`: Pressure variations
- `sample_humidity_data`: Humidity patterns
- `sample_station_metadata`: Station info for joins

## Output Schema

All curated tables share a common structure:

### Common Columns
- `feature_id`: BIGSERIAL PRIMARY KEY
- `station_id`: INTEGER
- `station_name`: VARCHAR
- `latitude`, `longitude`: DOUBLE PRECISION
- `elevation_m`: DOUBLE PRECISION
- `year`, `quarter`: INTEGER
- `quarter_start`, `quarter_end`: TIMESTAMP
- `dataset_version`: VARCHAR
- `computed_at`: TIMESTAMP
- `count_observations`, `count_missing`: INTEGER
- `missingness_ratio`: DOUBLE PRECISION

### Product-Specific Columns

See [docs/data-contracts/CURATED_SCHEMA.md](../../docs/data-contracts/CURATED_SCHEMA.md) for complete schema definitions.

**Unique Constraint**: `(station_id, year, quarter, dataset_version)`

## Performance Considerations

1. **Station Metadata Broadcasting**: Small table (~500 stations) is broadcast to all workers for efficient joins

2. **Repartitioning**: Data is repartitioned by station before aggregation to parallelize computation

3. **Caching**: Feature DataFrames are cached when counted and written to avoid recomputation

4. **Upsert Strategy**: Pre-deletion prevents unique constraint violations without expensive ON CONFLICT queries

5. **Parquet Filtering**: Leverages partition pruning for year/quarter filters

6. **Quality Pre-filtering**: Filters `quality_acceptable=True` before aggregation to reduce data volume

## Troubleshooting

### Out of Memory Errors

Increase Spark memory or reduce partition size:
```bash
docker run --rm \
  -e SPARK_EXECUTOR_MEMORY=4g \
  -e SPARK_DRIVER_MEMORY=2g \
  weatherinsight-aggregation:latest \
  python src/orchestrator.py ...
```

### S3 Connection Timeouts

Check MinIO accessibility and credentials:
```bash
# Test S3 access
docker run --rm \
  --network new-project_weatherinsight \
  weatherinsight-aggregation:latest \
  aws s3 ls s3://weatherinsight-staging/staged/dwd/ \
    --endpoint-url http://minio:9000
```

### PostgreSQL Connection Failures

Verify PostgreSQL is running and accessible:
```bash
docker run --rm \
  --network new-project_weatherinsight \
  weatherinsight-aggregation:latest \
  psql -h postgres -U weatherinsight -d weatherinsight -c "SELECT 1"
```

### Missing Staged Data

Ensure processing service has run for the specified year/quarter/version:
```bash
# Check staged data exists
aws s3 ls s3://weatherinsight-staging/staged/dwd/air_temperature/ \
  --recursive --endpoint-url http://minio:9000
```

### Unique Constraint Violations

If duplicates occur, manually delete existing records:
```sql
DELETE FROM quarterly_temperature_features
WHERE year = 2023 AND quarter = 1 AND dataset_version = 'v1.0.0';
```

Then re-run aggregation.

## Metrics and Observability

The orchestrator returns comprehensive metrics:

```python
{
    "product_type": "air_temperature",
    "year": 2023,
    "quarter": 1,
    "staged_version": "v1.0.0",
    "curated_version": "2023Q1_v1",
    "status": "success",
    "feature_count": 450,
    "written_count": 450,
    "elapsed_seconds": 45.23,
    "quality_metrics": {
        "total_stations": 450,
        "avg_missingness_ratio": 0.08
    },
    "start_time": "2024-01-15T10:00:00",
    "end_time": "2024-01-15T10:00:45"
}
```

Dataset versioning tracks:
- Dataset name, version, schema
- Date range (quarter boundaries)
- Storage location (PostgreSQL table)
- Status (PROCESSING → AVAILABLE/FAILED)
- Record counts and quality metrics
- Lineage to staged dataset versions

## Integration with Pipeline

### Upstream: Processing Service

Reads from: `s3a://weatherinsight-staging/staged/dwd/{product_type}/`

Expected structure:
- Partitioned by year/month or station_id/year
- Parquet format with Snappy compression
- Columns: STATIONS_ID, timestamp, year, quarter, product-specific measurements, quality_acceptable, dataset_version

### Downstream: API Service

Curated tables are consumed by the FastAPI service for:
- Station-based queries (all features for a station)
- Time-based queries (all stations for a quarter)
- Feature-based queries (specific statistics across stations)
- Aggregations and comparisons

### Orchestration: Airflow

Aggregation tasks are triggered by Airflow DAGs:
1. Processing service completes for a quarter
2. Metadata service registers staged dataset version
3. Airflow triggers aggregation for each product type
4. Aggregation creates curated dataset versions with lineage
5. API service automatically sees new data

## Future Enhancements

1. **Incremental Aggregation**: Support station-level updates without full quarter recomputation

2. **Derived Features**: Cross-product features (e.g., heat index from temp + humidity)

3. **Anomaly Detection**: Flag statistically unusual quarterly values

4. **Spatial Aggregation**: Regional/grid-based features in addition to station-level

5. **Multi-Quarter Trends**: Rolling statistics across quarters

6. **Configurable Thresholds**: User-defined thresholds for gust/frost/heavy-precip hours

## References

- [Curated Schema Documentation](../../docs/data-contracts/CURATED_SCHEMA.md)
- [Implementation Plan](../../docs/IMPLEMENTATION_PLAN.md)
- [Processing Service README](../processing/README.md)
- [Metadata Service README](../metadata/README.md)
Entry Points
- spark/aggregation_job.py (to be added)
