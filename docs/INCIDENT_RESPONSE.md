# WeatherInsight Incident Response Guide

## Overview

Operational runbook for diagnosing and resolving common failures in the WeatherInsight data pipeline.

## Quick Reference

| Incident | Severity | Response Time | Primary Responder |
|----------|----------|---------------|-------------------|
| API Down | Critical | <5 minutes | On-call engineer |
| High API Error Rate | Critical | <15 minutes | On-call engineer |
| Pipeline Stuck/Failed | High | <1 hour | Data engineer |
| Data Quality Issues | Medium | <4 hours | Data engineer |
| Disk Space Low | High | <30 minutes | Platform engineer |
| Database Performance | High | <1 hour | Database admin |

## Incident Response Process

### 1. Detection
- Alertmanager notification (email/Slack)
- Grafana dashboard anomaly
- User report
- Automated monitoring

### 2. Acknowledgment
- Acknowledge alert in Alertmanager
- Notify team in Slack/incident channel
- Create incident ticket if needed

### 3. Investigation
- Check Grafana dashboards
- Review service logs
- Query Prometheus metrics
- Inspect database state

### 4. Mitigation
- Apply immediate fix (restart, scale, etc.)
- Implement workaround if needed
- Monitor for stabilization

### 5. Resolution
- Verify service health restored
- Update status page
- Close incident ticket
- Schedule post-mortem if critical

## Common Incidents

### 1. API Service Down

#### Symptoms
- Alert: `APIDown` (critical)
- HTTP requests timing out
- Health check endpoint `/health` unreachable
- Zero traffic in Grafana API Performance dashboard

#### Diagnosis

**Step 1: Check service status**
```bash
docker compose ps api
# Expected: State "Up", Status "healthy"
```

**Step 2: View recent logs**
```bash
docker compose logs api --tail=100 --follow
# Look for: exceptions, connection errors, OOM kills
```

**Step 3: Check dependencies**
```bash
# Database connectivity
docker exec postgres pg_isready
psql -h localhost -U weatherinsight -d weatherinsight -c "SELECT 1"

# Redis connectivity (for rate limiting)
docker exec redis redis-cli ping
```

**Step 4: Check resource usage**
```bash
docker stats api --no-stream
# Look for: high CPU%, high memory usage
```

#### Resolution

**Option A: Restart API service**
```bash
docker compose restart api
# Wait 10s for health check
curl http://localhost:8000/health
```

**Option B: Database connection issue**
```bash
# Check connection pool
psql -h localhost -U weatherinsight -d weatherinsight -c "
  SELECT count(*) as connections, state 
  FROM pg_stat_activity 
  WHERE datname='weatherinsight' 
  GROUP BY state;"

# Kill idle connections if pool exhausted
psql -h localhost -U weatherinsight -d weatherinsight -c "
  SELECT pg_terminate_backend(pid) 
  FROM pg_stat_activity 
  WHERE datname='weatherinsight' AND state='idle' AND state_change < now() - interval '30 minutes';"
```

**Option C: Rebuild and restart**
```bash
docker compose stop api
docker compose rm -f api
docker compose up -d --build api
docker compose logs api --follow
```

**Verification**
```bash
# Health check
curl http://localhost:8000/health
# Expected: {"status": "healthy", "database": "connected"}

# Smoke test
curl http://localhost:8000/api/v1/stations?limit=5
# Expected: JSON array with station data

# Check metrics
curl http://localhost:8000/metrics | grep requests_total
```

#### Escalation
- If restart fails 3x → notify platform team
- If database unreachable → escalate to DBA
- If persistent OOM → increase container memory limit

---

### 2. High API Error Rate (5xx)

#### Symptoms
- Alert: `APIHighErrorRate` (critical)
- Elevated 500 errors in logs
- Error Rate panel spiking in Grafana
- User reports of "Internal Server Error"

#### Diagnosis

**Step 1: Identify error pattern**
```bash
# Recent 5xx errors
docker compose logs api --tail=500 | grep "500\|ERROR"

# Count by endpoint
docker compose logs api --tail=1000 | grep "500" | awk '{print $NF}' | sort | uniq -c | sort -rn
```

