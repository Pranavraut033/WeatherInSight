# Local Development Runbook

Quick start guide for setting up WeatherInsight locally for development. For production operations, see [OPERATIONS_HANDOVER.md](OPERATIONS_HANDOVER.md).

## Quick Start (5 minutes)

### Prerequisites
- Docker Desktop (or Docker Engine + Docker Compose)
- Minimum 8GB RAM allocated to Docker
- Minimum 20GB free disk space
- macOS, Linux, or Windows with WSL2

### Initial Setup

1. **Clone Repository**
   ```bash
   git clone <repository-url>
   cd weatherinsight
   ```

2. **Configure Environment**
   ```bash
   cp .env.example .env
   # Edit .env with your custom values if needed
   ```

3. **Start All Services**
   ```bash
   docker compose up -d
   ```

4. **Verify Services**
   ```bash
   docker compose ps
   ```
   All services should show "healthy" or "running" status.

5. **Access Local Services**
   - MinIO Console: http://localhost:9001 (minioadmin/minioadmin123)
   - Airflow: http://localhost:8080 (admin/admin123)
   - Grafana: http://localhost:3002 (admin/admin123)
   - Spark Master: http://localhost:8081
   - FastAPI Docs: http://localhost:8000/docs
   - Prometheus: http://localhost:9090
   - Alertmanager: http://localhost:9093

## Ingestion Service Operations

### Running Ingestion

**Ingest a specific variable:**
```bash
docker run --rm \
  --network new-project_weatherinsight \
  -e MINIO_ENDPOINT=minio:9000 \
  weatherinsight-ingestion:latest \
  python bin/ingest --variable air_temperature
```

**Quick Test Script:**
```bash
./test-ingestion.sh
```
This script:
1. Starts infrastructure services
2. Builds the ingestion service
3. Ingests air temperature data
4. Shows verification steps

### Verify Ingestion

**Check MinIO:**
1. Open MinIO Console: http://localhost:9001
2. Navigate to `weatherinsight-raw` bucket
3. Browse: `raw/dwd/air_temperature/`
4. Verify `.zip` and `.sha256` files exist

**Check PostgreSQL Metadata:**
```sql
-- View ingestion runs
SELECT * FROM ingestion_runs ORDER BY started_at DESC LIMIT 10;
```

### Service Architecture

```
┌─────────────────────┐   ┌─────────────┐   ┌──────────────┐
│  Ingestion Service  │→  │    MinIO    │→  │  PostgreSQL  │
│    (DWD Data)       │   │   (Raw)     │   │   (Curated)  │
└─────────────────────┘   └─────────────┘   └──────────────┘
```

## Common Operations

### Start/Stop Services

**Start all services:**
```bash
docker compose up -d
```

**Stop all services:**
```bash
docker compose down
```

**Stop and remove volumes (CAUTION: deletes all data):**
```bash
docker compose down -v
```

**Restart specific service:**
```bash
docker compose restart <service-name>
# Example: docker compose restart api
```

### View Logs

**All services:**
```bash
docker compose logs -f
```

**Specific service:**
```bash
docker compose logs -f <service-name>
# Example: docker compose logs -f airflow-scheduler
```

**Last 100 lines:**
```bash
docker compose logs --tail=100 <service-name>
```

### Database Access

**PostgreSQL (curated data):**
```bash
docker compose exec postgres psql -U weatherinsight -d weatherinsight
```

**Common queries:**
```sql
-- List all tables
\dt

-- Check station metadata
SELECT * FROM station_metadata LIMIT 10;

-- Check dataset versions
SELECT * FROM dataset_versions ORDER BY processing_started_at DESC;

-- Count temperature features
SELECT COUNT(*) FROM quarterly_temperature_features;
```

**MinIO (raw data):**
- Access via web console: http://localhost:9001
- Or use MinIO Client (mc):
  ```bash
  docker compose exec minio-init mc ls myminio/weatherinsight-raw/raw/dwd/
  ```

### Airflow Operations

**Trigger DAG manually:**
1. Open Airflow UI: http://localhost:8080
2. Navigate to DAGs
3. Find `weatherinsight_quarterly` DAG
4. Click play button → "Trigger DAG"
5. Optional: Set execution date for backfill

