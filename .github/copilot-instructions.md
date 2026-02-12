# WeatherInsight — AI Coding Agent Instructions

## System Overview

**WeatherInsight** is a production data pipeline that ingests hourly weather observations from DWD (German Weather Service), processes them quarterly using Spark, aggregates 67 features across 5 product types, and exposes data via FastAPI.

**Architecture**: DWD OpenData → Ingestion → MinIO (raw zone) → Spark Processing → MinIO (staging) → Spark Aggregation → PostgreSQL (curated) → FastAPI  
**Orchestration**: Airflow (quarterly scheduling) | **Monitoring**: Prometheus + Grafana  
**Key Data**: 200+ active weather stations, ~500-600 historical stations, features since 2019

---

## Service Architecture & Boundaries

| Service | Role | Key Files | Technology |
|---------|------|-----------|-----------|
| **ingestion** | Syncs DWD files → MinIO raw zone with checksum verification | `dwd_client.py`, `storage.py`, `orchestrator.py` | Python, MinIO SDK |
| **processing** | Parse/clean raw DWD files, validate schemas, stage to MinIO | `parser.py`, `cleaner.py`, `writer.py` | PySpark |
| **aggregation** | Compute 67 quarterly features, write to PostgreSQL curated tables | `aggregator.py`, `feature_calculators.py`, `postgres_writer.py` | PySpark |
| **metadata** | Schema registry, dataset versioning, governance metadata | Schema migrations, registry tables | PostgreSQL |
| **orchestrator** | Airflow DAGs: ingestion → processing → aggregation → publish | `dags/`, quarterly schedule | Apache Airflow 2.8+ |
| **api** | REST endpoints for feature access, pagination, filtering | `main.py`, `models.py`, `routes/` | FastAPI, SQLAlchemy |

---

## Critical Data Flows & Concepts

