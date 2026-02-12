# Ingestion Service

## Purpose
Sync DWD hourly station data and store immutable raw files in MinIO raw zone.

## Features
- Fetch station observation files from DWD Open Data API
- Verify file integrity with checksums (SHA256)
- Upload to MinIO following raw zone layout convention
- Track ingestion runs in metadata registry
- Support for all weather variables (temperature, precipitation, wind, etc.)

## Structure
```
ingestion/
├── src/
│   ├── __init__.py
│   ├── config.py           # Configuration management
│   ├── dwd_client.py       # DWD API client
│   ├── storage.py          # MinIO storage manager
│   ├── metadata.py         # Metadata registry
│   └── orchestrator.py     # Main orchestration logic
├── bin/
│   └── ingest              # CLI entry point
├── tests/
│   ├── test_dwd_client.py
│   ├── test_storage.py
│   └── test_integration.py
├── requirements.txt
├── Dockerfile
└── README.md
```

## Usage

### Prerequisites
- MinIO running and accessible
- PostgreSQL running with schema initialized
- Environment variables configured (see .env.example)

### CLI Commands

**Ingest a specific variable:**
```bash
python bin/ingest --variable air_temperature
```

**Ingest all variables:**
```bash
python bin/ingest --all
```

**Ingest specific stations:**
```bash
python bin/ingest --variable precipitation --station-ids 00433 01766 00164
```

**Re-download existing files:**
```bash
python bin/ingest --variable wind --no-skip-existing
```

**Ingest recent data:**
```bash
python bin/ingest --variable air_temperature --recent
```

### Docker Usage

**Build image:**
```bash
docker build -t weatherinsight-ingestion:latest .
```

**Run ingestion:**
```bash
docker run --rm \
  --env-file .env \
  --network weatherinsight \
  weatherinsight-ingestion:latest \
  python bin/ingest --variable air_temperature
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `MINIO_ENDPOINT` | MinIO endpoint | `localhost:9000` |
| `MINIO_ROOT_USER` | MinIO access key | `minioadmin` |
| `MINIO_ROOT_PASSWORD` | MinIO secret key | `minioadmin123` |
| `MINIO_BUCKET` | Raw zone bucket | `weatherinsight-raw` |
| `POSTGRES_HOST` | PostgreSQL host | `localhost` |
| `POSTGRES_PORT` | PostgreSQL port | `5432` |
| `POSTGRES_DB` | Database name | `weatherinsight` |
| `POSTGRES_USER` | Database user | `weatherinsight` |
| `POSTGRES_PASSWORD` | Database password | `weatherinsight` |

## Testing

**Run unit tests:**
```bash
pytest tests/ -v
```

**Run integration tests:**
```bash
RUN_INTEGRATION_TESTS=1 pytest tests/ -v -m integration
```

**Run with coverage:**
```bash
pytest tests/ --cov=src --cov-report=html
```

## Data Flow

1. **List Stations**: Query DWD directory listing for available station files
2. **Download**: Fetch ZIP files and checksums from DWD Open Data
3. **Verify**: Calculate SHA256 checksum and compare with DWD's value
4. **Upload**: Store file in MinIO at `raw/dwd/{variable}/station_{id}/{year}/`
5. **Track**: Record ingestion run metadata in PostgreSQL

## Error Handling

- Retries HTTP requests with exponential backoff (3 attempts)
- Skips files that already exist in MinIO (unless `--no-skip-existing`)
- Logs failed stations but continues with remaining stations
- Tracks failures in metadata registry

## Notes
- Files are stored immutably in raw zone
- Checksum files are stored alongside data files
- Ingestion runs are tracked for observability
- Supports both historical and recent data periods