**Check DAG run status:**
```bash
docker compose exec airflow-scheduler airflow dags list
docker compose exec airflow-scheduler airflow dags list-runs -d weatherinsight_quarterly
```

**Pause/Unpause DAG:**
```bash
docker compose exec airflow-scheduler airflow dags pause weatherinsight_quarterly
docker compose exec airflow-scheduler airflow dags unpause weatherinsight_quarterly
```

### Spark Job Execution

**Submit Spark job manually (processing):**
```bash
docker compose exec spark-master spark-submit \
  --master spark://spark-master:7077 \
  /opt/processing/spark/processing_job.py \
  --year 2023 --quarter 1
```

**Submit Spark job manually (aggregation):**
```bash
docker compose exec spark-master spark-submit \
  --master spark://spark-master:7077 \
  /opt/aggregation/spark/aggregation_job.py \
  --year 2023 --quarter 1
```

**Check Spark job status:**
- Spark Master UI: http://localhost:8081

## Backfill Procedures

### Backfill Quarterly Data

**Use Case:** Re-process historical quarters (e.g., Q1-Q4 2022)

**Steps:**
1. Open Airflow UI: http://localhost:8080
2. Navigate to `weatherinsight_quarterly` DAG
3. Click "Trigger DAG w/ config"
4. Set execution date: `2022-01-01` for Q1 2022
5. Enable "Run" button
6. Repeat for each quarter:
   - Q1: `YYYY-01-01`
   - Q2: `YYYY-04-01`
   - Q3: `YYYY-07-01`
   - Q4: `YYYY-10-01`

**CLI Method:**
```bash
docker compose exec airflow-scheduler airflow dags backfill \
  -s 2022-01-01 \
  -e 2022-12-31 \
  weatherinsight_quarterly
```

### Re-process Single Station

**Use Case:** Fix data for one station after discovering quality issue

1. Identify station_id and quarter
2. Delete existing features:
   ```sql
   DELETE FROM quarterly_temperature_features 
   WHERE station_id = 433 AND year = 2023 AND quarter = 1;
   -- Repeat for other feature tables
   ```
3. Trigger DAG with execution date matching the quarter

## Schema Change Procedures

### Adding New Feature Column

1. **Update data contract:**
   - Edit [docs/data-contracts/CURATED_SCHEMA.md](docs/data-contracts/CURATED_SCHEMA.md)
   - Increment schema version

2. **Create migration script:**
   ```bash
   touch infra/postgres/migrations/002_add_new_feature.sql
   ```

3. **Add ALTER TABLE statement:**
   ```sql
   ALTER TABLE quarterly_temperature_features 
   ADD COLUMN new_feature_name DECIMAL(6,2);
   ```

4. **Apply migration:**
   ```bash
   docker compose exec postgres psql -U weatherinsight -d weatherinsight -f /docker-entrypoint-initdb.d/migrations/002_add_new_feature.sql
   ```

5. **Update aggregation Spark job** to compute new feature

6. **Update API schemas** in `services/api/app/schemas/`

### Schema Version Tracking

Record schema changes in `dataset_versions` table:
```sql
UPDATE dataset_versions 
SET schema_version = 'v1.1', notes = 'Added new_feature_name column'
WHERE version_name = '2024Q1_v1';
```

## Troubleshooting

### Airflow Scheduler Not Running

**Symptoms:** DAGs not executing on schedule

**Solutions:**
1. Check scheduler logs:
   ```bash
   docker compose logs -f airflow-scheduler
   ```
2. Restart scheduler:
   ```bash
   docker compose restart airflow-scheduler
   ```
3. Verify database connection:
   ```bash
   docker compose exec airflow-scheduler airflow db check
   ```

### MinIO Connection Errors

**Symptoms:** Ingestion or processing fails with S3 connection errors

**Solutions:**
1. Check MinIO is healthy:
   ```bash
   docker compose ps minio
   curl http://localhost:9000/minio/health/live
   ```
2. Verify buckets exist:
   ```bash
   docker compose exec minio-init mc ls myminio
   ```
