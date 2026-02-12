# WeatherInsight Orchestrator Service

Airflow-based orchestration for WeatherInsight quarterly data pipeline.

## Overview

The orchestrator service provides three Airflow DAGs:

1. **Quarterly Pipeline** (`quarterly_pipeline.py`) - Automated quarterly production pipeline
2. **Backfill Pipeline** (`backfill_pipeline.py`) - Manual historical reprocessing
3. **Data Quality Checks** (`data_quality_checks.py`) - Validation and monitoring

## Architecture

```
┌─────────────┐
│  Ingestion  │ (5 product types in parallel)
└──────┬──────┘
       │
       ↓
┌─────────────┐
│ Processing  │ (5 Spark jobs in parallel)
└──────┬──────┘
       │
       ↓
┌─────────────┐
│ Aggregation │ (5 Spark jobs in parallel)
└──────┬──────┘
       │
       ↓
┌─────────────┐
│  Quality    │ (validation checks)
│   Checks    │
└─────────────┘
```

## DAGs

### 1. Quarterly Pipeline

**Schedule:** `0 0 1 1,4,7,10 *` (Jan 1, Apr 1, Jul 1, Oct 1 at midnight UTC)

**Purpose:** Automatically process quarterly DWD weather data through the complete pipeline.

**Stages:**
- **Ingestion**: Download raw DWD files for 5 product types (air_temperature, precipitation, wind, pressure, moisture)
- **Processing**: Parse and clean raw data using Spark, write to staging zone
- **Aggregation**: Compute 57 quarterly features per product, write to PostgreSQL

**Features:**
- Catchup enabled for historical backfill
- Depends on past (each quarter waits for previous quarter)
- Resource pools to limit concurrent Spark jobs
- Automatic version generation from execution date
- Email alerts on failure

**CLI:**
```bash
# Trigger manually for specific date
airflow dags trigger weatherinsight_quarterly_pipeline \
  --exec-date 2024-01-01

# Backfill range
airflow dags backfill weatherinsight_quarterly_pipeline \
  --start-date 2020-01-01 \
  --end-date 2023-12-31
```

### 2. Backfill Pipeline

**Schedule:** Manual trigger only

**Purpose:** Reprocess historical quarters with flexible parameters.

**Parameters** (via `dag_run.conf`):
- `start_year`: First year to backfill (default: 2020)
- `end_year`: Last year to backfill (default: 2024)
- `quarters`: List of quarters [1,2,3,4] (default: all)
- `products`: List of products (default: all 5)
- `force_reprocess`: Skip existing data checks (default: false)

**CLI:**
```bash
# Backfill specific quarters
airflow dags trigger weatherinsight_backfill \
  --conf '{"start_year": 2022, "end_year": 2023, "quarters": [1,2], "products": ["air_temperature"]}'

# Full historical backfill
airflow dags trigger weatherinsight_backfill \
  --conf '{"start_year": 2020, "end_year": 2024}'

# Force reprocess existing data
airflow dags trigger weatherinsight_backfill \
  --conf '{"start_year": 2023, "quarters": [4], "force_reprocess": true}'
```

### 3. Data Quality Checks

**Schedule:** `0 6 1 1,4,7,10 *` (6 hours after quarterly pipeline)

**Purpose:** Validate data quality and consistency after pipeline completion.

**Checks:**
1. **Row count validation**: Minimum 100 rows per quarter
2. **Null percentage**: Maximum 15% nulls in critical columns
3. **Station coverage**: Minimum 50 stations per quarter
4. **Metadata consistency**: All dataset versions are AVAILABLE
5. **Temporal continuity**: No missing quarters in time series

**Alerts:** Email sent on any validation failure

**CLI:**
```bash
# Trigger manually
airflow dags trigger weatherinsight_data_quality

# Run for specific date
airflow dags trigger weatherinsight_data_quality \
  --exec-date 2024-01-01
```

## Configuration

All DAGs use centralized configuration in `config/dag_config.yaml`:

```yaml
product_types: [air_temperature, precipitation, wind, pressure, moisture]
retries: {ingestion: 3, processing: 2, aggregation: 2}
retry_delay: {minutes: 5}
sla: {pipeline_hours: 12}
spark: {master: "spark://spark-master:7077"}
quality_thresholds: {min_rows_per_quarter: 100, max_null_percentage: 15.0}
```

Modify this file to adjust behavior across all DAGs.

## Environment Variables

DAGs use these environment variables (automatically passed from docker-compose):

```bash
MINIO_ENDPOINT=http://minio:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin123
POSTGRES_HOST=postgres
POSTGRES_USER=weatherinsight
POSTGRES_PASSWORD=weatherinsight123
SPARK_MASTER=spark://spark-master:7077
```

Override via Airflow Variables or `.env` file.

## Service Integration

### Ingestion Service
```bash
python /opt/services/ingestion/bin/ingest --variable <product>
```

### Processing Service
```bash
python /opt/services/processing/src/orchestrator.py \
  <product> \
  s3a://weatherinsight-raw/raw/dwd/<product> \
  <raw_version> \
  --master spark://spark-master:7077
```

### Aggregation Service
```bash
python /opt/services/aggregation/src/orchestrator.py \
  <product> \
  <year> \
  <quarter> \
  <staged_version> \
  --output-version <curated_version> \
  --master spark://spark-master:7077
```

## Monitoring

