# WeatherInsight Monitoring & Observability Guide

## Overview

Comprehensive monitoring and observability setup for the WeatherInsight data pipeline using Prometheus, Grafana, and Alertmanager.

## Architecture

```
┌─────────────┐    metrics    ┌────────────┐    alerts    ┌──────────────┐
│  Services   │──────────────>│ Prometheus │─────────────>│ Alertmanager │
│  - API      │               │            │              │              │
│  - MinIO    │               └────────────┘              └──────────────┘
│  - Postgres │                     │                            │
│  - Airflow  │                     │ queries                    │ notifications
└─────────────┘                     ▼                            ▼
                               ┌────────────┐              ┌──────────┐
                               │  Grafana   │              │  Email   │
                               │ Dashboards │              │  Slack   │
                               └────────────┘              └──────────┘
```

## Metrics Collection

### Services Instrumented

#### 1. **WeatherInsight API** (port 8000/metrics)
**Metrics Exposed**:
- `weatherinsight_api_requests_total{method, endpoint, status}` - Request counter
- `weatherinsight_api_request_duration_seconds{method, endpoint}` - Request latency histogram
- `weatherinsight_api_db_query_duration_seconds{operation}` - DB query latency histogram

**Implementation**: `services/api/app/main.py`
```python
from prometheus_client import Counter, Histogram

REQUEST_COUNT = Counter(
    "weatherinsight_api_requests_total",
    "Total API requests",
    ["method", "endpoint", "status"]
)
```

#### 2. **MinIO** (port 9000/minio/v2/metrics/cluster)
**Key Metrics**:
- `minio_bucket_usage_total_bytes{bucket}` - Bucket sizes
- `minio_bucket_usage_object_total{bucket}` - Object counts
- `minio_s3_requests_total{api}` - S3 API request rate
- `minio_s3_requests_errors_total{api}` - S3 API errors
- `minio_cluster_disk_total_bytes` / `minio_cluster_disk_free_bytes` - Disk usage

#### 3. **PostgreSQL** (via postgres-exporter on port 9187)
**Key Metrics**:
- `pg_stat_database_numbackends{datname}` - Active connections
- `pg_database_size_bytes{datname}` - Database size
- `pg_stat_database_xact_commit{datname}` - Transaction rate
- `pg_stat_statements` - Query performance (if pg_stat_statements enabled)

#### 4. **Airflow** (via statsd-exporter on port 9102)
**Key Metrics**:
- `airflow_dagrun_success_total{dag_id}` - DAG successes
- `airflow_dagrun_failed_total{dag_id}` - DAG failures
- `airflow_dagrun_duration_seconds{dag_id}` - DAG duration
- `airflow_task_duration_seconds{dag_id, task_id}` - Task duration
- `airflow_executor_open_slots` - Available executor slots
- `airflow_scheduler_heartbeat` - Scheduler health

### Prometheus Configuration

**File**: `infra/prometheus/prometheus.yml`

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'weatherinsight-api'
    static_configs:
      - targets: ['api:8000']
    metrics_path: /metrics
  
  - job_name: 'minio'
    static_configs:
      - targets: ['minio:9000']
    metrics_path: /minio/v2/metrics/cluster
  
  - job_name: 'postgres'
    static_configs:
      - targets: ['postgres-exporter:9187']
  
  - job_name: 'airflow'
    static_configs:
      - targets: ['airflow-statsd-exporter:9102']