**Step 2: Check database queries**
```bash
# Slow queries
psql -h localhost -U weatherinsight -d weatherinsight -c "
  SELECT pid, now() - query_start as duration, state, query 
  FROM pg_stat_activity 
  WHERE state != 'idle' AND query NOT LIKE '%pg_stat_activity%'
  ORDER BY duration DESC LIMIT 10;"

# Query statistics (requires pg_stat_statements)
psql -h localhost -U weatherinsight -d weatherinsight -c "
  SELECT query, calls, mean_exec_time, stddev_exec_time 
  FROM pg_stat_statements 
  ORDER BY mean_exec_time DESC LIMIT 10;"
```

**Step 3: Check for data issues**
```bash
# Feature table integrity
psql -h localhost -U weatherinsight -d weatherinsight -c "
  SELECT 'quarterly_temperature_features' as table, COUNT(*) FROM quarterly_temperature_features
  UNION ALL
  SELECT 'quarterly_precipitation_features', COUNT(*) FROM quarterly_precipitation_features
  UNION ALL
  SELECT 'quarterly_wind_features', COUNT(*) FROM quarterly_wind_features;"
```

**Step 4: Review Prometheus metrics**
```promql
# Error rate by endpoint
rate(weatherinsight_api_requests_total{status=~"5.."}[5m])

# Database query duration
histogram_quantile(0.95, rate(weatherinsight_api_db_query_duration_seconds_bucket[5m]))
```

#### Resolution

**Option A: Database connection pool exhaustion**
```bash
# Increase pool size in docker-compose.yml
# API service environment:
POSTGRES_POOL_SIZE=20  # Increase from default 10
POSTGRES_MAX_OVERFLOW=40  # Increase from default 20

docker compose up -d api
```

**Option B: Specific endpoint failure**
```bash
# Disable problematic endpoint temporarily
# Add to services/api/app/main.py:
@app.get("/api/v1/problematic-endpoint")
async def temp_disabled():
    raise HTTPException(status_code=503, detail="Temporarily unavailable")

# Redeploy
docker compose restart api
```

**Option C: Database query timeout**
```python
# Add timeout to services/api/app/database.py
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"options": "-c statement_timeout=5000"}  # 5s timeout
)
```

**Verification**
```bash
# Monitor error rate
watch -n 5 'curl -s http://localhost:9090/api/v1/query?query=rate\(weatherinsight_api_requests_total\{status=~\"5..\"\}\[1m]\) | jq'

# Check dashboard
# Open: http://localhost:3002/d/api-performance
# Verify: Error Rate panel trending down
```

#### Prevention
- Add query timeouts to all database calls
- Implement circuit breakers for external dependencies
- Add request validation to catch bad input early
- Scale API horizontally if sustained load increase

---

### 3. Airflow DAG Stuck/Failed

#### Symptoms
- Alert: `PipelineNotRunning` (warning)
- DAG run stuck in "running" state for >6 hours
- Tasks in "queued" or "scheduled" but not executing
- No new feature data in last 24 hours

#### Diagnosis

**Step 1: Check DAG status in Airflow UI**
```bash
# Open Airflow UI: http://localhost:8080
# Credentials: airflow/airflow
# Navigate to: DAGs > quarterly_pipeline
# Check: Latest run status, task states, logs
```

**Step 2: Check scheduler health**
```bash
# Scheduler logs
docker compose logs airflow-scheduler --tail=100

# Scheduler heartbeat
docker exec airflow-scheduler airflow jobs check --job-type SchedulerJob --hostname $(hostname)
```

**Step 3: Check worker/executor**
```bash
# Worker logs
docker compose logs airflow-worker --tail=100

# Executor slots
curl -s http://localhost:9090/api/v1/query?query=airflow_executor_open_slots | jq
```