3. Check credentials in `.env`

### PostgreSQL Connection Errors

**Symptoms:** API or aggregation fails with DB errors

**Solutions:**
1. Check PostgreSQL is healthy:
   ```bash
   docker compose ps postgres
   ```
2. Test connection:
   ```bash
   docker compose exec postgres pg_isready -U weatherinsight
   ```
3. Check disk space:
   ```bash
   docker compose exec postgres df -h
   ```

### Spark Job Failures

**Symptoms:** Processing or aggregation jobs fail

**Solutions:**
1. Check Spark Master logs:
   ```bash
   docker compose logs -f spark-master
   ```
2. Check worker memory allocation:
   ```bash
   docker compose ps spark-worker
   ```
3. Increase worker memory in `.env`:
   ```
   SPARK_WORKER_MEMORY=4G
   ```
4. Restart Spark services:
   ```bash
   docker compose restart spark-master spark-worker
   ```

### API Returns 500 Errors

**Symptoms:** FastAPI endpoints return internal server errors

**Solutions:**
1. Check API logs:
   ```bash
   docker compose logs -f api
   ```
2. Verify PostgreSQL connection:
   ```bash
   docker compose exec api python -c "import psycopg2; psycopg2.connect('postgresql://weatherinsight:weatherinsight123@postgres:5432/weatherinsight')"
   ```
3. Restart API:
   ```bash
   docker compose restart api
   ```

### High Disk Usage

**Symptoms:** Docker volumes consuming excessive disk space

**Solutions:**
1. Check volume sizes:
   ```bash
   docker system df -v
   ```
2. Clean up old logs:
   ```bash
   docker compose exec airflow-scheduler find /opt/airflow/logs -type f -mtime +30 -delete
   ```
3. Prune unused volumes (CAUTION):
   ```bash
   docker volume prune
   ```

## Monitoring & Alerts

### Check System Health

**Grafana Dashboard:**
1. Open Grafana: http://localhost:3002
2. Navigate to Dashboards → WeatherInsight System Overview
3. Monitor:
   - API response times
   - Database query performance
   - MinIO storage usage
   - Spark job durations

**Prometheus Queries:**
- API uptime: `up{job="weatherinsight-api"}`
- Database connections: `pg_stat_database_numbackends`
- Request rate: `rate(http_requests_total[5m])`

### Data Quality Checks

**Check missingness ratios:**
```sql
SELECT station_id, year, quarter, missingness_ratio
FROM quarterly_temperature_features
WHERE missingness_ratio > 0.2
ORDER BY missingness_ratio DESC;
```

**Check processing status:**
```sql
SELECT version_name, status, processing_started_at, processing_completed_at
FROM dataset_versions
WHERE status != 'completed'
ORDER BY processing_started_at DESC;
```

## Maintenance Tasks

### Weekly

- [ ] Review Airflow DAG runs for failures
- [ ] Check disk space on Docker host
- [ ] Review API error logs

### Monthly

- [ ] Clean up old Airflow logs (>30 days)
- [ ] Review Grafana dashboards for anomalies
- [ ] Update DWD station metadata if changed

### Quarterly

- [ ] Verify new quarter processing completed successfully
- [ ] Review data quality metrics across all stations
- [ ] Update documentation if workflows changed

## Backup & Recovery

### Backup PostgreSQL

**Manual backup:**
```bash
docker compose exec postgres pg_dump -U weatherinsight weatherinsight > backup_$(date +%Y%m%d).sql
```

**Restore from backup:**
```bash
docker compose exec -T postgres psql -U weatherinsight weatherinsight < backup_20240205.sql
```

### Backup MinIO

**Using MinIO Client:**
```bash
docker compose exec minio-init mc mirror myminio/weatherinsight-raw myminio/weatherinsight-backup
```

### Disaster Recovery

1. Stop all services:
   ```bash
   docker compose down
   ```
2. Restore PostgreSQL backup (see above)
3. Verify MinIO raw data is intact
4. Restart services:
   ```bash
   docker compose up -d
   ```
5. Verify service health
6. Re-run failed DAG runs if needed