```

## Grafana Dashboards

### Access
- **URL**: http://localhost:3002
- **Credentials**: admin/admin123
- **Datasource**: Prometheus (auto-configured)

### Available Dashboards

#### 1. Pipeline Overview (`pipeline_overview.json`)
**Panels** (12):
- Pipeline Status Overview - Service health status
- Quarterly Pipeline Execution Rate - Request rate over time
- Pipeline Task Duration Distribution - Heatmap of task durations
- Ingestion/Processing/Aggregation Tasks - Average durations
- Task Failure Rate - Error tracking by task
- Success Rate by Pipeline Stage - Bar gauge of success %
- Pipeline Execution Timeline - P50/P95/P99 latencies
- Active Pipeline Runs - Current running pipelines
- Recent Pipeline Completions - Last hour successes
- Pipeline Resource Utilization - CPU/memory usage

**Use Cases**:
- Monitor quarterly pipeline execution
- Identify bottlenecks in pipeline stages
- Track failure rates and success rates
- Resource utilization trends

#### 2. API Performance (`api_performance.json`)
**Panels** (10):
- API Request Rate - Requests/sec by endpoint
- API Latency (P50, P95, P99) - Latency percentiles
- Error Rate by Status Code - 4xx and 5xx errors
- Success Rate - Overall API success gauge
- Current Request Rate - Real-time req/s
- Active Connections - API service status
- Database Query Duration - DB query latencies
- Request Distribution by Endpoint - Pie chart
- Top 10 Slowest Endpoints - Table view
- Request Rate Heatmap - Distribution over time

**Alerts**:
- High API Latency (P99 > 500ms)

**Use Cases**:
- Monitor API response times
- Identify slow endpoints
- Track error rates and patterns
- Database performance correlation

#### 3. Data Quality (`data_quality.json`)
**Panels** (8):
- Feature Table Row Counts - Trend of successful queries
- Temperature/Precipitation/Wind/Pressure Features - Individual counts
- Data Freshness - Time since last update
- Station Coverage Trend - Unique stations over time
- Data Quality Score - Overall quality gauge
- Quality Check Results Timeline - Pass/fail rates

**Alerts**:
- Stale Data (>24h since last update)

**Use Cases**:
- Monitor data completeness
- Track feature table growth
- Identify data quality issues
- Validate station coverage

#### 4. Infrastructure (`infrastructure.json`)
**Panels** (14):
- Service Health Status - All services up/down
- MinIO Bucket Sizes - Storage utilization
- MinIO Object Counts - Object growth
- MinIO Request Rate - S3 API usage
- MinIO Error Rate - S3 API failures
- PostgreSQL Active Connections - DB connection pool
- PostgreSQL Query Duration (P95) - DB performance
- PostgreSQL Database Size - Storage growth
- PostgreSQL Transaction Rate - Transaction throughput
- Container CPU Usage - Resource utilization
- Container Memory Usage - Memory consumption
- Network I/O - Data transfer rates
- Disk Usage - MinIO disk utilization gauge
- System Load Average - Host system load

**Alerts**:
- High CPU Usage (>80%)
- Disk Space Running Low (>85%)

**Use Cases**:
- Monitor service health
- Track resource utilization
- Identify capacity issues
- Plan infrastructure scaling

### Query Examples

#### API Request Rate
```promql
sum(rate(weatherinsight_api_requests_total[5m])) by (endpoint)
```

#### P95 Latency by Endpoint
```promql
histogram_quantile(0.95, 
  sum(rate(weatherinsight_api_request_duration_seconds_bucket[5m])) by (le, endpoint)
)
```

#### Error Rate
```promql
(
  sum(rate(weatherinsight_api_requests_total{status=~"5.."}[5m]))
  /
  sum(rate(weatherinsight_api_requests_total[5m]))
) * 100
```

#### MinIO Disk Usage Percentage
```promql
(
  (sum(minio_cluster_disk_total_bytes) - sum(minio_cluster_disk_free_bytes))
  / sum(minio_cluster_disk_total_bytes)
) * 100
```

## Alerting

### Alert Rules

**File**: `infra/prometheus/alerts.yml`

#### Critical Alerts

1. **APIDown** - API service unreachable for >1 minute
2. **APIHighErrorRate** - Error rate >5% for 5 minutes
3. **DatabaseConnectionPoolExhausted** - High query volume
4. **MinIODown** - MinIO unreachable for >1 minute
5. **DiskSpaceRunningLow** - Disk usage >85%

#### Warning Alerts

1. **APIHighLatency** - P95 latency >2s for 10 minutes
2. **DatabaseSlowQueries** - P95 query time >1s
3. **DataQualityCheckFailed** - >10% feature queries failing
4. **StaleData** - No successful requests in 24 hours
5. **HighCPUUsage** - CPU >80% for 10 minutes
6. **HighMemoryUsage** - Memory >1GB for 10 minutes
7. **MinIOHighErrorRate** - S3 error rate >5%
8. **PipelineNotRunning** - No requests in 6 hours

#### Info Alerts

1. **LowStationCoverage** - Fewer station queries than expected
2. **APILowRequestRate** - Unusually low traffic

### Alertmanager Configuration

**File**: `infra/prometheus/alertmanager.yml`

**Routing**:
- **Critical** alerts → immediate email (1h repeat)
- **Warning** alerts → batched email (4h repeat)
- **Info** alerts → daily digest (24h repeat)

**Inhibition Rules**:
- Suppress warnings when critical alerts firing
- Suppress API errors when API is down
- Suppress database alerts when API is down

**Receivers**:
```yaml
receivers:
  - name: 'weatherinsight-critical'
    email_configs:
      - to: 'oncall@weatherinsight.local'
        subject: '🚨 [CRITICAL] {{ .CommonLabels.alertname }}'
    # Optional: Slack/PagerDuty integration
```

### Alert Response Procedures

#### APIDown
1. Check service status: `docker compose ps api`
2. View logs: `docker compose logs api --tail=100`
3. Check database connectivity: `docker exec postgres pg_isready`
4. Restart if needed: `docker compose restart api`
5. Verify recovery: `curl http://localhost:8000/health`