**Step 4: Identify stuck task**
```bash
# List running task instances
docker exec airflow-scheduler airflow tasks states-for-dag-run quarterly_pipeline LATEST

# View specific task log
docker exec airflow-scheduler airflow tasks logs quarterly_pipeline ingest_dwd_data LATEST
```

#### Resolution

**Option A: Clear stuck task**
```bash
# Mark task as failed
docker exec airflow-scheduler airflow tasks clear quarterly_pipeline \
  --task-regex "stuck_task_id" \
  --dag-run-id "scheduled__2026-01-01T00:00:00+00:00"

# Trigger DAG re-run
docker exec airflow-scheduler airflow dags trigger quarterly_pipeline
```

**Option B: Restart Airflow components**
```bash
# Restart scheduler (safest)
docker compose restart airflow-scheduler

# Or restart all Airflow services
docker compose restart airflow-webserver airflow-scheduler airflow-worker
```

**Option C: Database deadlock**
```bash
# Check for locks
psql -h localhost -U airflow -d airflow -c "
  SELECT blocked_locks.pid AS blocked_pid,
         blocking_locks.pid AS blocking_pid,
         blocked_activity.query AS blocked_query
  FROM pg_catalog.pg_locks blocked_locks
  JOIN pg_catalog.pg_stat_activity blocked_activity ON blocked_activity.pid = blocked_locks.pid
  JOIN pg_catalog.pg_locks blocking_locks ON blocking_locks.locktype = blocked_locks.locktype
  WHERE NOT blocked_locks.granted;"

# Kill blocking query
psql -h localhost -U airflow -d airflow -c "SELECT pg_terminate_backend(BLOCKING_PID);"
```

**Option D: Resource exhaustion**
```bash
# Check worker resources
docker stats airflow-worker --no-stream

# Check MinIO connectivity
docker exec airflow-worker wget -O- http://minio:9000/minio/health/live

# Check Spark executor logs (if using Spark)
docker compose logs airflow-worker | grep "spark"
```

**Verification**
```bash
# Check DAG run status
curl -s "http://localhost:8080/api/v1/dags/quarterly_pipeline/dagRuns?limit=1" \
  --user "airflow:airflow" | jq '.dag_runs[0].state'
# Expected: "running" or "success"

# Monitor task progress
watch -n 10 'docker exec airflow-scheduler airflow tasks states-for-dag-run quarterly_pipeline LATEST'
```

#### Prevention
- Set task timeouts: `execution_timeout=timedelta(hours=2)`
- Configure retries: `retries=3, retry_delay=timedelta(minutes=5)`
- Enable email alerts for task failures
- Monitor executor queue depth

---

### 4. Data Quality Check Failures

#### Symptoms
- Alert: `DataQualityCheckFailed` (warning)
- High null percentage in feature tables
- Missing station data
- Unexpected value ranges (e.g., temperature outliers)

#### Diagnosis

**Step 1: Check data quality metrics**
```sql
-- Connect to database
psql -h localhost -U weatherinsight -d weatherinsight

-- Row counts
SELECT 'temperature' as product, COUNT(*) as rows FROM quarterly_temperature_features
UNION ALL
SELECT 'precipitation', COUNT(*) FROM quarterly_precipitation_features
UNION ALL
SELECT 'wind', COUNT(*) FROM quarterly_wind_features
UNION ALL
SELECT 'pressure', COUNT(*) FROM quarterly_pressure_features
UNION ALL
SELECT 'moisture', COUNT(*) FROM quarterly_moisture_features;

-- Null percentages
SELECT 
  'temperature' as product,
  COUNT(*) as total,
  COUNT(*) FILTER (WHERE mean_value IS NULL) as nulls,
  ROUND(100.0 * COUNT(*) FILTER (WHERE mean_value IS NULL) / COUNT(*), 2) as null_pct
FROM quarterly_temperature_features;

-- Value ranges
SELECT 
  MIN(mean_value) as min, 
  MAX(mean_value) as max,
  AVG(mean_value) as avg
FROM quarterly_temperature_features;
-- Expected: min ~-30°C, max ~+45°C for Germany
```