### 1. **Raw Zone (Immutable)**
- **Location**: MinIO bucket `weatherinsight-raw`
- **Layout**: `<variable>/<station_id>/<year>/` (e.g., `air_temperature/00433/2023/`)
- **Files**: Original DWD ZIP-extracted text files with checksums
- **Write**: Only ingestion service writes here; verified once
- **Contract**: [docs/DATA_CONTRACTS.md](../docs/DATA_CONTRACTS.md#raw-data-schema)

### 2. **Staging Zone (Intermediate)**
- **Location**: MinIO bucket `weatherinsight-staging`
- **Format**: Parquet, partitioned by year/month or station/year
- **Content**: Cleaned, validated hourly data from processing service
- **Lifecycle**: Regenerated quarterly; not for external use

### 3. **Curated Zone (Query-Ready)**
- **Location**: PostgreSQL tables (schema `public`)
- **Key Tables**: 
  - `temperature_features`, `precipitation_features`, `wind_features`, `pressure_features`, `humidity_features` (quarterly aggregates)
  - `station_metadata` (station details: ID, name, lat/lon, elevation, active status)
  - `dataset_versions` (dataset versioning and lineage)
- **Grain**: One row per (station, product, year, quarter)
- **Characteristics**: Time-series data, versioned by ingestion run

---

## Configuration & Environment Patterns

**All services use Pydantic `BaseSettings` or custom config objects** with environment variable precedence:

```python
from pydantic import BaseSettings

class MyConfig(BaseSettings):
    MINIO_ENDPOINT: str = "minio:9000"
    POSTGRES_HOST: str = "postgres"
    # ...
    class Config:
        env_file = ".env"
```

**Key env vars** (see `.env.example`):
- MinIO: `MINIO_ENDPOINT`, `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`
- PostgreSQL: `POSTGRES_HOST`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`
- Airflow: `AIRFLOW_HOME`, `AIRFLOW__CORE__EXECUTOR`, `AIRFLOW__CELERY__BROKER_URL`

**Local development**: Copy `.env.example` to `.env` and update ports/credentials if needed.

---

## Common Developer Workflows

### **Start Local Infrastructure**
```bash
docker compose up -d minio postgres redis airflow-webserver
# Wait ~30s for services to be healthy
# MinIO Console: http://localhost:9001
# Airflow UI: http://localhost:8080
```

### **Run Ingestion Tests**
```bash
./test-ingestion.sh
# Or manually:
cd services/ingestion
pytest tests/
docker build -t weatherinsight-ingestion:latest .
docker run --rm --network weatherinsight \
  -e MINIO_ENDPOINT=minio:9000 \
  weatherinsight-ingestion:latest \
  python bin/ingest --variable air_temperature --station-ids 00433
```

### **Run Processing Tests**
```bash
cd services/processing
pytest tests/
# Spark jobs expect staging data in MinIO from ingestion
```

### **Run Aggregation & Feature Build**
```bash
cd services/aggregation
pytest tests/
# Reads cleaned data from MinIO staging, writes to PostgreSQL
```

### **Test Full Pipeline (E2E)**
```bash
docker compose up -d  # All services
pytest tests/e2e/
# Validates: ingestion → processing → aggregation → PostgreSQL → API
```

### **Debug Airflow DAGs**
```bash
# Access at http://localhost:8080 (airflow / airflow)
# Check DAG: services/orchestrator/dags/weatherinsight_dag.py
# Logs: docker compose logs -f airflow-webserver
# Trigger: airflow dags trigger weatherinsight_pipeline --exec-date 2025-03-31
```

### **Query Curated Data**
```bash
psql postgresql://weatherinsight:weatherinsight@localhost:5432/weatherinsight
SELECT * FROM temperature_features 
WHERE station_id = '00433' AND year = 2025 AND quarter = 1;
```

### **Test API Locally**
```bash
docker compose up -d postgres  # or full stack
cd services/api
python -m uvicorn app.main:app --reload --port 8000
# Swagger UI: http://localhost:8000/docs
```

---

## Project Conventions

### **Code Structure (All Python Services)**
```
services/<service>/
├── src/
│   ├── __init__.py
│   ├── config.py              # Config class with env var handling
│   ├── <main_module>.py       # Core logic
│   └── <helpers>.py
├── bin/
│   └── <cli_entry>            # Entry point script (if CLI)
├── tests/
│   ├── conftest.py            # pytest fixtures
│   ├── test_*.py              # Unit/integration tests
├── requirements.txt           # Python dependencies (pinned versions)
├── Dockerfile                 # Multi-stage builds preferred
└── README.md                  # Usage, endpoints, examples
```

### **Naming Conventions**
- **Files**: `snake_case.py` (PEP 8)
- **Classes**: `PascalCase`
- **Functions**: `snake_case()`
- **Config attributes**: `UPPER_CASE` (environment-like style)
- **Tables**: Plural `temperature_features`, `precipitation_features`
- **Columns**: Lowercase `station_id`, `quarter`, `feature_name`

### **Testing Patterns**
- **Unit tests** in `tests/test_*.py` using pytest
- **Fixtures** shared via `conftest.py` (mock MinIO, PostgreSQL)
- **Coverage target**: 80%+ (run `pytest --cov`)
- **E2E tests** in `tests/e2e/` — full pipeline validation
- **Mocking**: Use `unittest.mock` or pytest fixtures for S3/DB isolation

### **Schema & Data Validation**
- **Raw data**: Validate against [DATA_CONTRACTS.md](../docs/DATA_CONTRACTS.md) during parsing
- **Quality flags**: Enforce QN threshold in cleaner (e.g., QN >= 3)
- **Sentinel values**: Replace -999 with NULL in cleaning step
- **Curated tables**: Enforce NOT NULL on key columns (station_id, year, quarter, feature_name)

---

## Integration Points & Cross-Service Communication

1. **Ingestion → MinIO**: Writes raw zone with checksums; emits metadata to PostgreSQL
2. **MinIO → Processing**: Processing reads raw files; no direct DB reads
3. **Processing → MinIO**: Writes staging zone (parquet, partitioned)
4. **MinIO → Aggregation**: Aggregation reads staging zone with Spark
5. **Aggregation → PostgreSQL**: Writes curated features + updates `dataset_versions`
6. **Orchestrator (Airflow) → All Services**: Runs jobs via docker-compose or K8s; passes configs via env
7. **API → PostgreSQL**: Reads curated tables only; caches station metadata

---

## Key Files & Documentation

| File | Purpose |
|------|---------|
| [docs/requirements.md](../docs/requirements.md) | DWD products, station set, data scope |
| [docs/DATA_CONTRACTS.md](../docs/DATA_CONTRACTS.md) | Raw/curated schemas, file formats, quality rules |
| [docs/IMPLEMENTATION_PLAN.md](../docs/IMPLEMENTATION_PLAN.md) | Phase 0–9 roadmap and current status |
| [docs/runbook.md](../docs/runbook.md) | Operations: deployment, backfill, recovery |
| [docs/TESTING_STRATEGY.md](../docs/TESTING_STRATEGY.md) | Test scopes, coverage, CI/CD |
| [AGENTS.md](../AGENTS.md) | Guidance for AI agents; session defaults, DoD |
| [docker-compose.yml](../docker-compose.yml) | Local dev stack: MinIO, PostgreSQL, Airflow, Prometheus |

---

## Quick Troubleshooting

| Issue | Check |
|-------|-------|
| MinIO connection fails | Is MinIO running? `docker compose ps minio` |
| PostgreSQL connection fails | Check `POSTGRES_HOST`, `POSTGRES_USER`, `POSTGRES_PASSWORD` in `.env` |
| Spark jobs crash | Check Airflow/Spark logs; validate schema in [DATA_CONTRACTS.md](../docs/DATA_CONTRACTS.md) |
| API returns 404 for features | Verify aggregation job completed; query `temperature_features` directly in PostgreSQL |
| Tests fail with "no module" | Ensure `requirements.txt` installed: `pip install -r requirements.txt` |

---

## Key Principles for Contributions

1. **Immutability First**: Raw zone is append-only; never modify ingested files
2. **Quarterly Grain**: Features computed per (station, year, quarter) — respect this boundary
3. **Schema Contracts**: Update [DATA_CONTRACTS.md](../docs/DATA_CONTRACTS.md) before changing schemas
4. **Test Locally First**: Run unit + integration tests before committing
5. **Documentation**: Update runbook/contracts if adding new environment variables or processing steps
6. **Config Over Secrets**: Use `.env` + `BaseSettings` pattern; never hardcode credentials
