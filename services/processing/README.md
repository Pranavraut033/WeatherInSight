# Processing Service

PySpark-based pipeline for parsing, cleaning, and staging DWD weather observations.

## Overview

The processing service transforms raw DWD files from MinIO into cleaned, validated parquet datasets ready for aggregation. It handles:

- **Parsing**: Read semicolon-delimited DWD files with schema validation
- **Cleaning**: Missing value handling, unit normalization, outlier detection
- **Quality Control**: Quality flag enforcement and data validation
- **Staging**: Write partitioned parquet to staging zone

## Architecture

```
Raw Zone (MinIO)
    ↓
Parser → Cleaner → Writer
    ↓                ↓
Staging Zone     Metadata Registry
```

## Components

### Parser (`src/parser.py`)
- Reads DWD text files from S3/MinIO
- Validates against product-specific schemas
- Converts timestamps and adds metadata

### Cleaner (`src/cleaner.py`)
- Replaces sentinel values (-999) with nulls
- Filters by quality flags (QN >= threshold)
- Normalizes units (e.g., hPa → Pa)
- Detects statistical outliers
- Adds processing metadata

### Writer (`src/writer.py`)
- Writes parquet to staging zone
- Partitions by year/month or station/year
- Compaction to control file sizes
- Output validation

### Orchestrator (`src/orchestrator.py`)
- Coordinates pipeline steps
- Handles multiple product types
- Collects metrics and statistics

## Supported Product Types

- `air_temperature` - Temperature and humidity
- `precipitation` - Rainfall and precipitation form
- `wind` - Wind speed and direction
- `pressure` - Station and sea-level pressure
- `moisture` - Humidity and dew point
- `cloud_cover` - Cloud coverage

## Usage

### Docker

```bash
# Build image
docker build -t weatherinsight-processing:latest .

# Run processing for a product
docker run --rm \
  --network weatherinsight \
  -e MINIO_ENDPOINT=http://minio:9000 \
  -e POSTGRES_HOST=postgres \
  weatherinsight-processing:latest \
  python src/orchestrator.py \
    air_temperature \
    s3a://weatherinsight-raw/raw/dwd/air_temperature \
    v1.0.0
```

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export MINIO_ENDPOINT=http://localhost:9000
export POSTGRES_HOST=localhost

# Run processing
python src/orchestrator.py \
  air_temperature \
  s3a://weatherinsight-raw/raw/dwd/air_temperature \
  v1.0.0 \
  --mode append
```

### Python API

```python
from pyspark.sql import SparkSession
from orchestrator import ProcessingOrchestrator, create_spark_session

# Create Spark session
spark = create_spark_session("MyApp", master=None)

# Run processing
orchestrator = ProcessingOrchestrator(spark)
results = orchestrator.process_product(
    product_type="air_temperature",
    input_path="s3a://weatherinsight-raw/raw/dwd/air_temperature",
    dataset_version="v1.0.0"
)

print(results)
```

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| MINIO_ENDPOINT | http://minio:9000 | MinIO/S3 endpoint |
| MINIO_ROOT_USER | minioadmin | S3 access key |
| MINIO_ROOT_PASSWORD | minioadmin123 | S3 secret key |
| RAW_BUCKET | weatherinsight-raw | Raw data bucket |
| STAGING_BUCKET | weatherinsight-staging | Staging bucket |
| POSTGRES_HOST | postgres | PostgreSQL host |
| POSTGRES_PORT | 5432 | PostgreSQL port |
| POSTGRES_DB | weatherinsight | Database name |
| POSTGRES_USER | weatherinsight | Database user |
| POSTGRES_PASSWORD | weatherinsight123 | Database password |
| SPARK_MASTER | None | Spark master URL (None = local) |

## Data Quality

### Quality Thresholds

- **Quality Flag**: Only use observations with QN >= 5 (default)
- **Missing Data**: Max 50% missing values per station-quarter
- **Outliers**: Flag values outside physical limits

### Validation Checks

- Schema conformance
- Timestamp parsing
- Station ID validation
- Null value tracking
- Outlier detection

## Output Schema

Staged parquet files include:

- All original columns from DWD files
- `timestamp` - Parsed datetime (UTC)
- `year`, `month`, `day`, `hour` - Time components
- `quality_acceptable` - Quality flag check result
- `has_outlier` - Outlier detection flag
- `cleaned_at` - Processing timestamp
- `product_type` - Product identifier
- `dataset_version` - Version for lineage
- `_source_file` - Original file path
- `_parsed_at` - Parse timestamp

## Testing

```bash
# Install test dependencies
pip install pytest

# Run tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=src --cov-report=html
```

## Performance

- **Parallelism**: Configurable via Spark partitions
- **File Size**: Target 128 MB per parquet file
- **Compression**: Snappy compression (fast, good ratio)
- **Memory**: Adaptive execution enabled

Typical processing times (local mode, 1 year of data):
- Single station: ~5-10 seconds
- 100 stations: ~2-3 minutes
- 1000 stations: ~20-30 minutes

## Troubleshooting

### Schema Mismatch Errors
- Verify DWD file format matches expected schema
- Check for extra/missing columns
- Validate delimiter is semicolon (;)

### S3 Connection Issues
- Verify MINIO_ENDPOINT is accessible
- Check S3 credentials (access key/secret key)
- Ensure buckets exist

### Memory Issues
- Reduce Spark parallelism: `--conf spark.sql.shuffle.partitions=50`
- Increase executor memory: `--executor-memory 4g`
- Process smaller batches

## Next Steps

After processing completes:
1. Data is available in staging zone as parquet
2. Aggregation service reads staged data
3. Quarterly features computed
4. Results written to PostgreSQL curated tables