## Orchestration Operations

### Overview
Airflow orchestrates the quarterly data pipeline (ingestion → processing → aggregation) with automatic scheduling and manual backfill capabilities.

### Accessing Airflow UI

Navigate to http://localhost:8080 and log in with `admin/admin123`

**Key Views:**
- **DAGs**: List all available DAGs and their status
- **Tree View**: Visualize task execution history
- **Graph View**: See task dependencies
- **Gantt View**: Analyze task execution timeline
- **Logs**: View detailed task logs

### Quarterly Pipeline DAG

**Purpose:** Automatically process quarterly weather data on schedule

**Schedule:** Runs quarterly on Jan 1, Apr 1, Jul 1, Oct 1 at midnight UTC

**Manual Trigger:**
```bash
# Trigger for specific execution date
airflow dags trigger weatherinsight_quarterly_pipeline \
  --exec-date 2024-01-01

# Via Airflow UI
# 1. Navigate to DAGs page
# 2. Find "weatherinsight_quarterly_pipeline"
# 3. Click play button (▶) on the right
# 4. Confirm execution date
```

**Backfill Historical Quarters:**
```bash
# Backfill 2020-2023
airflow dags backfill weatherinsight_quarterly_pipeline \
  --start-date 2020-01-01 \
  --end-date 2023-12-31

# Note: Catchup is enabled, so just enabling the DAG will process missed quarters
```

**Monitoring:**
- Check Tree View for task status (green=success, red=failure, yellow=running)
- View task logs by clicking task box → "Log"
- Check XCom data for inter-task communication
- Monitor Spark jobs at http://localhost:8081

**Common Issues:**

*DAG not appearing in UI:*
```bash
# Check DAG syntax
docker exec airflow-scheduler python /opt/airflow/dags/quarterly_pipeline.py

# Check Airflow logs
docker compose logs airflow-scheduler | grep ERROR
```

*Task stuck in "running":*
```bash
# Check worker is processing
docker compose logs airflow-worker | tail -50

# Clear task state and retry
airflow tasks clear weatherinsight_quarterly_pipeline \
  --start-date 2024-01-01 \
  --end-date 2024-01-01
```

*Service container failures:*
```bash
# Check service logs
docker compose logs <service-name>

# Verify network connectivity
docker exec airflow-worker ping minio
docker exec airflow-worker ping postgres
docker exec airflow-worker ping spark-master
```

### Backfill Pipeline DAG

**Purpose:** Manually reprocess historical quarters with flexible parameters

**Trigger with Parameters:**
```bash
# Backfill specific quarters and products
airflow dags trigger weatherinsight_backfill \
  --conf '{
    "start_year": 2022,
    "end_year": 2023,
    "quarters": [1, 2],
    "products": ["air_temperature", "precipitation"]
  }'

# Full historical backfill (all products, all quarters)
airflow dags trigger weatherinsight_backfill \
  --conf '{
    "start_year": 2020,
    "end_year": 2024
  }'

# Force reprocess existing data
airflow dags trigger weatherinsight_backfill \
  --conf '{
    "start_year": 2023,
    "quarters": [4],
    "force_reprocess": true
  }'
```

**Via Airflow UI:**
1. Navigate to DAGs → "weatherinsight_backfill"
2. Click "Trigger DAG" button (▶ with +)
3. Enter JSON configuration in "Configuration JSON" field
4. Click "Trigger"

**Parameters:**
- `start_year`: First year to backfill (default: 2020)
- `end_year`: Last year to backfill (default: 2024)
- `quarters`: List [1,2,3,4] (default: all quarters)
- `products`: List of product types (default: all 5)
- `force_reprocess`: Boolean to skip existing data checks (default: false)

**Monitoring:**
- Backfill runs sequentially through all combinations
- Check task logs for progress
- Verify data in PostgreSQL after completion
- Review summary report in final task

### Data Quality Checks DAG

**Purpose:** Validate data quality after pipeline completion

**Schedule:** Runs 6 hours after quarterly pipeline (Jan/Apr/Jul/Oct 1 at 6:00 UTC)

**Manual Trigger:**
```bash
airflow dags trigger weatherinsight_data_quality
```