**Step 2: Check raw data**
```bash
# List recent raw files
docker exec minio mc ls --recursive minio/weatherinsight-raw/daily/ | tail -20

# Check file size (should be >100KB for typical daily file)
docker exec minio mc stat minio/weatherinsight-raw/daily/2026/01/20260101_daily.txt

# Download and inspect
docker exec minio mc cat minio/weatherinsight-raw/daily/2026/01/20260101_daily.txt | head -50
```

**Step 3: Check processing logs**
```bash
# Processing service logs
docker compose logs processing --tail=200 | grep -i "error\|warning\|failed"

# Aggregation service logs
docker compose logs aggregation --tail=200 | grep -i "error\|warning\|failed"

# Check for parsing errors
docker compose logs processing | grep "ParseError\|ValidationError"
```

**Step 4: Validate station coverage**
```sql
-- Unique stations in features
SELECT COUNT(DISTINCT station_id) as unique_stations 
FROM quarterly_temperature_features;
-- Expected: >50 stations for Germany

-- Stations with recent data
SELECT station_id, MAX(quarter_end) as latest_data 
FROM quarterly_temperature_features 
GROUP BY station_id 
ORDER BY latest_data DESC LIMIT 20;
```

#### Resolution

**Option A: Re-run processing pipeline**
```bash
# Trigger Airflow DAG
docker exec airflow-scheduler airflow dags trigger quarterly_pipeline

# Or run processing directly
docker compose run --rm processing python -m src.orchestrator \
  --start-date 2026-01-01 \
  --end-date 2026-03-31
```

**Option B: Re-ingest raw data**
```bash
# Sync specific date range
docker compose run --rm ingestion python -m src.orchestrator \
  --start-date 2026-01-01 \
  --end-date 2026-01-31

# Verify ingestion
docker exec minio mc ls --recursive minio/weatherinsight-raw/daily/2026/01/
```

**Option C: Clean and reprocess**
```bash
# Truncate affected feature tables
psql -h localhost -U weatherinsight -d weatherinsight -c "
  TRUNCATE quarterly_temperature_features, 
           quarterly_precipitation_features,
           quarterly_wind_features,
           quarterly_pressure_features,
           quarterly_moisture_features CASCADE;"

# Re-run full pipeline
docker exec airflow-scheduler airflow dags trigger quarterly_pipeline --conf '{"force": true}'
```

**Option D: Fix data quality rules**
```python
# Edit services/aggregation/src/feature_calculators.py
# Adjust thresholds if too strict:
TEMPERATURE_MIN = -50  # Was -30
TEMPERATURE_MAX = 50   # Was 45
NULL_THRESHOLD = 0.2   # Was 0.15 (15% → 20%)
```

**Verification**
```sql
-- Re-check metrics
SELECT 
  COUNT(*) as rows,
  COUNT(*) FILTER (WHERE mean_value IS NULL) as nulls,
  MIN(mean_value) as min,
  MAX(mean_value) as max
FROM quarterly_temperature_features;

-- Check freshness
SELECT MAX(quarter_end) as latest_quarter FROM quarterly_temperature_features;
-- Should be within last 3 months
```

#### Prevention
- Add data validation at ingestion stage
- Implement DWD API response validation
- Set up anomaly detection for outliers
- Archive raw data before reprocessing

---

### 5. Disk Space Running Low

#### Symptoms
- Alert: `DiskSpaceRunningLow` (critical)
- MinIO disk usage >85%
- Docker volumes filling up
- Services failing with "no space left on device"

#### Diagnosis

**Step 1: Check disk usage**
```bash
# Host system
df -h
# Look for: / or /var/lib/docker partitions

# Docker volumes
docker system df -v

# MinIO buckets
docker exec minio mc du --depth=2 minio/weatherinsight-raw
docker exec minio mc du --depth=2 minio/weatherinsight-curated
```

**Step 2: Identify large files**
```bash
# Largest objects in MinIO
docker exec minio mc ls --recursive minio/weatherinsight-raw | \
  awk '{print $4 "\t" $5 "/" $6}' | sort -h | tail -20

# Docker logs taking space
du -sh /var/lib/docker/containers/*/​*-json.log | sort -h | tail -10
```

