# WeatherInsight Metadata Service

Manages schema registry and dataset versioning for WeatherInsight data platform.

## Features

### Schema Registry
- **Version Management**: Track schema versions with automatic versioning
- **Compatibility Validation**: Ensure backward/forward/full compatibility
- **Change History**: Audit trail of schema changes
- **Hash-based Deduplication**: Prevent duplicate schema registrations

### Dataset Versioning
- **Version Tracking**: Link dataset versions to ingestion runs
- **Lineage**: Track parent-child relationships between datasets
- **Quality Metrics**: Store and query data quality check results
- **Status Management**: Track dataset lifecycle (pending → processing → available)

## Architecture

### Database Schema

#### Schema Registry Tables
- `schema_versions`: Schema definitions and metadata
- `schema_changes`: Audit log of schema changes

#### Dataset Versioning Tables
- `dataset_versions`: Dataset version metadata
- `dataset_lineage`: Parent-child relationships
- `dataset_quality_checks`: Quality check results

## Usage

### CLI Commands

#### Schema Management

```bash
# Register a new schema
python bin/metadata schema register \
  --name raw_station_data \
  --schema-file schemas/raw.json \
  --description "Raw DWD station observations" \
  --compatibility BACKWARD

# Get schema definition
python bin/metadata schema get --name raw_station_data

# List all schemas
python bin/metadata schema list

# View schema history
python bin/metadata schema history --name raw_station_data
```

#### Dataset Management

```bash
# Create dataset version
python bin/metadata dataset create \
  --dataset-name raw_temperature \
  --version 2024-Q1 \
  --schema-name raw_station_data \
  --schema-version 1 \
  --start-date 2024-01-01 \
  --end-date 2024-03-31 \
  --storage-location s3://bucket/2024-Q1/

# Update dataset status
python bin/metadata dataset update-status \
  --version-id 123 \
  --status available \
  --record-count 1000000 \
  --file-count 90

# List datasets
python bin/metadata dataset list --dataset-name raw_temperature

# Show lineage
python bin/metadata dataset lineage --version-id 123 --direction both
```

### Python API

```python
from config import get_config
from schema_registry import SchemaRegistry
from dataset_versioning import DatasetVersioning, DatasetStatus

config = get_config()

# Schema registry
registry = SchemaRegistry(config.postgres_dsn)

schema_def = {
    "name": "station_data",
    "fields": {
        "station_id": {"type": "string", "required": True},
        "timestamp": {"type": "datetime", "required": True},
        "temperature": {"type": "float", "required": False}
    }
}

version = registry.register_schema(
    schema_name="raw_station_data",
    schema_def=schema_def,
    description="Raw station observations"
)

# Dataset versioning
versioning = DatasetVersioning(config.postgres_dsn)

version_id = versioning.create_version(
    dataset_name="raw_temperature",
    version="2024-Q1",
    schema_name="raw_station_data",
    schema_version=version
)

versioning.update_version_status(
    version_id=version_id,
    status=DatasetStatus.AVAILABLE,
    record_count=1000000
)
```

## Configuration

Environment variables:
- `POSTGRES_HOST`: PostgreSQL host (default: localhost)
- `POSTGRES_PORT`: PostgreSQL port (default: 5432)
- `POSTGRES_DB`: Database name (default: weatherinsight)
- `POSTGRES_USER`: Database user
- `POSTGRES_PASSWORD`: Database password

## Docker

```bash
# Build
docker build -t weatherinsight-metadata:latest .

# Run CLI
docker run --rm \
  --network weatherinsight \
  -e POSTGRES_HOST=postgres \
  -e POSTGRES_USER=weatherinsight \
  -e POSTGRES_PASSWORD=weatherinsight123 \
  weatherinsight-metadata:latest \
  python bin/metadata schema list
```

## Testing

```bash
# Install test dependencies
pip install pytest

# Run tests
pytest tests/
```

## Schema Compatibility Modes

- **BACKWARD**: New schema can read data written with old schema
  - Can add optional fields
  - Can remove optional fields
  - Cannot remove required fields

- **FORWARD**: Old schema can read data written with new schema
  - Can add required fields (with defaults)
  - Can remove fields
  - Cannot add required fields without defaults

- **FULL**: Both backward and forward compatible
  - Most restrictive
  - Only optional field additions/removals

- **NONE**: No compatibility checks
  - Any changes allowed
  - Use with caution

## Integration

The metadata service integrates with:
- **Ingestion Service**: Links dataset versions to ingestion runs
- **Processing Service**: Tracks schema validation and transformations
- **Aggregation Service**: Records lineage from raw to curated datasets
- **API Service**: Provides schema and version information