**Validation Checks:**
1. **Row count**: Minimum 100 rows per quarter per product
2. **Null percentage**: Maximum 15% nulls in critical columns
3. **Station coverage**: Minimum 50 stations per quarter
4. **Metadata consistency**: All dataset versions are AVAILABLE
5. **Temporal continuity**: No missing quarters in time series

**Interpreting Results:**

*All checks pass:*
```
✓ Row count validation passed
✓ Null percentage validation passed
✓ Station coverage validation passed
✓ Metadata consistency check passed
✓ Temporal continuity check passed
```

*Validation failure:*
- DAG will fail and send email alert
- Review task logs to see which check failed
- Investigate root cause (missing data, ingestion failure, etc.)
- Fix underlying issue and re-run pipeline

**Common Quality Issues:**

*Low row counts:*
- Check if ingestion completed for all stations
- Verify processing didn't filter too many rows
- Review quality thresholds in `config/dag_config.yaml`

*High null percentages:*
- Check DWD data quality for that period
- Verify parsing logic in processing service
- May be acceptable for certain stations/periods

*Missing stations:*
- Check station metadata is loaded
- Verify station IDs in raw data match metadata
- Review filtering criteria in aggregation service

### DAG Configuration

All DAGs use centralized configuration in `services/orchestrator/config/dag_config.yaml`

**Modifying Configuration:**
```bash
# Edit configuration
vim services/orchestrator/config/dag_config.yaml

# Restart Airflow services to apply changes
docker compose restart airflow-scheduler airflow-worker
```

**Common Configuration Changes:**

*Adjust retry policy:*
```yaml
retries:
  ingestion: 5  # Increase retries for unreliable DWD API
  processing: 3
  aggregation: 2
```

*Modify quality thresholds:*
```yaml
quality_thresholds:
  min_rows_per_quarter: 50  # Lower threshold for sparse stations
  max_null_percentage: 20.0  # Allow more nulls
  min_stations_per_quarter: 30
```

*Change Spark configuration:*
```yaml
spark:
  executor_memory: "8g"  # Increase for larger datasets
  executor_cores: 4
```

### Airflow Connections

**PostgreSQL Connection:**
```bash
# Add via CLI
airflow connections add weatherinsight_postgres \
  --conn-type postgres \
  --conn-host postgres \
  --conn-port 5432 \
  --conn-login weatherinsight \
  --conn-password weatherinsight123 \
  --conn-schema weatherinsight

# Or via UI: Admin → Connections → Add
```

**Verify Connection:**
```bash
airflow connections test weatherinsight_postgres
```

### Resource Management

**Resource Pools:**

Create pools to limit concurrent task execution:
```bash
# Via CLI
airflow pools set spark_jobs 3 "Spark job execution pool"
airflow pools set api_calls 5 "External API call pool"

# Via UI: Admin → Pools → Add
```

**Monitor Pool Usage:**
- Navigate to Browse → Task Instances
- Filter by pool name
- Check "Queued" vs "Running" counts

**Adjust Parallelism:**

Edit `docker-compose.yml`:
```yaml
airflow-common:
  environment:
    AIRFLOW__CORE__PARALLELISM: 16  # Total parallel tasks across all DAGs
    AIRFLOW__CORE__DAG_CONCURRENCY: 8  # Parallel tasks per DAG
    AIRFLOW__CORE__MAX_ACTIVE_RUNS_PER_DAG: 1  # One DAG run at a time
```

Restart services:
```bash
docker compose up -d airflow-scheduler airflow-worker
```

### Troubleshooting Orchestration

**DAG Import Errors:**
```bash
# Check DAG files for syntax errors
docker exec airflow-scheduler python -m py_compile /opt/airflow/dags/*.py

# View DAG parsing errors in UI
# Navigate to Browse → DAG Imports
```

**Task Execution Failures:**
```bash
# View task logs
airflow tasks logs weatherinsight_quarterly_pipeline ingest_air_temperature 2024-01-01 1

# Re-run specific task
airflow tasks run weatherinsight_quarterly_pipeline ingest_air_temperature 2024-01-01

# Clear task state and retry
airflow tasks clear weatherinsight_quarterly_pipeline \
  --task-regex "ingest_.*" \
  --start-date 2024-01-01 \
  --end-date 2024-01-01
```