**Step 3: Check retention policies**
```bash
# Old raw data
docker exec minio mc ls minio/weatherinsight-raw/daily/ | head -20
# Should have automatic lifecycle policy

# Database size
psql -h localhost -U weatherinsight -d weatherinsight -c "
  SELECT pg_size_pretty(pg_database_size('weatherinsight'));"
```

#### Resolution

**Option A: Clean Docker resources**
```bash
# Remove unused images
docker image prune -a --force

# Remove unused volumes
docker volume prune --force

# Remove stopped containers
docker container prune --force

# Clean build cache
docker builder prune --all --force
```

**Option B: Archive old raw data**
```bash
# Move data older than 6 months to archive bucket
docker exec minio mc mv --recursive \
  minio/weatherinsight-raw/daily/2025/ \
  minio/weatherinsight-archive/daily/2025/

# Or delete if archival not needed
docker exec minio mc rm --recursive --force \
  minio/weatherinsight-raw/daily/2025/
```

**Option C: Compress old data**
```bash
# Export and compress
docker exec minio mc cat minio/weatherinsight-raw/daily/2025/01/ > 202501.txt
gzip 202501.txt

# Re-upload compressed
docker exec -i minio mc pipe minio/weatherinsight-archive/daily/202501.txt.gz < 202501.txt.gz
```

**Option D: Extend storage**
```bash
# Add new volume to docker-compose.yml
volumes:
  minio_data:
    driver: local
    driver_opts:
      type: none
      device: /mnt/extra-storage
      o: bind

# Migrate data
docker compose stop minio
rsync -av /var/lib/docker/volumes/minio_data/ /mnt/extra-storage/
docker compose up -d minio
```

**Verification**
```bash
# Check disk usage after cleanup
df -h
docker system df

# Verify MinIO accessible
docker exec minio mc ls minio/weatherinsight-raw

# Test API access
curl http://localhost:8000/api/v1/stations?limit=5
```

#### Prevention
- Implement MinIO lifecycle policies (auto-delete after 365 days)
- Set Docker log rotation: `max-size: "10m", max-file: "3"`
- Monitor disk usage with Prometheus alerts
- Schedule regular cleanup jobs in Airflow

---

### 6. PostgreSQL Database Performance Issues

#### Symptoms
- Alert: `DatabaseSlowQueries` (warning)
- API latency spike in Grafana
- Query timeouts in application logs
- High database CPU usage

#### Diagnosis

**Step 1: Identify slow queries**
```sql
-- Current active queries
SELECT pid, now() - query_start as duration, state, query 
FROM pg_stat_activity 
WHERE state != 'idle' 
ORDER BY duration DESC;

-- Slow query statistics (requires pg_stat_statements extension)
SELECT query, 
       calls, 
       mean_exec_time, 
       total_exec_time,
       stddev_exec_time
FROM pg_stat_statements 
WHERE mean_exec_time > 1000  -- >1 second
ORDER BY mean_exec_time DESC 
LIMIT 20;
```

**Step 2: Check indexes**
```sql
-- Missing indexes
SELECT schemaname, tablename, attname, n_distinct, correlation
FROM pg_stats
WHERE schemaname = 'public' 
  AND tablename IN ('quarterly_temperature_features', 'quarterly_precipitation_features')
  AND attname IN ('station_id', 'quarter_start', 'quarter_end');

-- Index usage
SELECT schemaname, tablename, indexname, idx_scan, idx_tup_read, idx_tup_fetch
FROM pg_stat_user_indexes
WHERE schemaname = 'public'
ORDER BY idx_scan ASC;
-- Low idx_scan means index not being used
```

**Step 3: Check table bloat**
```sql
-- Table sizes
SELECT schemaname, tablename, 
       pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

-- Dead tuples
SELECT schemaname, tablename, n_live_tup, n_dead_tup, 
       ROUND(100 * n_dead_tup / NULLIF(n_live_tup + n_dead_tup, 0), 2) AS dead_pct
FROM pg_stat_user_tables
WHERE n_dead_tup > 1000
ORDER BY dead_pct DESC;
```

