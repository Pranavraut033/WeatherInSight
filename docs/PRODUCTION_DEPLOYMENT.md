# WeatherInsight Production Deployment Guide

## Overview
This guide covers deploying WeatherInsight to production, including infrastructure provisioning, configuration, security hardening, and operational procedures.

## Table of Contents
1. [Prerequisites](#prerequisites)
2. [Infrastructure Setup](#infrastructure-setup)
3. [Service Deployment](#service-deployment)
4. [Security Configuration](#security-configuration)
5. [Initial Data Load](#initial-data-load)
6. [Validation & Testing](#validation--testing)
7. [Go-Live Checklist](#go-live-checklist)
8. [Rollback Procedures](#rollback-procedures)

---

## Prerequisites

### Required Resources
- **Compute**: 
  - Airflow: 4 vCPU, 16 GB RAM (scheduler + workers)
  - Spark: 8 vCPU, 32 GB RAM (master + workers)
  - API: 2 vCPU, 8 GB RAM
  - PostgreSQL: 4 vCPU, 16 GB RAM, 500 GB SSD
  - MinIO: 2 vCPU, 8 GB RAM, 2 TB storage
  - Monitoring: 2 vCPU, 8 GB RAM

- **Network**:
  - Private VPC with subnets
  - Load balancer for API (SSL/TLS)
  - Bastion host for secure access

- **DNS & Certificates**:
  - Domain name for API endpoint
  - SSL/TLS certificates (Let's Encrypt or commercial)

### Required Accounts & Access
- Cloud provider account (AWS/GCP/Azure)
- DWD OpenData access (public, no credentials required)
- SMTP credentials for email alerts
- Slack webhook for notifications (optional)
- Docker registry access (DockerHub, ECR, GCR, or ACR)

### Tools
```bash
# Install required tools
brew install docker docker-compose kubectl helm terraform
brew install postgresql awscli

# Verify installations
docker --version
docker-compose --version
kubectl version --client
helm version
terraform --version
```

---

## Infrastructure Setup

### Option 1: Docker Compose (Single-Node Production)

Suitable for small-to-medium deployments (up to 500 stations).

#### 1.1 Server Provisioning
```bash
# Provision VM (example: AWS EC2)
# - Instance type: r5.4xlarge (16 vCPU, 128 GB RAM)
# - Storage: 2 TB EBS SSD
# - OS: Ubuntu 22.04 LTS
# - Security groups: Allow 443 (HTTPS), 22 (SSH)

# SSH to server
ssh -i prod-key.pem ubuntu@weatherinsight.example.com

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/download/v2.20.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Verify
docker --version
docker-compose --version
```

#### 1.2 Clone Repository
```bash
cd /opt
sudo git clone https://github.com/yourorg/weatherinsight.git
cd weatherinsight
```

#### 1.3 Configure Environment
```bash
# Copy and customize environment variables
cp .env.example .env

# Edit production configuration
nano .env
```

**Production `.env` Configuration:**
```bash
# === Environment ===
ENVIRONMENT=production
LOG_LEVEL=INFO

# === PostgreSQL ===
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=weatherinsight
POSTGRES_USER=weatherinsight
POSTGRES_PASSWORD=<STRONG_PASSWORD_HERE>  # Generate with: openssl rand -base64 32

# === MinIO ===
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=<STRONG_PASSWORD_HERE>
MINIO_ENDPOINT=http://minio:9000
MINIO_ACCESS_KEY=<ACCESS_KEY>
MINIO_SECRET_KEY=<SECRET_KEY>

# === Airflow ===
AIRFLOW_ADMIN_USERNAME=admin
AIRFLOW_ADMIN_PASSWORD=<STRONG_PASSWORD_HERE>
AIRFLOW_ADMIN_EMAIL=ops@example.com
AIRFLOW_FERNET_KEY=<GENERATE_WITH_python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())">
AIRFLOW_SECRET_KEY=<GENERATE_WITH_openssl rand -hex 32>

# === API ===
API_HOST=0.0.0.0
API_PORT=8000
API_KEY_HEADER=X-API-Key
API_KEY_SECRET=<GENERATE_WITH_openssl rand -hex 32>
RATE_LIMIT=100/minute

# === Monitoring ===
GRAFANA_ADMIN_PASSWORD=<STRONG_PASSWORD_HERE>
PROMETHEUS_RETENTION_DAYS=90

# === Email Alerts ===
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=alerts@example.com
SMTP_PASSWORD=<APP_PASSWORD>
ALERT_EMAIL_FROM=weatherinsight@example.com
ALERT_EMAIL_TO=ops@example.com

# === Slack Alerts (Optional) ===
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

#### 1.4 Deploy Services
```bash
# Pull latest images
docker-compose pull

# Start all services
docker-compose up -d

# Verify all services are running
docker-compose ps

# Check logs
docker-compose logs -f
```

### Option 2: Kubernetes (Multi-Node Production)

Suitable for large-scale deployments (500+ stations, high availability required).

#### 2.1 Kubernetes Cluster Setup
```bash
# Create EKS cluster (example)
eksctl create cluster \
  --name weatherinsight-prod \
  --region us-east-1 \
  --nodegroup-name standard-workers \
  --node-type r5.2xlarge \
  --nodes 5 \
  --nodes-min 3 \
  --nodes-max 10 \
  --managed

# Configure kubectl
aws eks update-kubeconfig --region us-east-1 --name weatherinsight-prod
```

#### 2.2 Install Helm Charts
```bash
# Add Helm repositories
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo add apache-airflow https://airflow.apache.org
helm repo update

# Create namespace
kubectl create namespace weatherinsight

# Install PostgreSQL
helm install postgres bitnami/postgresql \
  --namespace weatherinsight \
  --set auth.username=weatherinsight \
  --set auth.password=<PASSWORD> \
  --set auth.database=weatherinsight \
  --set primary.persistence.size=500Gi

# Install MinIO
helm install minio bitnami/minio \
  --namespace weatherinsight \
  --set auth.rootUser=minioadmin \
  --set auth.rootPassword=<PASSWORD> \
  --set persistence.size=2Ti

# Install Airflow
helm install airflow apache-airflow/airflow \
  --namespace weatherinsight \
  --values k8s/airflow-values.yaml

# Deploy custom services (API, processing, aggregation)
kubectl apply -f k8s/api-deployment.yaml
kubectl apply -f k8s/processing-deployment.yaml
kubectl apply -f k8s/aggregation-deployment.yaml
```

---

## Service Deployment

### Build & Push Docker Images

#### 3.1 Build All Images
```bash
# Build ingestion service
cd services/ingestion
docker build -t yourregistry/weatherinsight-ingestion:v1.0.0 .
docker push yourregistry/weatherinsight-ingestion:v1.0.0

# Build metadata service
cd ../metadata
docker build -t yourregistry/weatherinsight-metadata:v1.0.0 .
docker push yourregistry/weatherinsight-metadata:v1.0.0

# Build processing service
cd ../processing
docker build -t yourregistry/weatherinsight-processing:v1.0.0 .
docker push yourregistry/weatherinsight-processing:v1.0.0

# Build aggregation service
cd ../aggregation
docker build -t yourregistry/weatherinsight-aggregation:v1.0.0 .
docker push yourregistry/weatherinsight-aggregation:v1.0.0

# Build API service
cd ../api
docker build -t yourregistry/weatherinsight-api:v1.0.0 .
docker push yourregistry/weatherinsight-api:v1.0.0
```

#### 3.2 Update docker-compose.yml
```yaml
# Update image tags in docker-compose.yml
services:
  api:
    image: yourregistry/weatherinsight-api:v1.0.0
  # ... other services
```

### Database Initialization

#### 4.1 Run Schema Migrations
```bash
# Connect to PostgreSQL
docker exec -it postgres psql -U weatherinsight -d weatherinsight

# Verify schema
\dt

# Expected tables:
# - schema_registry
# - dataset_versions
# - station_metadata
# - quarterly_temperature_features
# - quarterly_precipitation_features
# - quarterly_wind_features
# - quarterly_pressure_features
# - quarterly_humidity_features
```

#### 4.2 Seed Station Metadata
```bash
# Download station list from DWD
docker exec -it ingestion python -c "
from src.dwd_client import DWDClient
client = DWDClient()
stations = client.get_station_list('air_temperature')
print(f'Found {len(stations)} stations')
"

# Metadata will be populated during first ingestion
```

### Airflow Configuration

#### 5.1 Set Up Connections
```bash
# Access Airflow UI
open http://weatherinsight.example.com:8080

# Admin > Connections > Add Connection
# Connection ID: weatherinsight_postgres
# Connection Type: Postgres
# Host: postgres
# Schema: weatherinsight
# Login: weatherinsight
# Password: <PASSWORD>
# Port: 5432
```

#### 5.2 Configure Variables
```bash
# Admin > Variables > Add Variable
# Key: dwd_base_url
# Value: https://opendata.dwd.de/climate_environment/CDC/observations_germany/climate/hourly/

# Key: minio_endpoint
# Value: http://minio:9000

# Key: dataset_version
# Value: v1.0.0
```

#### 5.3 Enable DAGs
```bash
# Enable quarterly pipeline
airflow dags unpause weatherinsight_quarterly_pipeline

# Enable data quality checks
airflow dags unpause weatherinsight_data_quality

# Verify DAGs are enabled
airflow dags list
```

---

## Security Configuration

### 6.1 API Authentication
```bash
# Generate API keys for clients
python3 << 'EOF'
import secrets
for i in range(5):
    print(f"Client {i+1}: {secrets.token_urlsafe(32)}")
EOF

# Add to API key whitelist (in .env or database)
```

### 6.2 Network Security
```bash
# Configure firewall (example: ufw)
sudo ufw allow 443/tcp   # HTTPS only
sudo ufw allow 22/tcp    # SSH (restrict to bastion host)
sudo ufw deny 8080/tcp   # Block direct Airflow access
sudo ufw deny 9000/tcp   # Block direct MinIO access
sudo ufw deny 5432/tcp   # Block direct PostgreSQL access
sudo ufw enable

# Set up reverse proxy (nginx)
sudo apt install nginx
sudo nano /etc/nginx/sites-available/weatherinsight
```

**Nginx Configuration:**
```nginx
upstream api_backend {
    server localhost:8000;
}

server {
    listen 443 ssl http2;
    server_name api.weatherinsight.example.com;

    ssl_certificate /etc/letsencrypt/live/weatherinsight.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/weatherinsight.example.com/privkey.pem;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;

    # Rate limiting
    limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;
    limit_req zone=api_limit burst=20 nodelay;

    location / {
        proxy_pass http://api_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### 6.3 SSL/TLS Setup
```bash
# Install certbot
sudo apt install certbot python3-certbot-nginx

# Obtain certificate
sudo certbot --nginx -d api.weatherinsight.example.com

# Auto-renewal
sudo certbot renew --dry-run
```

### 6.4 Database Security
```bash
# Restrict PostgreSQL connections
docker exec -it postgres nano /var/lib/postgresql/data/pg_hba.conf

# Allow only local network
# host    weatherinsight    weatherinsight    10.0.0.0/8    md5

# Reload configuration
docker exec -it postgres psql -U postgres -c "SELECT pg_reload_conf();"
```

---

## Initial Data Load

### 7.1 Historical Backfill Strategy
```bash
# Plan backfill based on requirements
# Example: Load 5 years of historical data (2019-2023)

# Start with a small test quarter
airflow dags trigger weatherinsight_backfill \
  --conf '{
    "start_year": 2023,
    "end_year": 2023,
    "quarters": [1],
    "products": ["air_temperature"]
  }'

# Monitor progress in Airflow UI
# Expected duration: 2-4 hours for 1 quarter, 1 product

# Verify data
docker exec postgres psql -U weatherinsight -d weatherinsight \
  -c "SELECT COUNT(*), MIN(year), MAX(year) FROM quarterly_temperature_features;"
```

### 7.2 Full Historical Load
```bash
# Backfill all products for all quarters (2019-2023)
# Total time: ~80-120 hours (parallelize across years)

for year in {2019..2023}; do
  airflow dags trigger weatherinsight_backfill \
    --conf "{
      \"start_year\": $year,
      \"end_year\": $year,
      \"quarters\": [1, 2, 3, 4],
      \"products\": [\"air_temperature\", \"precipitation\", \"wind\", \"pressure\", \"cloud_cover\"]
    }"
  echo "Triggered backfill for $year"
  sleep 3600  # Wait 1 hour between years to avoid overload
done
```

### 7.3 Data Validation
```bash
# Run comprehensive data quality checks
airflow dags trigger weatherinsight_data_quality

# Verify feature counts
docker exec postgres psql -U weatherinsight -d weatherinsight << 'EOF'
SELECT 
    'Temperature' as product,
    COUNT(*) as total_rows,
    COUNT(DISTINCT station_id) as stations,
    MIN(year) as min_year,
    MAX(year) as max_year
FROM quarterly_temperature_features
UNION ALL
SELECT 'Precipitation', COUNT(*), COUNT(DISTINCT station_id), MIN(year), MAX(year)
FROM quarterly_precipitation_features
UNION ALL
SELECT 'Wind', COUNT(*), COUNT(DISTINCT station_id), MIN(year), MAX(year)
FROM quarterly_wind_features
UNION ALL
SELECT 'Pressure', COUNT(*), COUNT(DISTINCT station_id), MIN(year), MAX(year)
FROM quarterly_pressure_features
UNION ALL
SELECT 'Humidity', COUNT(*), COUNT(DISTINCT station_id), MIN(year), MAX(year)
FROM quarterly_humidity_features;
EOF
```

---

## Validation & Testing

### 8.1 Service Health Checks
```bash
# Check all services
./scripts/health_check.sh

# Or manually:
curl https://api.weatherinsight.example.com/health
curl http://localhost:3002/api/health  # Grafana
curl http://localhost:9090/-/healthy   # Prometheus
```

### 8.2 API Integration Tests
```bash
# Run E2E tests against production
cd tests/e2e
export API_BASE_URL=https://api.weatherinsight.example.com
export API_KEY=<PRODUCTION_API_KEY>
pytest test_api_integration.py -v
```

### 8.3 Performance Testing
```bash
# Install Apache Bench
sudo apt install apache2-utils

# Load test API endpoint
ab -n 1000 -c 10 -H "X-API-Key: <KEY>" \
  https://api.weatherinsight.example.com/api/v1/features/temperature?year=2023&quarter=1

# Expected results:
# - Requests per second: >50
# - Mean response time: <200ms
# - 99th percentile: <500ms
```

### 8.4 Data Quality Validation
```bash
# Run data quality checks
docker exec postgres psql -U weatherinsight -d weatherinsight -f /opt/scripts/validate_data.sql

# Check for anomalies
python3 << 'EOF'
import psycopg2
conn = psycopg2.connect(
    host="postgres",
    database="weatherinsight",
    user="weatherinsight",
    password="<PASSWORD>"
)
cur = conn.cursor()

# Check for missing quarters
cur.execute("""
SELECT year, quarter 
FROM generate_series(2019, 2023) AS year
CROSS JOIN generate_series(1, 4) AS quarter
EXCEPT
SELECT DISTINCT year, quarter FROM quarterly_temperature_features
ORDER BY year, quarter;
""")
missing = cur.fetchall()
if missing:
    print(f"Warning: Missing quarters: {missing}")
else:
    print("All quarters present")

conn.close()
EOF
```

---

## Go-Live Checklist

### Pre-Launch (T-7 Days)
- [ ] All services deployed and running
- [ ] Historical backfill complete (2019-2023)
- [ ] Data quality checks passing (>95%)
- [ ] API performance meets SLAs (<200ms p95)
- [ ] SSL/TLS certificates valid
- [ ] Monitoring dashboards configured
- [ ] Alert rules tested and verified
- [ ] Backup procedures tested
- [ ] Disaster recovery plan documented
- [ ] Team training completed

### Launch Day (T-0)
- [ ] DNS cutover to production IP
- [ ] Enable real-time monitoring
- [ ] Send go-live notification to stakeholders
- [ ] Monitor error rates and performance
- [ ] Verify scheduled quarterly pipeline for next quarter
- [ ] Document any issues in incident log

### Post-Launch (T+7 Days)
- [ ] Review first week's metrics
- [ ] Adjust alerts based on actual patterns
- [ ] Collect user feedback
- [ ] Optimize slow queries
- [ ] Plan capacity scaling if needed

---

## Rollback Procedures

### Emergency Rollback
If critical issues arise, follow these steps:

#### 1. Stop New Requests
```bash
# Block traffic at load balancer
sudo nginx -s stop

# Or update DNS to point to maintenance page
```

#### 2. Restore Previous Version
```bash
# Rollback to previous Docker images
docker-compose down
git checkout <PREVIOUS_TAG>
docker-compose up -d
```

#### 3. Restore Database (if needed)
```bash
# Restore from most recent backup
docker exec postgres pg_restore \
  -U weatherinsight \
  -d weatherinsight \
  /backups/weatherinsight_YYYYMMDD.dump
```

#### 4. Verify Rollback
```bash
# Check all services
docker-compose ps

# Test API
curl https://api.weatherinsight.example.com/health

# Verify data
docker exec postgres psql -U weatherinsight -d weatherinsight \
  -c "SELECT COUNT(*) FROM quarterly_temperature_features;"
```

#### 5. Resume Traffic
```bash
# Re-enable load balancer
sudo nginx
```

#### 6. Post-Mortem
- Document what went wrong
- Identify root cause
- Plan fixes for next deployment
- Update runbooks

---

## Maintenance Windows

### Scheduled Maintenance
- **Frequency**: Monthly (first Saturday of each month)
- **Duration**: 2 hours (02:00-04:00 UTC)
- **Activities**:
  - Security patches
  - Database vacuum/reindex
  - Log rotation
  - Backup verification

### Maintenance Procedure
```bash
# 1. Notify users (T-48h)
# Send email/Slack notification

# 2. Enable maintenance mode (T-0)
docker-compose stop api

# 3. Perform maintenance
# - Apply security patches
sudo apt update && sudo apt upgrade -y

# - Database maintenance
docker exec postgres psql -U weatherinsight -d weatherinsight -c "VACUUM ANALYZE;"

# - Clear old logs
docker system prune -f
find /var/log -name "*.log" -mtime +90 -delete

# 4. Test services
./scripts/health_check.sh

# 5. Resume operations
docker-compose start api

# 6. Monitor for 1 hour
# Check Grafana dashboards for anomalies
```

---

## Disaster Recovery

### Backup Strategy
```bash
# Automated daily backups
0 3 * * * /opt/scripts/backup.sh

# /opt/scripts/backup.sh
#!/bin/bash
DATE=$(date +%Y%m%d)
docker exec postgres pg_dump -U weatherinsight weatherinsight | gzip > /backups/db/weatherinsight_$DATE.sql.gz
docker exec minio mc mirror minio/weatherinsight-raw /backups/minio/raw_$DATE
aws s3 sync /backups s3://weatherinsight-backups/
```

### Recovery Procedures
See [INCIDENT_RESPONSE.md](INCIDENT_RESPONSE.md) for detailed recovery procedures.

---

## Support & Escalation

### On-Call Rotation
- **Primary**: ops-primary@example.com
- **Secondary**: ops-secondary@example.com
- **Manager**: engineering-manager@example.com

### Severity Levels
- **P0 (Critical)**: Complete outage, data loss
  - Response time: 15 minutes
  - Escalation: Immediate to manager
- **P1 (High)**: Degraded performance, partial outage
  - Response time: 1 hour
  - Escalation: 2 hours to manager
- **P2 (Medium)**: Minor issues, workaround available
  - Response time: 4 hours
  - Escalation: Next business day
- **P3 (Low)**: Enhancement requests, questions
  - Response time: Next business day
  - Escalation: None

---

## Appendix

### Useful Commands
```bash
# View service logs
docker-compose logs -f <service>

# Restart specific service
docker-compose restart <service>

# Check disk usage
docker system df

# Database connections
docker exec postgres psql -U weatherinsight -d weatherinsight

# MinIO browser
mc alias set prod http://localhost:9000 minioadmin <PASSWORD>
mc ls prod/weatherinsight-raw

# Trigger manual DAG run
airflow dags trigger weatherinsight_quarterly_pipeline --conf '{"execution_date": "2024-01-01"}'

# Check Prometheus targets
curl http://localhost:9090/api/v1/targets

# Query Grafana API
curl -u admin:<PASSWORD> http://localhost:3002/api/dashboards/home
```

### Resource Sizing Guidelines
| Component | Small (<200 stations) | Medium (200-500) | Large (>500) |
|-----------|----------------------|------------------|--------------|
| PostgreSQL | 2 vCPU, 8 GB | 4 vCPU, 16 GB | 8 vCPU, 32 GB |
| Spark | 4 vCPU, 16 GB | 8 vCPU, 32 GB | 16 vCPU, 64 GB |
| MinIO | 100 GB | 500 GB | 2 TB |
| Airflow | 2 vCPU, 8 GB | 4 vCPU, 16 GB | 8 vCPU, 32 GB |
| API | 1 vCPU, 4 GB | 2 vCPU, 8 GB | 4 vCPU, 16 GB |

### Cost Estimates (AWS)
- **Small deployment**: $300-500/month
- **Medium deployment**: $800-1200/month
- **Large deployment**: $2000-3002/month

---

## Version History
- v1.0.0 (2026-02-08): Initial production deployment guide

## Local Development (Mac M1, 16GB)

This project can run on a single M1 Mac with reduced resources. Use Docker Compose only.

### Recommended Minimums
- **PostgreSQL**: 1 vCPU, 2–4 GB RAM
- **API**: 0.5–1 vCPU, 1–2 GB RAM
- **MinIO**: 0.5 vCPU, 1–2 GB RAM
- **Airflow**: 1 vCPU, 2–3 GB RAM (scheduler only)
- **Spark**: 1–2 vCPU, 2–4 GB RAM (local mode)
- **Monitoring**: Optional (disable Grafana/Prometheus for memory savings)

### Practical Tips
- Run only one pipeline at a time (ingestion or processing).
- Disable monitoring and alerting in local runs.
- Backfill a single quarter and single product only.
- Prefer local Docker images (no registry).

### Example Docker Desktop Limits
- CPU: 4–6 cores
- Memory: 8–10 GB

### Suggested Local .env Overrides
```bash
ENVIRONMENT=local
LOG_LEVEL=INFO
RATE_LIMIT=30/minute
PROMETHEUS_RETENTION_DAYS=7
SPARK_WORKER_MEMORY=2G
SPARK_WORKER_CORES=2
```

### Minimal Service Set (Local)
To keep memory usage low, run only the core services you need:
- Always required: MinIO, PostgreSQL, Redis, API
- Airflow (optional): webserver + scheduler (skip worker)
- Spark (optional): master + worker (only when running processing/aggregation)
- Monitoring: skip Prometheus, Alertmanager, Grafana, and exporters

If you need Airflow, start the init container once, then keep only webserver + scheduler running.
If you do not need orchestration, skip all Airflow services entirely.

### Local Run Order
1) Start core services (MinIO, PostgreSQL, Redis, API).
2) If running ingestion or orchestration, add Airflow webserver + scheduler.
3) If running processing/aggregation, add Spark master + worker.
4) Keep monitoring services disabled for memory savings.

### Local Compose Profiles (Recommended)
This repo includes a local compose override that makes Airflow, Spark, and monitoring optional.
Use it to start only the core services by default.

Start core services only (default):
```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d
```

Enable Airflow when needed:
```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml --profile airflow up -d
```

Enable Spark when needed:
```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml --profile spark up -d
```

Enable monitoring (not recommended on 16GB):
```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml --profile monitoring up -d
```
