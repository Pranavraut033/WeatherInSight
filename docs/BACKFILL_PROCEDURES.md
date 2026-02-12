# WeatherInsight Backfill Procedures

## Overview
This document provides detailed procedures for backfilling historical data in WeatherInsight, including strategies for different scenarios, troubleshooting, and validation.

## Table of Contents
1. [Backfill Strategies](#backfill-strategies)
2. [Prerequisites](#prerequisites)
3. [Execution Procedures](#execution-procedures)
4. [Monitoring & Troubleshooting](#monitoring--troubleshooting)
5. [Validation](#validation)
6. [Common Scenarios](#common-scenarios)
7. [Recovery Procedures](#recovery-procedures)

---

## Backfill Strategies

### Strategy Selection Matrix

| Scenario | Strategy | Duration | Risk | Recommended |
|----------|----------|----------|------|-------------|
| New product type | Incremental by year | 2-3 days/year | Low | ✅ Yes |
| Missing quarters | Targeted backfill | Hours | Low | ✅ Yes |
| Data quality issue | Reprocess affected | Varies | Medium | ✅ Yes |
| Full reprocessing | Parallel by year | 1-2 weeks | High | ⚠️ Carefully |
| Schema migration | Staged migration | 3-5 days | High | ⚠️ With testing |

### Incremental Backfill
**When to use**: Adding new product types, filling gaps, routine historical loads

**Pros**:
- Lower resource usage
- Easier to monitor
- Can pause/resume
- Lower failure impact

**Cons**:
- Longer total duration
- Sequential processing

### Parallel Backfill
**When to use**: Time-sensitive loads, full system initialization

**Pros**:
- Faster completion
- Efficient resource usage

**Cons**:
- Higher resource requirements
- Harder to troubleshoot
- Risk of cascade failures

---

## Prerequisites

### System Requirements
```bash
# Verify system capacity
# Minimum for backfill:
# - 50 GB free disk space per year
# - 16 GB available RAM
# - 4 vCPU available

# Check disk space
df -h /var/lib/docker
df -h /opt/weatherinsight

# Check available memory
free -h

# Check CPU load
uptime
```

### Service Health
```bash
# Verify all services are running
docker-compose ps

# Expected output: All services "Up"
# - postgres: Up
# - minio: Up
# - airflow-scheduler: Up
# - airflow-webserver: Up
# - spark-master: Up
# - spark-worker: Up

# Check service health endpoints
curl http://localhost:8000/health  # API
curl http://localhost:9000/minio/health/live  # MinIO
```

### Database Preparation
```bash
# Check current data state
docker exec postgres psql -U weatherinsight -d weatherinsight << 'EOF'
SELECT 
    'Temperature' as product,
    COUNT(*) as rows,
    MIN(year) as min_year,
    MAX(year) as max_year,
    COUNT(DISTINCT station_id) as stations
FROM quarterly_temperature_features
UNION ALL
SELECT 'Precipitation', COUNT(*), MIN(year), MAX(year), COUNT(DISTINCT station_id)
FROM quarterly_precipitation_features
UNION ALL
SELECT 'Wind', COUNT(*), MIN(year), MAX(year), COUNT(DISTINCT station_id)
FROM quarterly_wind_features
UNION ALL
SELECT 'Pressure', COUNT(*), MIN(year), MAX(year), COUNT(DISTINCT station_id)
FROM quarterly_pressure_features
UNION ALL
SELECT 'Humidity', COUNT(*), MIN(year), MAX(year), COUNT(DISTINCT station_id)
FROM quarterly_humidity_features;
EOF
```

### Backup Before Major Backfills
```bash
# Create database backup
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
docker exec postgres pg_dump -U weatherinsight weatherinsight | \
  gzip > /backups/pre_backfill_${TIMESTAMP}.sql.gz

# Verify backup
gunzip -c /backups/pre_backfill_${TIMESTAMP}.sql.gz | head -n 100
```

---

## Execution Procedures

### Procedure 1: Single Quarter Backfill

**Use case**: Fill a missing quarter or reprocess specific quarter

#### Step 1: Identify Target Quarter
```bash
# Verify quarter is missing or needs reprocessing
docker exec postgres psql -U weatherinsight -d weatherinsight -c \
  "SELECT COUNT(*) FROM quarterly_temperature_features WHERE year=2023 AND quarter=1;"

# Expected: 0 if missing, >0 if needs reprocessing
```

#### Step 2: Trigger Backfill DAG
```bash
# Access Airflow CLI
docker exec airflow-scheduler airflow dags trigger weatherinsight_backfill \
  --conf '{
    "start_year": 2023,
    "end_year": 2023,
    "quarters": [1],
    "products": ["air_temperature", "precipitation", "wind", "pressure", "cloud_cover"],
    "force_reprocess": false
  }'

# Get DAG run ID
docker exec airflow-scheduler airflow dags list-runs \
  -d weatherinsight_backfill \
  --state running \
  -o json | jq -r '.[0].run_id'
```

#### Step 3: Monitor Progress
```bash
# Watch DAG execution in Airflow UI
open http://localhost:8080/dags/weatherinsight_backfill/grid

# Or monitor via CLI
watch -n 10 "docker exec airflow-scheduler airflow dags list-runs \
  -d weatherinsight_backfill --state running -o table"

# Expected duration: 2-4 hours per quarter
```

#### Step 4: Validate Results
```bash
# Check row counts
docker exec postgres psql -U weatherinsight -d weatherinsight << 'EOF'
SELECT 
    table_name,
    COUNT(*) as rows
FROM (
    SELECT 'temperature' as table_name FROM quarterly_temperature_features WHERE year=2023 AND quarter=1
    UNION ALL
    SELECT 'precipitation' FROM quarterly_precipitation_features WHERE year=2023 AND quarter=1
    UNION ALL
    SELECT 'wind' FROM quarterly_wind_features WHERE year=2023 AND quarter=1
    UNION ALL
    SELECT 'pressure' FROM quarterly_pressure_features WHERE year=2023 AND quarter=1
    UNION ALL
    SELECT 'humidity' FROM quarterly_humidity_features WHERE year=2023 AND quarter=1
) counts
GROUP BY table_name;
EOF

# Expected: ~200-500 rows per product (varies by active stations)
```

---

### Procedure 2: Full Year Backfill

**Use case**: Add complete year of historical data

#### Step 1: Plan Execution
```bash
# Estimate duration: 8-16 hours per year (all products)
# Estimate storage: ~50 GB raw + 10 GB processed per year

# Check available resources
df -h /var/lib/docker
free -h
```

#### Step 2: Sequential Year Backfill (Recommended)
```bash
# Process one year at a time to avoid resource exhaustion
for year in {2020..2023}; do
  echo "Starting backfill for $year"
  
  docker exec airflow-scheduler airflow dags trigger weatherinsight_backfill \
    --conf "{
      \"start_year\": $year,
      \"end_year\": $year,
      \"quarters\": [1, 2, 3, 4],
      \"products\": [\"air_temperature\", \"precipitation\", \"wind\", \"pressure\", \"cloud_cover\"],
      \"force_reprocess\": false
    }"
  
  # Wait for completion before starting next year
  while true; do
    STATUS=$(docker exec airflow-scheduler airflow dags list-runs \
      -d weatherinsight_backfill --state running -o json | jq -r 'length')
    
    if [ "$STATUS" = "0" ]; then
      echo "Year $year completed"
      break
    fi
    
    echo "Year $year in progress... (waiting 5 minutes)"
    sleep 300
  done
  
  # Validate year completion
  docker exec postgres psql -U weatherinsight -d weatherinsight -c \
    "SELECT COUNT(*) FROM quarterly_temperature_features WHERE year=$year;"
  
  echo "Completed $year, waiting 10 minutes before next year..."
  sleep 600
done
```

#### Step 3: Parallel Year Backfill (Advanced)
```bash
# WARNING: Requires significant resources (32+ GB RAM, 8+ vCPU)
# Only use if system has capacity and urgent timeline

# Trigger multiple years in parallel (max 2-3 concurrent)
for year in 2020 2021; do
  docker exec airflow-scheduler airflow dags trigger weatherinsight_backfill \
    --conf "{
      \"start_year\": $year,
      \"end_year\": $year,
      \"quarters\": [1, 2, 3, 4],
      \"products\": [\"air_temperature\", \"precipitation\", \"wind\", \"pressure\", \"cloud_cover\"],
      \"force_reprocess\": false
    }"
  echo "Triggered year $year"
done

# Monitor all runs
watch -n 30 "docker exec airflow-scheduler airflow dags list-runs \
  -d weatherinsight_backfill --state running -o table"
```

---

### Procedure 3: Product-Specific Backfill

**Use case**: Add new product type to existing time range

#### Step 1: Identify Date Range
```bash
# Find existing data range
docker exec postgres psql -U weatherinsight -d weatherinsight -c \
  "SELECT MIN(year) as min_year, MAX(year) as max_year 
   FROM quarterly_temperature_features;"

# Use this range for new product
```

#### Step 2: Backfill New Product
```bash
# Example: Adding humidity data to existing 2019-2023 range
docker exec airflow-scheduler airflow dags trigger weatherinsight_backfill \
  --conf '{
    "start_year": 2019,
    "end_year": 2023,
    "quarters": [1, 2, 3, 4],
    "products": ["cloud_cover"],
    "force_reprocess": false
  }'

# Monitor specifically for new product
docker-compose logs -f airflow-worker | grep "cloud_cover"
```

#### Step 3: Verify Alignment
```bash
# Check that new product has same coverage as existing
docker exec postgres psql -U weatherinsight -d weatherinsight << 'EOF'
WITH counts AS (
  SELECT year, quarter, COUNT(*) as temp_count 
  FROM quarterly_temperature_features 
  GROUP BY year, quarter
), new_counts AS (
  SELECT year, quarter, COUNT(*) as hum_count 
  FROM quarterly_humidity_features 
  GROUP BY year, quarter
)
SELECT 
  COALESCE(c.year, n.year) as year,
  COALESCE(c.quarter, n.quarter) as quarter,
  c.temp_count,
  n.hum_count,
  CASE 
    WHEN ABS(c.temp_count - n.hum_count) > 10 THEN 'MISMATCH'
    ELSE 'OK'
  END as status
FROM counts c
FULL OUTER JOIN new_counts n ON c.year = n.year AND c.quarter = n.quarter
ORDER BY year, quarter;
EOF
```

---

### Procedure 4: Targeted Reprocessing

**Use case**: Fix data quality issues in specific quarters

#### Step 1: Identify Affected Quarters
```bash
# Run data quality checks
docker exec airflow-scheduler airflow dags trigger weatherinsight_data_quality

# Review quality check results
docker exec postgres psql -U weatherinsight -d weatherinsight << 'EOF'
SELECT 
  year, 
  quarter, 
  product,
  issue_type,
  issue_count
FROM data_quality_issues
WHERE severity = 'HIGH'
ORDER BY year DESC, quarter DESC;
EOF
```

#### Step 2: Delete Corrupted Data
```bash
# CAREFUL: This deletes data permanently
# Always backup first!

# Delete specific quarter/product
docker exec postgres psql -U weatherinsight -d weatherinsight << 'EOF'
BEGIN;

DELETE FROM quarterly_temperature_features 
WHERE year = 2023 AND quarter = 2;

-- Verify deletion
SELECT COUNT(*) FROM quarterly_temperature_features 
WHERE year = 2023 AND quarter = 2;

-- If correct count (0), commit. Otherwise rollback.
COMMIT;  -- or ROLLBACK;
EOF
```

#### Step 3: Reprocess with Force Flag
```bash
docker exec airflow-scheduler airflow dags trigger weatherinsight_backfill \
  --conf '{
    "start_year": 2023,
    "end_year": 2023,
    "quarters": [2],
    "products": ["air_temperature"],
    "force_reprocess": true
  }'
```

---

## Monitoring & Troubleshooting

### Real-Time Monitoring

#### Airflow UI Dashboard
```bash
# Access Airflow UI
open http://localhost:8080/dags/weatherinsight_backfill/grid

# Key metrics to watch:
# - Task success rate (should be >95%)
# - Task duration (compare to historical average)
# - Queue depth (should not grow unbounded)
```

#### Grafana Dashboards
```bash
# Access Grafana
open http://localhost:3002/d/pipeline_overview

# Monitor:
# - Ingestion throughput (files/hour)
# - Processing throughput (records/second)
# - Database write rate (rows/second)
# - Error rate (should be <1%)
```

#### CLI Monitoring
```bash
# Create monitoring script
cat > /opt/scripts/monitor_backfill.sh << 'EOF'
#!/bin/bash

while true; do
  clear
  echo "=== Backfill Progress Monitor ==="
  echo "Time: $(date)"
  echo ""
  
  echo "=== Active DAG Runs ==="
  docker exec airflow-scheduler airflow dags list-runs \
    -d weatherinsight_backfill --state running -o table
  echo ""
  
  echo "=== Recent Task Failures ==="
  docker exec airflow-scheduler airflow tasks list weatherinsight_backfill \
    | tail -5
  echo ""
  
  echo "=== Database Row Counts ==="
  docker exec postgres psql -U weatherinsight -d weatherinsight -t -c \
    "SELECT 'Temperature', COUNT(*) FROM quarterly_temperature_features 
     UNION ALL SELECT 'Precipitation', COUNT(*) FROM quarterly_precipitation_features;"
  echo ""
  
  echo "=== Disk Usage ==="
  df -h /var/lib/docker | tail -1
  echo ""
  
  sleep 60
done
EOF

chmod +x /opt/scripts/monitor_backfill.sh
/opt/scripts/monitor_backfill.sh
```

### Common Issues & Solutions

#### Issue 1: Slow Download Speeds
**Symptoms**: Ingestion tasks taking >30 minutes per file

**Diagnosis**:
```bash
# Check network connectivity to DWD
docker exec ingestion curl -o /dev/null -w "%{speed_download}" \
  https://opendata.dwd.de/climate_environment/CDC/observations_germany/climate/hourly/air_temperature/recent/stundenwerte_TU_00433_akt.zip

# Expected: >100000 bytes/sec (100 KB/s)
```

**Solution**:
```bash
# If slow, check:
# 1. Network bandwidth limits
# 2. DWD server issues (check status page)
# 3. DNS resolution

# Temporary mitigation: Increase task timeout
docker exec airflow-scheduler airflow dags pause weatherinsight_backfill
# Edit DAG file to increase timeout from 3600 to 7200 seconds
docker exec airflow-scheduler airflow dags unpause weatherinsight_backfill
```

#### Issue 2: Out of Memory Errors
**Symptoms**: Spark tasks failing with OOM errors

**Diagnosis**:
```bash
# Check memory usage
docker stats --no-stream spark-worker

# Check Spark logs
docker-compose logs spark-worker | grep -i "out of memory"
```

**Solution**:
```bash
# Option 1: Increase Spark memory allocation
# Edit docker-compose.yml:
# services:
#   spark-worker:
#     environment:
#       - SPARK_WORKER_MEMORY=16G  # Increase from 8G

docker-compose up -d spark-worker

# Option 2: Process fewer quarters concurrently
# Reduce parallelism in backfill DAG configuration
docker exec airflow-scheduler airflow variables set backfill_max_active_tasks 2
```

#### Issue 3: Database Connection Pool Exhausted
**Symptoms**: Tasks failing with "connection pool exhausted"

**Diagnosis**:
```bash
# Check active connections
docker exec postgres psql -U weatherinsight -d weatherinsight -c \
  "SELECT count(*) FROM pg_stat_activity WHERE state = 'active';"

# Check max connections
docker exec postgres psql -U postgres -c "SHOW max_connections;"
```

**Solution**:
```bash
# Increase max connections
docker exec postgres psql -U postgres -c \
  "ALTER SYSTEM SET max_connections = 200;"

# Restart PostgreSQL
docker-compose restart postgres

# Or reduce concurrent tasks
docker exec airflow-scheduler airflow variables set backfill_max_active_tasks 5
```

#### Issue 4: Duplicate Data
**Symptoms**: More rows than expected, duplicate records

**Diagnosis**:
```bash
# Check for duplicates
docker exec postgres psql -U weatherinsight -d weatherinsight << 'EOF'
SELECT station_id, year, quarter, COUNT(*)
FROM quarterly_temperature_features
GROUP BY station_id, year, quarter
HAVING COUNT(*) > 1
ORDER BY COUNT(*) DESC
LIMIT 10;
EOF
```

**Solution**:
```bash
# Remove duplicates (keep most recent)
docker exec postgres psql -U weatherinsight -d weatherinsight << 'EOF'
BEGIN;

WITH duplicates AS (
  SELECT id, 
    ROW_NUMBER() OVER (
      PARTITION BY station_id, year, quarter 
      ORDER BY created_at DESC
    ) as rn
  FROM quarterly_temperature_features
)
DELETE FROM quarterly_temperature_features
WHERE id IN (SELECT id FROM duplicates WHERE rn > 1);

COMMIT;
EOF

# Prevent future duplicates: Add unique constraint
docker exec postgres psql -U weatherinsight -d weatherinsight << 'EOF'
ALTER TABLE quarterly_temperature_features
ADD CONSTRAINT unique_station_year_quarter 
UNIQUE (station_id, year, quarter);
EOF
```

---

## Validation

### Validation Checklist

After completing a backfill, run through this checklist:

#### 1. Row Count Validation
```bash
docker exec postgres psql -U weatherinsight -d weatherinsight << 'EOF'
SELECT 
  table_name,
  COUNT(*) as total_rows,
  COUNT(DISTINCT station_id) as unique_stations,
  COUNT(DISTINCT year) as unique_years,
  MIN(year) as min_year,
  MAX(year) as max_year
FROM (
  SELECT 'temperature' as table_name, station_id, year FROM quarterly_temperature_features
  UNION ALL
  SELECT 'precipitation', station_id, year FROM quarterly_precipitation_features
  UNION ALL
  SELECT 'wind', station_id, year FROM quarterly_wind_features
  UNION ALL
  SELECT 'pressure', station_id, year FROM quarterly_pressure_features
  UNION ALL
  SELECT 'humidity', station_id, year FROM quarterly_humidity_features
) all_data
GROUP BY table_name;
EOF

# Expected results:
# - temperature: 8000-12000 rows (2000-3002 per year, 500-750 per quarter)
# - Similar for other products
# - ~200-300 unique stations
```

#### 2. Completeness Check
```bash
# Check for missing quarters
docker exec postgres psql -U weatherinsight -d weatherinsight << 'EOF'
WITH expected_quarters AS (
  SELECT year, quarter
  FROM generate_series(2019, 2023) AS year
  CROSS JOIN generate_series(1, 4) AS quarter
)
SELECT 
  eq.year,
  eq.quarter,
  CASE WHEN tf.count IS NULL THEN 'MISSING' ELSE 'OK' END as temperature,
  CASE WHEN pf.count IS NULL THEN 'MISSING' ELSE 'OK' END as precipitation,
  CASE WHEN wf.count IS NULL THEN 'MISSING' ELSE 'OK' END as wind,
  CASE WHEN prf.count IS NULL THEN 'MISSING' ELSE 'OK' END as pressure,
  CASE WHEN hf.count IS NULL THEN 'MISSING' ELSE 'OK' END as humidity
FROM expected_quarters eq
LEFT JOIN (SELECT year, quarter, COUNT(*) as count FROM quarterly_temperature_features GROUP BY year, quarter) tf 
  ON eq.year = tf.year AND eq.quarter = tf.quarter
LEFT JOIN (SELECT year, quarter, COUNT(*) as count FROM quarterly_precipitation_features GROUP BY year, quarter) pf 
  ON eq.year = pf.year AND eq.quarter = pf.quarter
LEFT JOIN (SELECT year, quarter, COUNT(*) as count FROM quarterly_wind_features GROUP BY year, quarter) wf 
  ON eq.year = wf.year AND eq.quarter = wf.quarter
LEFT JOIN (SELECT year, quarter, COUNT(*) as count FROM quarterly_pressure_features GROUP BY year, quarter) prf 
  ON eq.year = prf.year AND eq.quarter = prf.quarter
LEFT JOIN (SELECT year, quarter, COUNT(*) as count FROM quarterly_humidity_features GROUP BY year, quarter) hf 
  ON eq.year = hf.year AND eq.quarter = hf.quarter
WHERE tf.count IS NULL 
   OR pf.count IS NULL 
   OR wf.count IS NULL 
   OR prf.count IS NULL 
   OR hf.count IS NULL
ORDER BY year, quarter;
EOF

# Expected: Empty result (no missing quarters)
```

#### 3. Data Quality Validation
```bash
# Run automated quality checks
docker exec airflow-scheduler airflow dags trigger weatherinsight_data_quality

# Wait for completion and review results
docker exec postgres psql -U weatherinsight -d weatherinsight -c \
  "SELECT * FROM data_quality_results ORDER BY check_timestamp DESC LIMIT 20;"

# Expected: All checks pass (status='PASS')
```

#### 4. Metadata Validation
```bash
# Verify dataset versions are recorded
docker exec postgres psql -U weatherinsight -d weatherinsight << 'EOF'
SELECT 
  dataset_name,
  version,
  start_date,
  end_date,
  record_count,
  created_at
FROM dataset_versions
WHERE created_at > NOW() - INTERVAL '7 days'
ORDER BY created_at DESC;
EOF

# Expected: One version entry per product/quarter backfilled
```

#### 5. API Validation
```bash
# Test API endpoints for backfilled data
curl -s "http://localhost:8000/api/v1/features/temperature?year=2023&quarter=1&limit=5" | jq .

# Expected: Returns data with correct year/quarter
```

---

## Common Scenarios

### Scenario 1: Initial System Setup (5 Years Historical)

**Timeline**: 3-5 days

```bash
#!/bin/bash
# Full historical backfill script

YEARS=(2019 2020 2021 2022 2023)
PRODUCTS=("air_temperature" "precipitation" "wind" "pressure" "cloud_cover")

for YEAR in "${YEARS[@]}"; do
  echo "=== Starting backfill for $YEAR ==="
  
  docker exec airflow-scheduler airflow dags trigger weatherinsight_backfill \
    --conf "{
      \"start_year\": $YEAR,
      \"end_year\": $YEAR,
      \"quarters\": [1, 2, 3, 4],
      \"products\": [\"air_temperature\", \"precipitation\", \"wind\", \"pressure\", \"cloud_cover\"],
      \"force_reprocess\": false
    }"
  
  # Wait for completion
  while [ "$(docker exec airflow-scheduler airflow dags list-runs -d weatherinsight_backfill --state running -o json | jq -r 'length')" != "0" ]; do
    echo "Year $YEAR in progress..."
    sleep 300
  done
  
  echo "=== Completed $YEAR ==="
  
  # Validate
  /opt/scripts/validate_year.sh $YEAR
  
  # Brief pause between years
  sleep 600
done

echo "=== Full backfill complete ==="
```

### Scenario 2: Adding New Product Type

**Timeline**: 1-2 days (for 5 years)

```bash
# Add humidity to existing 2019-2023 coverage
docker exec airflow-scheduler airflow dags trigger weatherinsight_backfill \
  --conf '{
    "start_year": 2019,
    "end_year": 2023,
    "quarters": [1, 2, 3, 4],
    "products": ["cloud_cover"],
    "force_reprocess": false
  }'
```

### Scenario 3: Quarterly Maintenance (Missed Quarter)

**Timeline**: 2-4 hours

```bash
# Fill in Q1 2024 after system downtime
docker exec airflow-scheduler airflow dags trigger weatherinsight_backfill \
  --conf '{
    "start_year": 2024,
    "end_year": 2024,
    "quarters": [1],
    "products": ["air_temperature", "precipitation", "wind", "pressure", "cloud_cover"],
    "force_reprocess": false
  }'
```

### Scenario 4: Data Quality Issue (Reprocess Quarter)

**Timeline**: 3-5 hours

```bash
# Delete bad data
docker exec postgres psql -U weatherinsight -d weatherinsight << 'EOF'
DELETE FROM quarterly_temperature_features WHERE year=2023 AND quarter=2;
DELETE FROM quarterly_precipitation_features WHERE year=2023 AND quarter=2;
DELETE FROM quarterly_wind_features WHERE year=2023 AND quarter=2;
DELETE FROM quarterly_pressure_features WHERE year=2023 AND quarter=2;
DELETE FROM quarterly_humidity_features WHERE year=2023 AND quarter=2;
EOF

# Reprocess with force flag
docker exec airflow-scheduler airflow dags trigger weatherinsight_backfill \
  --conf '{
    "start_year": 2023,
    "end_year": 2023,
    "quarters": [2],
    "products": ["air_temperature", "precipitation", "wind", "pressure", "cloud_cover"],
    "force_reprocess": true
  }'
```

---

## Recovery Procedures

### Recovery from Failed Backfill

#### Step 1: Identify Failure Point
```bash
# Check Airflow task logs
docker exec airflow-scheduler airflow tasks list weatherinsight_backfill | grep failed

# View specific task log
docker exec airflow-scheduler airflow tasks log weatherinsight_backfill <task_id> <execution_date>
```

#### Step 2: Clean Up Partial Data
```bash
# Identify incomplete quarters
docker exec postgres psql -U weatherinsight -d weatherinsight << 'EOF'
SELECT year, quarter, COUNT(*) as row_count
FROM quarterly_temperature_features
GROUP BY year, quarter
HAVING COUNT(*) < 100  -- Threshold for incomplete data
ORDER BY year, quarter;
EOF

# Delete incomplete data
docker exec postgres psql -U weatherinsight -d weatherinsight << 'EOF'
DELETE FROM quarterly_temperature_features 
WHERE year = <YEAR> AND quarter = <QUARTER>;
-- Repeat for other products
EOF
```

#### Step 3: Resume Backfill
```bash
# Clear failed DAG run
docker exec airflow-scheduler airflow dags delete weatherinsight_backfill \
  --yes \
  --execution-date <FAILED_DATE>

# Restart backfill
docker exec airflow-scheduler airflow dags trigger weatherinsight_backfill \
  --conf '{...}'
```

### Recovery from Database Corruption

#### Step 1: Stop All Writes
```bash
# Pause all DAGs
docker exec airflow-scheduler airflow dags pause weatherinsight_quarterly_pipeline
docker exec airflow-scheduler airflow dags pause weatherinsight_backfill

# Stop API (if accepting writes)
docker-compose stop api
```

#### Step 2: Restore from Backup
```bash
# List available backups
ls -lh /backups/*.sql.gz

# Restore most recent clean backup
docker exec postgres psql -U postgres -c "DROP DATABASE weatherinsight;"
docker exec postgres psql -U postgres -c "CREATE DATABASE weatherinsight;"
gunzip -c /backups/weatherinsight_20240207.sql.gz | \
  docker exec -i postgres psql -U weatherinsight -d weatherinsight
```

#### Step 3: Replay Missing Data
```bash
# Identify date range to replay
# (from backup date to current)

docker exec airflow-scheduler airflow dags trigger weatherinsight_backfill \
  --conf '{
    "start_year": 2024,
    "end_year": 2024,
    "quarters": [1],
    "products": ["air_temperature", "precipitation", "wind", "pressure", "cloud_cover"],
    "force_reprocess": true
  }'
```

#### Step 4: Resume Normal Operations
```bash
# Unpause DAGs
docker exec airflow-scheduler airflow dags unpause weatherinsight_quarterly_pipeline
docker exec airflow-scheduler airflow dags unpause weatherinsight_backfill

# Restart API
docker-compose start api
```

---

## Performance Optimization

### Tune Parallelism
```bash
# Adjust based on system capacity
docker exec airflow-scheduler airflow config set-value core parallelism 16
docker exec airflow-scheduler airflow config set-value core max_active_tasks_per_dag 8
```

### Optimize Database Writes
```bash
# Increase Spark batch size
# Edit services/aggregation/src/config.py:
# BATCH_SIZE = 10000  # Increase from 5000

# Tune PostgreSQL for bulk writes
docker exec postgres psql -U postgres << 'EOF'
ALTER SYSTEM SET shared_buffers = '4GB';
ALTER SYSTEM SET work_mem = '256MB';
ALTER SYSTEM SET maintenance_work_mem = '1GB';
ALTER SYSTEM SET effective_cache_size = '12GB';
EOF

docker-compose restart postgres
```

### Monitor Resource Usage
```bash
# Create monitoring dashboard
watch -n 10 "echo '=== CPU Usage ===' && \
  docker stats --no-stream --format 'table {{.Container}}\t{{.CPUPerc}}' && \
  echo '' && \
  echo '=== Memory Usage ===' && \
  docker stats --no-stream --format 'table {{.Container}}\t{{.MemUsage}}'"
```

---

## Best Practices

1. **Always backup before major backfills**
2. **Start with small test runs** (single quarter, single product)
3. **Monitor resource usage** throughout execution
4. **Validate data quality** after each backfill
5. **Document any issues** encountered for future reference
6. **Schedule large backfills** during low-traffic periods
7. **Use force_reprocess=false** by default (prevents accidental overwrites)
8. **Keep backfill logs** for at least 90 days
9. **Test rollback procedures** before production backfills
10. **Communicate** with stakeholders about backfill schedules and expected downtime

---

## Version History
- v1.0.0 (2026-02-08): Initial backfill procedures documentation