**Celery Worker Issues:**
```bash
# Check worker status
docker compose logs airflow-worker

# Inspect active tasks
docker exec airflow-scheduler airflow celery inspect active

# Check registered workers
docker exec airflow-scheduler airflow celery inspect registered
```

**Database Connection Issues:**
```bash
# Test Postgres connection from Airflow
docker exec airflow-scheduler psql -h postgres -U weatherinsight -d weatherinsight -c "SELECT 1"

# Check Airflow metadata DB
docker exec airflow-scheduler airflow db check
```

**Scheduler Not Picking Up DAGs:**
```bash
# Check scheduler logs
docker compose logs -f airflow-scheduler

# Manually trigger DAG parse
docker exec airflow-scheduler airflow dags reserialize

# Restart scheduler
docker compose restart airflow-scheduler
```

## Development Workflow

### Adding New Variable/Product

1. Update [docs/requirements.md](docs/requirements.md) with new variable
2. Update [docs/data-contracts/RAW_SCHEMA.md](docs/data-contracts/RAW_SCHEMA.md)
3. Update [docs/data-contracts/CURATED_SCHEMA.md](docs/data-contracts/CURATED_SCHEMA.md)
4. Create PostgreSQL table migration
5. Update ingestion service to fetch new variable
6. Update processing Spark job to parse new variable
7. Update aggregation Spark job to compute features
8. Update API schemas and endpoints
9. Test end-to-end with sample data
10. Update Grafana dashboards

### Testing Changes Locally

1. Make code changes in `services/`
2. Restart affected service:
   ```bash
   docker compose restart <service>
   ```
3. Trigger test DAG run with small date range
4. Verify outputs in PostgreSQL
5. Test API endpoints: http://localhost:8000/docs

### Running Tests

**Unit Tests:**
```bash
# API service tests
docker compose run --rm api pytest tests/ -v

# Ingestion service tests
cd services/ingestion
pytest tests/ -v --cov=src

# Processing service tests
cd services/processing
pytest tests/ -v --cov=src

# Aggregation service tests
cd services/aggregation
pytest tests/ -v --cov=src

# All unit tests with coverage
pytest services/*/tests/ -v --cov=services --cov-report=html
```

**Integration Tests:**
```bash
# Database integration tests
pytest tests/e2e/ -v -m integration

# MinIO integration tests
pytest services/ingestion/tests/test_integration.py -v

# Spark integration tests
pytest services/processing/tests/ -v -k integration
```

**E2E Tests:**
```bash
# Full pipeline E2E tests (requires Docker Compose)
pytest tests/e2e/ -v

# Specific E2E test suite
pytest tests/e2e/test_full_pipeline.py -v
pytest tests/e2e/test_data_quality.py -v
pytest tests/e2e/test_api_integration.py -v

# E2E tests with cleanup
pytest tests/e2e/ -v --tb=short --maxfail=1
```

**Performance Tests:**
```bash
# Locust load testing
cd tests/performance
locust -f locustfile.py --headless -u 100 -r 10 -t 60s

# With web UI
locust -f locustfile.py --host=http://localhost:8000
# Open: http://localhost:8089
```

**Test Coverage Report:**
```bash
# Generate HTML coverage report
pytest services/ tests/ --cov=services --cov-report=html
open htmlcov/index.html

# Coverage summary
pytest --cov=services --cov-report=term-missing
```

## Monitoring & Observability

### Access Monitoring Tools