**Step 4: Check connection pool**
```sql
-- Active connections
SELECT state, COUNT(*) 
FROM pg_stat_activity 
WHERE datname = 'weatherinsight' 
GROUP BY state;

-- Waiting queries
SELECT COUNT(*) as waiting_queries 
FROM pg_stat_activity 
WHERE wait_event_type IS NOT NULL;
```

#### Resolution

**Option A: Add missing indexes**
```sql
-- Common query patterns
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_temp_station_quarter 
ON quarterly_temperature_features(station_id, quarter_start, quarter_end);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_precip_station_quarter 
ON quarterly_precipitation_features(station_id, quarter_start, quarter_end);

-- GIN index for faster text search if needed
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_stations_name_gin 
ON stations USING GIN(to_tsvector('english', name));
```

**Option B: VACUUM and ANALYZE**
```bash
# Vacuum all tables (reclaim space)
psql -h localhost -U weatherinsight -d weatherinsight -c "VACUUM ANALYZE;"

# Or specific table with FULL (locks table)
psql -h localhost -U weatherinsight -d weatherinsight -c "VACUUM FULL quarterly_temperature_features;"
```

**Option C: Optimize query**
```python
# Before (slow - fetches all columns)
stations = session.query(Station).filter(Station.state == 'Bayern').all()

# After (fast - fetch only needed columns)
stations = session.query(Station.id, Station.name).filter(Station.state == 'Bayern').all()

# Use pagination
stations = session.query(Station).limit(100).offset(0).all()
```

**Option D: Increase resources**
```yaml
# docker-compose.yml - increase PostgreSQL resources
postgres:
  deploy:
    resources:
      limits:
        cpus: '2.0'
        memory: 4G
  environment:
    - POSTGRES_SHARED_BUFFERS=1GB
    - POSTGRES_WORK_MEM=32MB
    - POSTGRES_MAINTENANCE_WORK_MEM=256MB
```

**Verification**
```bash
# Check query performance
psql -h localhost -U weatherinsight -d weatherinsight -c "
  EXPLAIN ANALYZE 
  SELECT * FROM quarterly_temperature_features 
  WHERE station_id = '00433' AND quarter_start >= '2026-01-01';"
# Should show Index Scan instead of Seq Scan

# Monitor metrics
curl -s 'http://localhost:9090/api/v1/query?query=pg_stat_database_xact_commit' | jq
```

#### Prevention
- Enable `pg_stat_statements` extension
- Set up automated VACUUM schedule
- Add query performance tests in CI/CD
- Monitor index usage and add as needed
- Set statement_timeout to prevent runaway queries

---

## Escalation Paths

| Issue Type | L1 Response | L2 Escalation | L3 Escalation |
|------------|------------|---------------|---------------|
| API Issues | On-call engineer | Platform team lead | CTO |
| Database | On-call engineer | DBA team | Database architect |
| Pipeline | Data engineer | Data engineering lead | Data platform architect |
| Infrastructure | DevOps engineer | Platform team | Cloud architect |

## Post-Incident Tasks

1. **Document Incident**
   - Create post-mortem document
   - Timeline of events
   - Root cause analysis
   - Action items

2. **Update Runbooks**
   - Add new failure scenarios
   - Update resolution steps
   - Document lessons learned

3. **Improve Monitoring**
   - Add alerts for new failure modes
   - Adjust alert thresholds if needed
   - Create new Grafana dashboards

4. **Preventive Measures**
   - Code fixes
   - Infrastructure improvements
   - Process changes
   - Team training

## Additional Resources

- [Monitoring Guide](./MONITORING_GUIDE.md) - Metrics and dashboards
- [Runbook](./runbook.md) - Operational procedures
- [Testing Strategy](./TESTING_STRATEGY.md) - Test execution
- [API Documentation](../services/api/README.md) - API reference