#### HighAPILatency
1. Check Grafana API Performance dashboard
2. Identify slow endpoints in "Top 10 Slowest Endpoints" panel
3. Check database query performance:
   ```sql
   SELECT query, mean_exec_time FROM pg_stat_statements 
   ORDER BY mean_exec_time DESC LIMIT 10;
   ```
4. Consider scaling API or optimizing queries
5. Check for concurrent load spikes

#### DataQualityCheckFailed
1. Check Grafana Data Quality dashboard
2. View quality check DAG logs in Airflow
3. Check feature table row counts:
   ```sql
   SELECT 'temperature' as product, COUNT(*) FROM quarterly_temperature_features
   UNION ALL
   SELECT 'precipitation', COUNT(*) FROM quarterly_precipitation_features;
   ```
4. Investigate data pipeline failures
5. Re-run quality check DAG if transient

#### DiskSpaceRunningLow
1. Check MinIO bucket sizes in Grafana
2. List large objects:
   ```bash
   docker exec minio mc ls --recursive minio/weatherinsight-raw | sort -k 4 -h
   ```
3. Archive old data to backup bucket
4. Consider adding storage capacity
5. Implement data retention policy

## Metrics Endpoint Testing

### Test API Metrics
```bash
# Check metrics endpoint
curl http://localhost:8000/metrics

# Verify specific metric
curl http://localhost:8000/metrics | grep weatherinsight_api_requests_total

# Test metrics after making requests
curl http://localhost:8000/api/v1/stations?limit=10
curl http://localhost:8000/metrics | grep requests_total
```

### Test Prometheus Scraping
```bash
# Check Prometheus targets
curl http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | {job: .labels.job, health: .health}'

# Query metric
curl 'http://localhost:9090/api/v1/query?query=up'

# Query rate
curl 'http://localhost:9090/api/v1/query?query=rate(weatherinsight_api_requests_total[5m])'
```

### Test Alertmanager
```bash
# Check active alerts
curl http://localhost:9093/api/v1/alerts | jq '.data[] | {alertname: .labels.alertname, state: .status.state}'

# Silence an alert
curl -X POST http://localhost:9093/api/v1/silences -d '{
  "matchers": [{"name":"alertname","value":"APIHighLatency","isRegex":false}],
  "startsAt":"2026-02-08T00:00:00Z",
  "endsAt":"2026-02-08T12:00:00Z",
  "comment":"Planned maintenance"
}'
```

## Troubleshooting

### Prometheus Not Scraping
1. Check Prometheus configuration: `cat infra/prometheus/prometheus.yml`
2. Validate syntax: `docker exec prometheus promtool check config /etc/prometheus/prometheus.yml`
3. View Prometheus logs: `docker compose logs prometheus`
4. Check target health: http://localhost:9090/targets
5. Verify network connectivity: `docker exec prometheus wget -O- api:8000/metrics`

### Grafana Dashboard Not Loading
1. Check Grafana logs: `docker compose logs grafana`
2. Verify datasource: http://localhost:3002/datasources
3. Test Prometheus query in Explore tab
4. Reload dashboard provisioning: Restart Grafana service
5. Check dashboard JSON for syntax errors

### Missing Metrics
1. Verify service is exposing metrics endpoint
2. Check Prometheus scrape config includes target
3. Wait for next scrape interval (15s default)
4. Query Prometheus directly: http://localhost:9090/graph
5. Check for metric naming mismatches

### Alerts Not Firing
1. Check alert rules: `docker exec prometheus promtool check rules /etc/prometheus/alerts.yml`
2. View alert status: http://localhost:9090/alerts
3. Check evaluation interval (15s default)
4. Verify alert expression returns data
5. Check Alertmanager configuration

## Best Practices

### 1. Metric Naming
- Use consistent prefixes: `weatherinsight_*`
- Include units in names: `_seconds`, `_bytes`, `_total`
- Use labels for dimensions: `{endpoint, method, status}`

### 2. Dashboard Design
- Group related metrics together
- Use appropriate visualization types
- Set meaningful thresholds and colors
- Add descriptions and documentation links
- Enable drill-down capabilities

### 3. Alert Design
- Define clear thresholds based on SLOs
- Avoid alert fatigue with appropriate delays (`for: 5m`)
- Use inhibition rules to prevent alert storms
- Include actionable information in annotations
- Test alerts with realistic scenarios

### 4. Retention
- **Prometheus**: 15 days (default)
- **Grafana**: Dashboard history enabled
- **Logs**: 7 days via Docker logging
- **Metrics**: Consider long-term storage (Thanos/Cortex) for >15 days

## Related Documentation

- [Testing Strategy](./TESTING_STRATEGY.md) - Test coverage and execution
- [Incident Response](./INCIDENT_RESPONSE.md) - Response procedures
- [Runbook](./runbook.md) - Operational procedures
- [API Documentation](../services/api/README.md) - API endpoints