**Grafana Dashboards** (http://localhost:3002):
- **Credentials**: admin/admin123
- **Dashboards**:
  - Pipeline Overview: Airflow DAG execution and task performance
  - API Performance: Request rates, latencies, error rates
  - Data Quality: Feature table completeness and freshness
  - Infrastructure: Service health, resource utilization

**Prometheus** (http://localhost:9090):
- Query metrics: `weatherinsight_api_requests_total`
- View targets: http://localhost:9090/targets
- Check alerts: http://localhost:9090/alerts

**Alertmanager** (http://localhost:9093):
- View active alerts
- Silence alerts during maintenance
- Check notification status

### Key Metrics to Monitor

**API Performance:**
```promql
# Request rate
sum(rate(weatherinsight_api_requests_total[5m])) by (endpoint)

# P95 latency
histogram_quantile(0.95, rate(weatherinsight_api_request_duration_seconds_bucket[5m]))

# Error rate
(sum(rate(weatherinsight_api_requests_total{status=~"5.."}[5m])) / 
 sum(rate(weatherinsight_api_requests_total[5m]))) * 100
```

**Pipeline Health:**
```promql
# DAG success rate
rate(airflow_dagrun_success_total{dag_id="quarterly_pipeline"}[1h])

# Task duration
airflow_task_duration_seconds{dag_id="quarterly_pipeline"}

# Executor queue depth
airflow_executor_open_slots
```

**Data Quality:**
```sql
-- Feature table row counts
SELECT 'temperature' as product, COUNT(*) FROM quarterly_temperature_features
UNION ALL
SELECT 'precipitation', COUNT(*) FROM quarterly_precipitation_features;

-- Data freshness
SELECT MAX(quarter_end) as latest_data FROM quarterly_temperature_features;

-- Null percentage
SELECT 
  COUNT(*) FILTER (WHERE mean_value IS NULL) * 100.0 / COUNT(*) as null_pct
FROM quarterly_temperature_features;
```

**Infrastructure:**
```bash
# Service health
docker compose ps

# Resource usage
docker stats --no-stream

# MinIO disk usage
docker exec minio mc du --depth=2 minio/weatherinsight-raw

# PostgreSQL connections
psql -h localhost -U weatherinsight -d weatherinsight -c "
  SELECT count(*), state FROM pg_stat_activity 
  WHERE datname='weatherinsight' GROUP BY state;"
```

### Alert Response

When an alert fires, follow these steps:

1. **Acknowledge Alert**:
   ```bash
   # View active alerts
   curl http://localhost:9093/api/v1/alerts
   
   # Silence alert during investigation
   curl -X POST http://localhost:9093/api/v1/silences -d '{
     "matchers": [{"name":"alertname","value":"APIHighLatency"}],
     "comment":"Investigating latency spike"
   }'
   ```

2. **Check Grafana Dashboard**: Open relevant dashboard based on alert
3. **Review Service Logs**: `docker compose logs <service> --tail=100`
4. **Follow Incident Response Guide**: See [docs/INCIDENT_RESPONSE.md](docs/INCIDENT_RESPONSE.md)

### Common Alert Scenarios

**APIDown**:
```bash
docker compose restart api
curl http://localhost:8000/health
```

**HighAPILatency**:
```bash
# Check slow queries
psql -h localhost -U weatherinsight -d weatherinsight -c "
  SELECT query, mean_exec_time FROM pg_stat_statements 
  ORDER BY mean_exec_time DESC LIMIT 10;"
```

**DataQualityCheckFailed**:
```bash
# Check latest pipeline run
docker exec airflow-scheduler airflow dags list-runs -d quarterly_pipeline
docker compose logs airflow-worker --tail=200
```

**DiskSpaceRunningLow**:
```bash
# Check disk usage
docker exec minio mc du minio/weatherinsight-raw
# Clean old data
docker exec minio mc rm --recursive --older-than 180d minio/weatherinsight-raw/
```



## Security Considerations

### Change Default Passwords

Before deploying to production:
1. Edit `.env` and set strong passwords for:
   - MINIO_ROOT_PASSWORD
   - POSTGRES_PASSWORD
   - AIRFLOW_PASSWORD
   - GRAFANA_PASSWORD
2. Regenerate AIRFLOW_FERNET_KEY

### Network Security

For production:
- Remove port bindings for internal services (PostgreSQL, Redis)
- Use Docker secrets instead of environment variables
- Enable TLS for all services
- Add authentication to FastAPI endpoints

## Contact & Support

- Documentation: `docs/`
- Issues: Create ticket in project management system
- Runbook updates: Submit PR to this file
