# WeatherInsight Operations Handover Guide

## Document Purpose
This guide provides everything needed for operations teams to successfully run, maintain, and troubleshoot the WeatherInsight system in production.

## Table of Contents
1. [System Overview](#system-overview)
2. [Daily Operations](#daily-operations)
3. [Weekly Tasks](#weekly-tasks)
4. [Monthly Tasks](#monthly-tasks)
5. [Quarterly Operations](#quarterly-operations)
6. [Monitoring & Alerts](#monitoring--alerts)
7. [Troubleshooting](#troubleshooting)
8. [Emergency Procedures](#emergency-procedures)
9. [Contacts & Escalation](#contacts--escalation)
10. [Reference Materials](#reference-materials)

---

## System Overview

### Architecture Summary
WeatherInsight is a batch data pipeline that ingests hourly weather observations from DWD (German Weather Service), processes them quarterly, and serves aggregated features via REST API.

**Data Flow**:
```
DWD OpenData → Ingestion → MinIO (raw) → Spark Processing → MinIO (staging) 
→ Spark Aggregation → PostgreSQL (curated) → FastAPI → End Users
```

**Components**:
- **Ingestion**: Downloads DWD files, verifies checksums, stores in MinIO
- **Metadata**: Tracks schemas, dataset versions, and lineage
- **Processing**: Parses raw files, normalizes, validates, stages in Parquet
- **Aggregation**: Computes quarterly features, writes to PostgreSQL
- **Orchestrator**: Airflow schedules and coordinates pipeline
- **API**: FastAPI serves feature data to clients
- **Monitoring**: Prometheus, Grafana, Alertmanager track health

### Production Environment

**Infrastructure**:
- **Server**: Single-node Docker Compose (or Kubernetes cluster)
- **OS**: Ubuntu 22.04 LTS
- **Resources**: 16 vCPU, 128 GB RAM, 2 TB SSD
- **Network**: Private VPC, Load balancer for API

**Services**:
| Service | Port | Purpose | Status Check |
|---------|------|---------|--------------|
| PostgreSQL | 5432 | Feature database | `curl postgres:5432` |
| MinIO | 9000, 9001 | Object storage | `curl http://minio:9000/minio/health/live` |
| Airflow Webserver | 8080 | Pipeline UI | `curl http://airflow:8080/health` |
| Airflow Scheduler | - | Task scheduling | Check process |
| Spark Master | 7077, 8081 | Compute cluster | `curl http://spark-master:8081` |
| Spark Workers | - | Compute nodes | Check in Spark UI |
| FastAPI | 8000 | Data API | `curl http://api:8000/health` |
| Prometheus | 9090 | Metrics collection | `curl http://prometheus:9090/-/healthy` |
| Grafana | 3002 | Dashboards | `curl http://grafana:3002/api/health` |
| Alertmanager | 9093 | Alert routing | `curl http://alertmanager:9093/-/healthy` |

**Data Products**:
- Temperature features (14 features)
- Precipitation features (15 features)
- Wind features (14 features)
- Pressure features (13 features)
- Humidity features (11 features)

**SLAs**:
- API availability: 99.5% uptime
- API latency: p95 < 200ms, p99 < 500ms
- Data freshness: Within 7 days of quarter end
- Quarterly pipeline: Complete within 24 hours

---

## Daily Operations

### Morning Health Check (Every Day, 9:00 AM)

#### Step 1: Service Status
```bash
# SSH to production server
ssh prod-weatherinsight.example.com

# Check all services are running
cd /opt/weatherinsight
docker-compose ps

# Expected: All services "Up" and healthy
# If any service is down, see [Troubleshooting](#troubleshooting)
```

#### Step 2: Review Overnight Activity
```bash
# Check Airflow DAG runs from last 24 hours
docker exec airflow-scheduler airflow dags list-runs \
  --state failed \
  --end-date $(date +%Y-%m-%d) \
  -o table

# Expected: No failed runs
# If failures found, investigate in Airflow UI
```

#### Step 3: Check Critical Alerts
```bash
# Access Grafana
open https://grafana.weatherinsight.example.com

# Review dashboards:
# 1. Pipeline Overview - Check for failed tasks
# 2. API Performance - Verify latency within SLA
# 3. Infrastructure - Check resource usage < 80%
# 4. Data Quality - Verify no quality issues

# Or check via CLI:
curl -s http://prometheus:9090/api/v1/alerts | jq '.data.alerts[] | select(.state=="firing")'

# Expected: No active alerts
```

#### Step 4: Verify Data Freshness
```bash
# Check latest data in database
docker exec postgres psql -U weatherinsight -d weatherinsight << 'EOF'
SELECT 
  'Temperature' as product,
  MAX(year) as latest_year,
  MAX(quarter) as latest_quarter
FROM quarterly_temperature_features
UNION ALL
SELECT 'Precipitation', MAX(year), MAX(quarter)
FROM quarterly_precipitation_features
UNION ALL
SELECT 'Wind', MAX(year), MAX(quarter)
FROM quarterly_wind_features
UNION ALL
SELECT 'Pressure', MAX(year), MAX(quarter)
FROM quarterly_pressure_features
UNION ALL
SELECT 'Humidity', MAX(year), MAX(quarter)
FROM quarterly_humidity_features;
EOF

# Expected: Latest quarter should be current or previous quarter
# If data is stale (>1 quarter behind), investigate pipeline
```

#### Step 5: Review API Metrics
```bash
# Check API request counts and error rates
docker exec prometheus promtool query instant \
  'sum(rate(http_requests_total[24h]))'

docker exec prometheus promtool query instant \
  'sum(rate(http_requests_total{status=~"5.."}[24h])) / sum(rate(http_requests_total[24h]))'

# Expected: 
# - Request rate > 0 (API is being used)
# - Error rate < 0.01 (< 1% errors)
```

#### Step 6: Document Issues
```bash
# Log any issues found
echo "$(date): Daily check - Status: OK/ISSUES" >> /var/log/weatherinsight/daily_checks.log

# If issues found, create incident in tracking system
# gh issue create --title "Daily Check: <Issue>" --label incident
```

**Time Required**: 15-20 minutes

---

### Continuous Monitoring (Throughout Day)

#### Monitor Alert Channels
- **Email**: ops@example.com (check for Alertmanager notifications)
- **Slack**: #weatherinsight-alerts channel
- **Grafana**: Dashboards should be displayed on ops monitors

#### Respond to Alerts
When an alert fires:
1. Acknowledge alert in Alertmanager UI
2. Check severity (Critical/Warning/Info)
3. Follow runbook for specific alert (see [INCIDENT_RESPONSE.md](INCIDENT_RESPONSE.md))
4. Document resolution
5. Close alert when resolved

---

## Weekly Tasks

### Monday: Pipeline Review (Every Monday, 10:00 AM)

#### Step 1: Review Previous Week's Runs
```bash
# Check all DAG runs from last 7 days
docker exec airflow-scheduler airflow dags list-runs \
  --start-date $(date -d '7 days ago' +%Y-%m-%d) \
  --end-date $(date +%Y-%m-%d) \
  -o table

# Review:
# - Success rate (should be > 95%)
# - Average duration (compare to baseline)
# - Any retries or failures
```

#### Step 2: Data Quality Report
```bash
# Run weekly data quality check
docker exec airflow-scheduler airflow dags trigger weatherinsight_data_quality

# Review results in Grafana Data Quality dashboard
# Or query database:
docker exec postgres psql -U weatherinsight -d weatherinsight << 'EOF'
SELECT 
  check_name,
  status,
  details,
  check_timestamp
FROM data_quality_results
WHERE check_timestamp > NOW() - INTERVAL '7 days'
ORDER BY check_timestamp DESC;
EOF

# Expected: All checks PASS
# If failures, investigate and remediate
```

#### Step 3: Resource Usage Trends
```bash
# Check resource trends in Grafana Infrastructure dashboard
# Look for:
# - Disk space trending (should not be > 85%)
# - Memory usage spikes
# - CPU saturation
# - Database connection pool usage

# Or check via CLI:
df -h /var/lib/docker  # Disk space
docker stats --no-stream  # Container resources
```

#### Step 4: API Usage Report
```bash
# Generate weekly API usage report
cat > /tmp/api_usage_query.sh << 'EOF'
#!/bin/bash
START_DATE=$(date -d '7 days ago' +%s)
END_DATE=$(date +%s)

echo "=== API Usage Report (Last 7 Days) ==="
echo ""

echo "Total Requests:"
curl -s "http://prometheus:9090/api/v1/query_range?query=sum(increase(http_requests_total[1d]))&start=$START_DATE&end=$END_DATE&step=86400" | jq '.data.result[0].values[][1]' | awk '{sum+=$1} END {print sum}'

echo ""
echo "Requests by Endpoint:"
curl -s "http://prometheus:9090/api/v1/query?query=sum(http_requests_total)%20by%20(endpoint)" | jq -r '.data.result[] | "\(.metric.endpoint): \(.value[1])"'

echo ""
echo "Top API Key Users:"
curl -s "http://prometheus:9090/api/v1/query?query=topk(5,%20sum(http_requests_total)%20by%20(api_key))" | jq -r '.data.result[] | "\(.metric.api_key): \(.value[1])"'

echo ""
echo "Average Latency (ms):"
curl -s "http://prometheus:9090/api/v1/query?query=avg(http_request_duration_seconds_sum%20/%20http_request_duration_seconds_count)" | jq -r '.data.result[0].value[1]'
EOF

chmod +x /tmp/api_usage_query.sh
/tmp/api_usage_query.sh

# Send report to stakeholders
# /tmp/api_usage_query.sh | mail -s "WeatherInsight Weekly Report" stakeholders@example.com
```

#### Step 5: Update Documentation
```bash
# Update operational notes
nano /opt/weatherinsight/docs/operational_notes.md

# Add any new issues, resolutions, or learnings from the week
```

**Time Required**: 30-45 minutes

---

### Friday: Backup Verification (Every Friday, 3:00 PM)

#### Step 1: Verify Automated Backups
```bash
# Check backup logs
tail -n 50 /var/log/weatherinsight/backup.log

# Verify backups exist
ls -lh /backups/db/ | tail -n 7  # Last 7 daily backups
ls -lh /backups/minio/ | tail -n 4  # Last 4 weekly backups

# Check backup sizes (should be consistent)
```

#### Step 2: Test Database Restore (Monthly)
```bash
# Restore latest backup to test database (first Friday of month)
LATEST_BACKUP=$(ls -t /backups/db/*.sql.gz | head -n 1)

# Create test database
docker exec postgres psql -U postgres -c "DROP DATABASE IF EXISTS weatherinsight_restore_test;"
docker exec postgres psql -U postgres -c "CREATE DATABASE weatherinsight_restore_test;"

# Restore backup
gunzip -c $LATEST_BACKUP | docker exec -i postgres psql -U weatherinsight -d weatherinsight_restore_test

# Verify restoration
docker exec postgres psql -U weatherinsight -d weatherinsight_restore_test -c \
  "SELECT COUNT(*) FROM quarterly_temperature_features;"

# Clean up
docker exec postgres psql -U postgres -c "DROP DATABASE weatherinsight_restore_test;"

# Document result
echo "$(date): Backup restore test: SUCCESS" >> /var/log/weatherinsight/backup_tests.log
```

#### Step 3: Offsite Backup Verification
```bash
# Verify backups are replicated to S3 (or other offsite storage)
aws s3 ls s3://weatherinsight-backups/$(date +%Y/%m/)/ | tail -n 10

# Check replication lag (should be < 24 hours)
```

**Time Required**: 15-20 minutes (45 minutes on first Friday with restore test)

---

## Monthly Tasks

### First Monday: Maintenance Window (First Monday, 2:00 AM)

#### Preparation (T-48 hours)
```bash
# Send notification to users
cat > /tmp/maintenance_notice.txt << 'EOF'
Subject: WeatherInsight Scheduled Maintenance - [Date] 2:00-4:00 AM UTC

Dear WeatherInsight Users,

Scheduled maintenance will be performed on [Date] from 2:00 AM to 4:00 AM UTC.

During this time:
- API will be unavailable
- No data updates will occur

Expected downtime: 2 hours
Maintenance activities: Security updates, database optimization, log cleanup

We apologize for any inconvenience.

Operations Team
EOF

# Send to user mailing list
cat /tmp/maintenance_notice.txt | mail -s "Scheduled Maintenance" users@example.com
```

#### Maintenance Execution
```bash
# 1. Enable maintenance mode
docker-compose stop api

# Put up maintenance page at load balancer
# nginx: Update upstream to point to maintenance.html

# 2. Apply security updates
sudo apt update
sudo apt upgrade -y

# 3. Database maintenance
docker exec postgres psql -U weatherinsight -d weatherinsight << 'EOF'
-- Vacuum all tables
VACUUM ANALYZE;

-- Reindex
REINDEX DATABASE weatherinsight;

-- Update statistics
ANALYZE;

-- Check for bloat
SELECT 
  schemaname, 
  tablename,
  pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
EOF

# 4. Clean old logs
find /var/log/weatherinsight -name "*.log" -mtime +90 -delete
docker system prune -f --volumes

# 5. Rotate logs
docker-compose logs --no-color > /var/log/weatherinsight/docker-compose-$(date +%Y%m).log
docker-compose logs --no-color --tail=100 > /dev/null  # Clear current logs

# 6. Update Docker images (if new versions available)
docker-compose pull
docker-compose up -d

# 7. Verify all services
sleep 60  # Wait for services to start
docker-compose ps
./scripts/health_check.sh

# 8. Re-enable API
docker-compose start api

# Revert nginx to normal upstream

# 9. Monitor for 1 hour
watch -n 60 'curl -s http://localhost:8000/health | jq .'

# 10. Send completion notice
echo "Maintenance completed successfully at $(date)" | \
  mail -s "Maintenance Complete" ops@example.com
```

**Time Required**: 2 hours

---

### Mid-Month: Capacity Planning (15th of Month, Anytime)

#### Step 1: Resource Utilization Review
```bash
# Generate capacity report
cat > /tmp/capacity_report.sh << 'EOF'
#!/bin/bash

echo "=== WeatherInsight Capacity Report ==="
echo "Generated: $(date)"
echo ""

echo "=== Disk Usage ==="
df -h /var/lib/docker
echo ""

echo "=== Database Size ==="
docker exec postgres psql -U weatherinsight -d weatherinsight << 'SQL'
SELECT 
  pg_size_pretty(pg_database_size('weatherinsight')) as total_size,
  (SELECT count(*) FROM quarterly_temperature_features) as temp_rows,
  (SELECT count(*) FROM quarterly_precipitation_features) as precip_rows,
  (SELECT count(*) FROM quarterly_wind_features) as wind_rows,
  (SELECT count(*) FROM quarterly_pressure_features) as pressure_rows,
  (SELECT count(*) FROM quarterly_humidity_features) as humidity_rows;
SQL
echo ""

echo "=== MinIO Usage ==="
docker exec minio mc du minio/weatherinsight-raw
docker exec minio mc du minio/weatherinsight-staging
echo ""

echo "=== Average Resource Usage (Last 30 Days) ==="
curl -s 'http://prometheus:9090/api/v1/query?query=avg_over_time(container_memory_usage_bytes[30d])' | \
  jq -r '.data.result[] | "\(.metric.name): \(.value[1] | tonumber / 1024 / 1024 / 1024) GB"'
echo ""

echo "=== Projected Growth (Next 6 Months) ==="
# Calculate growth rate
CURRENT_SIZE=$(docker exec postgres psql -U weatherinsight -d weatherinsight -t -c "SELECT pg_database_size('weatherinsight');")
echo "Current DB Size: $(($CURRENT_SIZE / 1024 / 1024 / 1024)) GB"
echo "Quarterly Growth: ~50 GB (estimate)"
echo "Projected Size (6mo): $(($CURRENT_SIZE / 1024 / 1024 / 1024 + 300)) GB"
echo ""

echo "=== Recommendations ==="
DISK_USAGE=$(df /var/lib/docker | tail -1 | awk '{print $5}' | sed 's/%//')
if [ $DISK_USAGE -gt 70 ]; then
  echo "⚠️  WARNING: Disk usage > 70%. Consider expanding storage."
else
  echo "✅ Disk usage within acceptable range."
fi
EOF

chmod +x /tmp/capacity_report.sh
/tmp/capacity_report.sh > /tmp/capacity_report.txt

# Review report
cat /tmp/capacity_report.txt

# Email to stakeholders
cat /tmp/capacity_report.txt | mail -s "WeatherInsight Capacity Report - $(date +%B)" stakeholders@example.com
```

#### Step 2: Plan Resource Adjustments
Based on capacity report:
- If disk > 70%: Plan storage expansion
- If memory > 80%: Consider scaling up server
- If CPU > 75%: Optimize queries or add resources
- If DB size growing rapidly: Consider data retention policy

#### Step 3: Update Cost Estimates
```bash
# Calculate current infrastructure costs
# Document in capacity report

# Update budget forecasts
# Coordinate with finance team
```

**Time Required**: 1-2 hours

---

## Quarterly Operations

### Quarter End: Pipeline Execution (Within 7 Days of Quarter End)

#### Before Quarter End (T-7 days)
```bash
# Verify pipeline is ready
docker exec airflow-scheduler airflow dags list

# Check quarterly_pipeline DAG configuration
docker exec airflow-scheduler airflow dags show weatherinsight_quarterly_pipeline

# Verify sufficient disk space (need ~100 GB for quarter)
df -h /var/lib/docker

# Pre-download station list for upcoming quarter
docker exec ingestion python -c "
from src.dwd_client import DWDClient
client = DWDClient()
for product in ['air_temperature', 'precipitation', 'wind', 'pressure', 'cloud_cover']:
    stations = client.get_station_list(product)
    print(f'{product}: {len(stations)} stations')
"
```

#### Quarter Start (Q+1 day, 00:00 UTC)
```bash
# Quarterly pipeline should trigger automatically via Airflow schedule
# Verify trigger in Airflow UI
open http://airflow.weatherinsight.example.com/dags/weatherinsight_quarterly_pipeline

# Or trigger manually if needed
docker exec airflow-scheduler airflow dags trigger weatherinsight_quarterly_pipeline \
  --conf "{\"execution_date\": \"$(date +%Y-%m-01)\"}"
```

#### During Pipeline Execution (Q+1 to Q+2)
```bash
# Monitor progress every 2 hours
watch -n 7200 "docker exec airflow-scheduler airflow dags list-runs \
  -d weatherinsight_quarterly_pipeline --state running"

# Check Grafana Pipeline Overview dashboard
open http://grafana.weatherinsight.example.com/d/pipeline_overview

# Expected stages and duration:
# 1. Ingestion: 4-6 hours (download all files for quarter)
# 2. Processing: 8-12 hours (parse and stage data)
# 3. Aggregation: 2-4 hours (compute features)
# 4. Quality Checks: 1-2 hours (validate data)
# Total: 15-24 hours

# If pipeline takes > 30 hours, investigate:
# - Slow DWD download speeds
# - Spark worker failures
# - Database connection issues
```

#### After Pipeline Completion (Q+2)
```bash
# Validate quarter data
docker exec postgres psql -U weatherinsight -d weatherinsight << 'EOF'
SELECT 
  'Temperature' as product,
  COUNT(*) as rows,
  COUNT(DISTINCT station_id) as stations
FROM quarterly_temperature_features
WHERE year = <YEAR> AND quarter = <QUARTER>
UNION ALL
SELECT 'Precipitation', COUNT(*), COUNT(DISTINCT station_id)
FROM quarterly_precipitation_features
WHERE year = <YEAR> AND quarter = <QUARTER>
UNION ALL
SELECT 'Wind', COUNT(*), COUNT(DISTINCT station_id)
FROM quarterly_wind_features
WHERE year = <YEAR> AND quarter = <QUARTER>
UNION ALL
SELECT 'Pressure', COUNT(*), COUNT(DISTINCT station_id)
FROM quarterly_pressure_features
WHERE year = <YEAR> AND quarter = <QUARTER>
UNION ALL
SELECT 'Humidity', COUNT(*), COUNT(DISTINCT station_id)
FROM quarterly_humidity_features
WHERE year = <YEAR> AND quarter = <QUARTER>;
EOF

# Expected: 200-300 stations, 200-500 rows per product

# Run comprehensive data quality checks
docker exec airflow-scheduler airflow dags trigger weatherinsight_data_quality

# Notify stakeholders of data availability
cat > /tmp/data_release.txt << 'EOF'
Subject: Q<QUARTER> <YEAR> Data Now Available

WeatherInsight users,

Quarterly weather features for Q<QUARTER> <YEAR> are now available via API.

Data includes:
- Temperature features (200+ stations)
- Precipitation features (200+ stations)
- Wind features (200+ stations)
- Pressure features (200+ stations)
- Humidity features (200+ stations)

Access via: https://api.weatherinsight.example.com/api/v1/features/

Operations Team
EOF

cat /tmp/data_release.txt | mail -s "Q<QUARTER> <YEAR> Data Release" users@example.com
```

**Time Required**: 30-40 hours (mostly automated, 2-3 hours of manual work)

---

## Monitoring & Alerts

### Grafana Dashboards

#### 1. Pipeline Overview
**URL**: http://grafana.weatherinsight.example.com/d/pipeline_overview

**Panels**:
- DAG Run Status (last 30 days)
- Task Duration Trends
- Task Failure Rate
- Ingestion Throughput
- Processing Throughput
- Aggregation Throughput

**Check**: Daily

#### 2. API Performance
**URL**: http://grafana.weatherinsight.example.com/d/api_performance

**Panels**:
- Request Rate (requests/sec)
- Latency Distribution (p50, p95, p99)
- Error Rate by Status Code
- Top Endpoints by Traffic
- API Key Usage
- Rate Limit Hits

**Check**: Multiple times daily

#### 3. Data Quality
**URL**: http://grafana.weatherinsight.example.com/d/data_quality

**Panels**:
- Completeness Checks
- Null Value Percentages
- Outlier Detection
- Schema Validation Results
- Metadata Consistency

**Check**: Weekly, after pipeline runs

#### 4. Infrastructure
**URL**: http://grafana.weatherinsight.example.com/d/infrastructure

**Panels**:
- CPU Usage by Container
- Memory Usage by Container
- Disk I/O
- Network Traffic
- Database Connections
- MinIO Storage Usage

**Check**: Daily

### Alert Rules

#### Critical Alerts (P0)
**Response Time**: 15 minutes

| Alert | Threshold | Action |
|-------|-----------|--------|
| Service Down | Any service unhealthy > 5min | Restart service, investigate |
| Database Down | PostgreSQL unavailable | Restore from backup if needed |
| API Error Rate High | > 5% for 5min | Check logs, rollback if recent deploy |
| Disk Space Critical | > 95% used | Emergency cleanup, expand storage |
| Pipeline Failure | DAG fails after retries | Investigate logs, re-run manually |

#### Warning Alerts (P1)
**Response Time**: 1 hour

| Alert | Threshold | Action |
|-------|-----------|--------|
| High Latency | p95 > 500ms for 15min | Check slow queries, optimize |
| Memory Pressure | > 85% for 15min | Restart containers, consider scaling |
| Data Quality Issue | Check fails | Investigate data, may need reprocessing |
| Backup Failed | Daily backup not completed | Retry backup, verify storage |

#### Info Alerts (P2)
**Response Time**: Next business day

| Alert | Threshold | Action |
|-------|-----------|--------|
| High Disk Usage | > 70% | Plan expansion |
| Unusual Traffic | 2x normal requests | Monitor for abuse |
| Slow Pipeline | Taking > 30 hours | Optimize, consider resources |

### Alert Channels

**Email**: ops@example.com
- All P0 and P1 alerts
- Daily summary of P2 alerts

**Slack**: #weatherinsight-alerts
- All alerts with context
- Resolution updates

**PagerDuty** (if configured):
- P0 alerts only
- 24/7 on-call rotation

---

## Troubleshooting

### Common Issues & Solutions

#### Issue 1: Service Won't Start

**Symptoms**: `docker-compose ps` shows service as "Restarting" or "Exited"

**Diagnosis**:
```bash
# Check service logs
docker-compose logs <service_name> --tail=100

# Common causes:
# - Port already in use
# - Insufficient memory
# - Configuration error
# - Missing environment variables
```

**Solution**:
```bash
# Check ports
sudo netstat -tulpn | grep <PORT>

# Check memory
free -h

# Verify configuration
docker-compose config

# Restart service
docker-compose restart <service_name>

# If still failing, recreate
docker-compose stop <service_name>
docker-compose rm -f <service_name>
docker-compose up -d <service_name>
```

#### Issue 2: Database Connection Failures

**Symptoms**: Services logging "connection refused" or "too many connections"

**Diagnosis**:
```bash
# Check active connections
docker exec postgres psql -U postgres -c \
  "SELECT count(*), state FROM pg_stat_activity GROUP BY state;"

# Check max connections
docker exec postgres psql -U postgres -c "SHOW max_connections;"
```

**Solution**:
```bash
# If too many connections, identify source
docker exec postgres psql -U postgres -c \
  "SELECT application_name, count(*) FROM pg_stat_activity GROUP BY application_name;"

# Kill idle connections
docker exec postgres psql -U postgres -c \
  "SELECT pg_terminate_backend(pid) FROM pg_stat_activity 
   WHERE state = 'idle' AND query_start < NOW() - INTERVAL '1 hour';"

# Or increase max_connections (requires restart)
docker exec postgres psql -U postgres -c \
  "ALTER SYSTEM SET max_connections = 200;"
docker-compose restart postgres
```

#### Issue 3: Slow API Responses

**Symptoms**: API latency > 500ms, timeouts

**Diagnosis**:
```bash
# Check slow queries
docker exec postgres psql -U weatherinsight -d weatherinsight -c \
  "SELECT query, mean_exec_time, calls FROM pg_stat_statements 
   ORDER BY mean_exec_time DESC LIMIT 10;"

# Check database load
docker exec postgres psql -U postgres -c \
  "SELECT * FROM pg_stat_activity WHERE state = 'active';"

# Check API container resources
docker stats api --no-stream
```

**Solution**:
```bash
# Add missing indexes (if identified)
# See SCHEMA_CHANGE_PROCEDURES.md

# Increase API replicas (if using Docker Swarm/K8s)
docker service scale api=3

# Clear query cache (PostgreSQL)
docker exec postgres psql -U postgres -c "SELECT pg_stat_reset();"

# Restart API
docker-compose restart api
```

#### Issue 4: Pipeline Stuck/Hanging

**Symptoms**: Airflow task running for abnormally long time

**Diagnosis**:
```bash
# Check task logs in Airflow UI
open http://airflow:8080/dags/weatherinsight_quarterly_pipeline

# Or CLI:
docker exec airflow-scheduler airflow tasks logs \
  weatherinsight_quarterly_pipeline <task_id> <execution_date>

# Check resource usage
docker stats --no-stream
```

**Solution**:
```bash
# Kill stuck task
docker exec airflow-scheduler airflow tasks clear \
  weatherinsight_quarterly_pipeline <task_id> <execution_date>

# Re-run task
docker exec airflow-scheduler airflow tasks run \
  weatherinsight_quarterly_pipeline <task_id> <execution_date>

# If Spark job stuck, restart Spark
docker-compose restart spark-master spark-worker
```

#### Issue 5: Data Quality Check Failures

**Symptoms**: Data quality DAG reports failures

**Diagnosis**:
```bash
# Review quality check results
docker exec postgres psql -U weatherinsight -d weatherinsight -c \
  "SELECT * FROM data_quality_results 
   WHERE status = 'FAIL' 
   ORDER BY check_timestamp DESC 
   LIMIT 10;"

# Check specific quarter
docker exec postgres psql -U weatherinsight -d weatherinsight << 'EOF'
SELECT year, quarter, COUNT(*) as row_count
FROM quarterly_temperature_features
GROUP BY year, quarter
ORDER BY year DESC, quarter DESC
LIMIT 10;
EOF
```

**Solution**:
```bash
# If completeness issue (missing data):
# Re-run pipeline for affected quarter
docker exec airflow-scheduler airflow dags trigger weatherinsight_backfill \
  --conf '{"start_year": <YEAR>, "end_year": <YEAR>, "quarters": [<Q>], "force_reprocess": true}'

# If data quality issue (bad values):
# Investigate processing code, may need hotfix

# If schema issue:
# See SCHEMA_CHANGE_PROCEDURES.md
```

For more troubleshooting, see [INCIDENT_RESPONSE.md](INCIDENT_RESPONSE.md).

---

## Emergency Procedures

### Total System Failure

**Symptoms**: All services down, unrecoverable errors

**Recovery**:
```bash
# 1. Stop all services
cd /opt/weatherinsight
docker-compose down

# 2. Check disk space
df -h

# If disk full, emergency cleanup:
docker system prune -a -f --volumes
find /var/log -name "*.log" -mtime +7 -delete

# 3. Restore from backup (if needed)
# See PRODUCTION_DEPLOYMENT.md "Disaster Recovery" section

# 4. Restart services
docker-compose up -d

# 5. Verify health
sleep 120  # Wait for startup
./scripts/health_check.sh

# 6. Notify stakeholders
```

### Data Corruption

**Symptoms**: Incorrect data, missing records, schema issues

**Recovery**:
```bash
# 1. Stop writes
docker-compose stop api aggregation processing

# 2. Assess damage
# Run data quality checks
# Identify affected quarters

# 3. Restore database
# See BACKFILL_PROCEDURES.md "Recovery from Database Corruption"

# 4. Resume operations
docker-compose start api aggregation processing
```

### Security Breach

**Symptoms**: Unauthorized access, suspicious activity, data leak

**Response**:
```bash
# 1. IMMEDIATE: Isolate system
sudo ufw deny in on eth0
docker-compose stop api

# 2. Assess breach
# Review logs: /var/log/weatherinsight/, docker-compose logs
# Check access logs: docker exec postgres psql -U postgres -c "SELECT * FROM pg_stat_activity;"

# 3. Contain damage
# Rotate all credentials
# Block compromised API keys
# Review and revoke database access

# 4. Notify
# - Security team
# - Management
# - Affected users (if data exposed)

# 5. Restore security
# Apply patches, update credentials, re-enable firewall

# 6. Post-mortem
# Document breach, implement preventions
```

---

## Contacts & Escalation

### Operations Team
- **On-Call Engineer**: oncall@example.com, +1-555-0100
- **Backup On-Call**: backup-oncall@example.com, +1-555-0101
- **Operations Lead**: ops-lead@example.com, +1-555-0102

### Development Team
- **Backend Lead**: backend-lead@example.com
- **Data Engineer**: data-engineer@example.com
- **DevOps Engineer**: devops@example.com

### Management
- **Engineering Manager**: eng-manager@example.com
- **Product Owner**: product-owner@example.com

### External
- **Cloud Provider Support**: https://support.aws.amazon.com (or GCP/Azure)
- **DWD Support**: https://www.dwd.de/EN/service/contact/contact_node.html

### Escalation Path
1. **P3 (Low)**: On-call engineer handles during business hours
2. **P2 (Medium)**: On-call engineer handles, notify ops lead if not resolved in 4 hours
3. **P1 (High)**: On-call engineer + ops lead, notify management if not resolved in 2 hours
4. **P0 (Critical)**: All hands on deck, immediate management notification

---

## Reference Materials

### Documentation
- [Production Deployment Guide](PRODUCTION_DEPLOYMENT.md)
- [Backfill Procedures](BACKFILL_PROCEDURES.md)
- [Schema Change Procedures](SCHEMA_CHANGE_PROCEDURES.md)
- [Incident Response Runbook](INCIDENT_RESPONSE.md)
- [Monitoring Guide](MONITORING_GUIDE.md)
- [Testing Strategy](TESTING_STRATEGY.md)
- [API Documentation](../services/api/README.md)

### External Resources
- [DWD Open Data Documentation](https://opendata.dwd.de/climate_environment/CDC/Readme_intro_CDC_ftp.pdf)
- [Airflow Documentation](https://airflow.apache.org/docs/)
- [PostgreSQL Performance Tuning](https://wiki.postgresql.org/wiki/Performance_Optimization)
- [Spark Monitoring Guide](https://spark.apache.org/docs/latest/monitoring.html)

### Useful Commands Cheat Sheet
```bash
# Service management
docker-compose ps                          # List all services
docker-compose logs -f <service>           # Tail service logs
docker-compose restart <service>           # Restart service
docker-compose up -d --scale api=3         # Scale service

# Database queries
docker exec postgres psql -U weatherinsight -d weatherinsight -c "<SQL>"

# Airflow operations
docker exec airflow-scheduler airflow dags list
docker exec airflow-scheduler airflow dags trigger <dag_id>
docker exec airflow-scheduler airflow tasks clear <dag_id> <task_id> <date>

# Monitoring
curl http://localhost:9090/api/v1/alerts   # Prometheus alerts
docker stats --no-stream                   # Container resources
df -h /var/lib/docker                      # Disk usage

# Logs
docker-compose logs --since 1h             # Last hour of logs
tail -f /var/log/weatherinsight/*.log      # Application logs
journalctl -u docker -f                    # Docker system logs
```

---

## Version History
- v1.0.0 (2026-02-08): Initial operations handover guide