### Airflow UI
Access at http://localhost:8080 (admin/admin123)

**Views:**
- **DAGs**: List all DAGs with status
- **Tree View**: Visualize task dependencies
- **Gantt View**: Task execution timeline
- **Graph View**: DAG structure
- **Task Instance Details**: Logs and XCom data

### Logs
Task logs stored in `services/orchestrator/logs/`

```bash
# View logs
docker compose logs airflow-scheduler
docker compose logs airflow-worker

# View specific task log
cat services/orchestrator/logs/weatherinsight_quarterly_pipeline/ingest_air_temperature/2024-01-01T00:00:00+00:00/1.log
```

### Prometheus Metrics
Airflow exports metrics to Prometheus (configured in docker-compose):
- DAG run duration
- Task success/failure rates
- Pool utilization
- Queue length

View in Grafana at http://localhost:3002

## Troubleshooting

### DAG Not Appearing in UI

1. Check DAG file syntax:
```bash
docker exec airflow-scheduler python /opt/airflow/dags/quarterly_pipeline.py
```

2. Check Airflow logs:
```bash
docker compose logs airflow-scheduler | grep ERROR
```

3. Verify volume mount:
```bash
docker exec airflow-scheduler ls -la /opt/airflow/dags/
```

### Task Failing

1. View task log in Airflow UI or:
```bash
airflow tasks test weatherinsight_quarterly_pipeline ingest_air_temperature 2024-01-01
```

2. Check service logs:
```bash
# Ingestion
docker compose logs ingestion

# Processing/Aggregation
docker compose logs spark-master
docker compose logs spark-worker
```

3. Verify database connection:
```bash
airflow connections test weatherinsight_postgres
```

### DAG Stuck in Running State

1. Check if worker is processing tasks:
```bash
docker compose logs airflow-worker | tail -50
```

2. Check Celery queue:
```bash
docker exec airflow-scheduler airflow celery inspect active
```

3. Clear task state:
```bash
airflow tasks clear weatherinsight_quarterly_pipeline \
  --start-date 2024-01-01 \
  --end-date 2024-01-01
```

### Dataset Version Mismatch

1. Check metadata service:
```bash
docker exec postgres psql -U weatherinsight -d weatherinsight \
  -c "SELECT * FROM dataset_versions ORDER BY created_at DESC LIMIT 10;"
```

2. Verify version naming pattern in DAG matches services

3. Force reprocess with backfill DAG

## Development

### Testing DAGs Locally

```bash
# Validate DAG syntax
python services/orchestrator/dags/quarterly_pipeline.py

# Test specific task
airflow tasks test weatherinsight_quarterly_pipeline \
  ingest_air_temperature \
  2024-01-01

# Run full DAG (without scheduler)
airflow dags test weatherinsight_quarterly_pipeline 2024-01-01
```

### Adding New DAG

1. Create DAG file in `services/orchestrator/dags/`
2. Import configuration from `config/dag_config.yaml`
3. Use `BashOperator` or `PythonOperator` for tasks
4. Test locally before deploying
5. Update this README with DAG documentation

### Modifying Configuration

1. Edit `config/dag_config.yaml`
2. Restart Airflow services:
```bash
docker compose restart airflow-scheduler airflow-worker
```
3. No code changes needed - DAGs reload config dynamically

## Production Deployment

### Prerequisites
- Docker Compose with all services running
- PostgreSQL with schema initialized
- MinIO buckets created
- Station metadata loaded

### Deployment Steps

1. **Start Airflow**:
```bash
docker compose up -d airflow-init
docker compose up -d airflow-webserver airflow-scheduler airflow-worker
```

2. **Configure Connections**:
```bash
# Add Postgres connection
airflow connections add weatherinsight_postgres \
  --conn-type postgres \
  --conn-host postgres \
  --conn-port 5432 \
  --conn-login weatherinsight \
  --conn-password weatherinsight123 \
  --conn-schema weatherinsight
```

3. **Enable DAGs**:
- Open Airflow UI at http://localhost:8080
- Toggle DAGs to "On" state
- Set catchup to True for historical backfill

4. **Monitor First Run**:
- Watch task progress in Tree View
- Check logs for errors
- Verify data in PostgreSQL

5. **Setup Alerts** (optional):
```bash
# Add email SMTP settings
airflow config set smtp smtp_host smtp.gmail.com
airflow config set smtp smtp_user alerts@weatherinsight.local
airflow config set smtp smtp_password <app-password>
```

## Performance Tuning

### Parallelism

Edit `docker-compose.yml`:
```yaml
airflow-common:
  environment:
    AIRFLOW__CORE__PARALLELISM: 16  # Total parallel tasks
    AIRFLOW__CORE__DAG_CONCURRENCY: 8  # Per DAG
    AIRFLOW__CORE__MAX_ACTIVE_RUNS_PER_DAG: 1
```

### Resource Pools

Create pools in Airflow UI or via CLI:
```bash
airflow pools set spark_jobs 3 "Spark job execution pool"
airflow pools set api_calls 5 "External API call pool"
```

### Spark Configuration

Adjust in `config/dag_config.yaml`:
```yaml
spark:
  executor_memory: "8g"  # Increase for large datasets
  executor_cores: 4
```

## Next Steps

After M6 completion:
- **M7**: Implement Delivery API (FastAPI endpoints)
- **M8**: Add comprehensive E2E tests
- **M9**: Finalize documentation and runbooks
