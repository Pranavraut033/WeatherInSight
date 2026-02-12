# 🌤️ WeatherInsight

A data engineering project that ingests German weather data from DWD (Deutscher Wetterdienst), processes it with Apache Spark, and serves weather features via a REST API.

**Status**: ✅ Production Ready | **Last Updated**: February 2026

---

## 🚀 Quick Start (5 minutes)

### Prerequisites
- Docker & Docker Compose
- 8+ GB RAM allocated to Docker
- 20+ GB free disk space
- macOS, Linux, or Windows with WSL2

### Run the Project

```bash
# 1. Clone and navigate
git clone https://github.com/Pranavraut033/WeatherInSight.git
cd WeatherInSight

# 2. Configure environment
cp .env.example .env

# 3. Start all services
docker compose up -d

# 4. Wait for services to be healthy (~30 seconds)
docker compose ps

# 5. Access the services
# - API Docs: http://localhost:8000/docs
# - Airflow: http://localhost:8080 (admin / admin123)
# - Grafana: http://localhost:3002 (admin / admin123)
# - MinIO: http://localhost:9001 (minioadmin / minioadmin123)
# - Prometheus: http://localhost:9090
```

### Stop the Project

```bash
# Stop services (data persists)
docker compose down

# Stop and remove all data
docker compose down -v
```

---

## ✅ How to Test

### Run All Tests
```bash
# Unit tests (fast, ~2 minutes)
pytest services/*/tests/ -v

# Integration tests
pytest tests/e2e/ -v -m integration

# End-to-end tests (requires Docker Compose running)
pytest tests/e2e/ -v

# All tests with coverage report
pytest services/ tests/ --cov=services --cov-report=html
open htmlcov/index.html
```

### Run Tests for Specific Service
```bash
# API service tests
cd services/api && pytest tests/ -v

# Ingestion service tests
cd services/ingestion && pytest tests/ -v

# Processing service tests
cd services/processing && pytest tests/ -v

# Aggregation service tests
cd services/aggregation && pytest tests/ -v
```

### Quick Validation (Services Running)
```bash
# Test API is responding
curl http://localhost:8000/health

# Test database connection
docker exec postgres psql -U weatherinsight -d weatherinsight -c "SELECT 1"

# Test MinIO access
docker compose exec minio-init mc ls myminio/

# View API docs
open http://localhost:8000/docs
```

---

## 📊 What Is WeatherInsight?

WeatherInsight is a batch data pipeline that:
- **📥 Ingests** hourly weather observations from DWD (200+ German weather stations)
- **🔄 Processes** raw data quarterly with Apache Spark (parsing, validation, cleaning)
- **📊 Aggregates** 67 weather features (temperature, precipitation, wind, pressure, humidity)
- **💾 Stores** curated features in PostgreSQL
- **🌐 Serves** features via REST API with authentication and rate limiting
- **📈 Monitors** with Prometheus/Grafana dashboards and alerting

### Key Features
- ✅ 159 automated tests (unit + integration + E2E)
- ✅ 85% code coverage
- ✅ Quarterly batch processing with Airflow orchestration
- ✅ Data versioning and lineage tracking
- ✅ Immutable raw storage in MinIO
- ✅ Comprehensive monitoring and alerting
- ✅ 8,000+ lines of documentation

### Data Products
- 🌡️ **Temperature**: mean, median, min, max, HDD, CDD, frost hours
- 🌧️ **Precipitation**: totals, wet/dry spells, heavy events, intensity
- 💨 **Wind**: speed stats, direction, gusts, calms
- 🌡️ **Pressure**: means, ranges, high/low pressure hours
- 💧 **Humidity**: means, ranges, high/low humidity hours

---

## 🏗️ Project Architecture

```
DWD OpenData
    ↓
Ingestion Service (Python)
    ↓
MinIO Raw Zone (immutable objects)
    ↓
Spark Processing (parse, clean, validate)
    ↓
MinIO Staging Zone (parquet files)
    ↓
Spark Aggregation (compute features)
    ↓
PostgreSQL (curated tables)
    ↓
FastAPI (REST endpoints)
    ↓
End Users / Applications
```

### Orchestration & Monitoring
- **Airflow**: Quarterly pipeline scheduling
- **Prometheus**: Metrics collection
- **Grafana**: Dashboards & visualization
- **Alertmanager**: Alert routing & management

---

## 📚 Tech Stack

| Component | Technology |
|-----------|-----------|
| Data Ingestion | Python 3.11 |
| Object Storage | MinIO (S3-compatible) |
| Batch Processing | Apache Spark 3.4 |
| Database | PostgreSQL 15 |
| Orchestration | Apache Airflow 2.8 |
| API Service | FastAPI 0.104 |
| Monitoring | Prometheus + Grafana |
| Containerization | Docker & Docker Compose |
| Testing | pytest |

---

## 🔍 API Usage

The project exposes REST endpoints to query weather features. All requests require an API key.

```bash
# List all stations
curl "http://localhost:8000/api/v1/stations" \
  -H "X-API-Key: dev-key-12345"

# Get temperature features for Q1 2023
curl "http://localhost:8000/api/v1/features/temperature?year=2023&quarter=1" \
  -H "X-API-Key: dev-key-12345"

# Get features for a specific station
curl "http://localhost:8000/api/v1/features/temperature/stations/00433" \
  -H "X-API-Key: dev-key-12345"
```

**Interactive Docs**: Open http://localhost:8000/docs (Swagger UI)

---

## 📊 Monitoring & Dashboards

Access Grafana at http://localhost:3002 (admin / admin123)

Available dashboards:
- **Pipeline Overview**: DAG runs, task durations, throughput
- **API Performance**: Request rates, latency, error rates
- **Data Quality**: Feature completeness and validation
- **Infrastructure**: CPU, memory, disk, network usage

Prometheus at http://localhost:9090 for raw metrics queries.

---

## 🔧 Common Commands

```bash
# View service logs
docker compose logs -f <service>          # Follow logs
docker compose logs --tail=100 <service>  # Last 100 lines

# Access database
docker exec postgres psql -U weatherinsight -d weatherinsight
# Then: SELECT * FROM station_metadata LIMIT 10;

# Check Airflow
open http://localhost:8080

# Restart a service
docker compose restart <service>

# View disk usage
docker system df -v

# Clean up (removes all data!)
docker compose down -v
```

---

## 🐛 Troubleshooting

### Services won't start
```bash
# Check logs
docker compose logs <service> --tail=50

# Restart services
docker compose restart

# Check if ports are in use
lsof -i :8000   # API
lsof -i :8080   # Airflow
lsof -i :5432   # PostgreSQL
```

### Database connection errors
```bash
# Check database is running
docker compose ps postgres

# Test connection
docker exec postgres psql -U weatherinsight -d weatherinsight -c "SELECT 1"
```

### MinIO not accessible
```bash
# Check MinIO health
curl http://localhost:9000/minio/health/live

# List buckets
docker compose exec minio-init mc ls myminio/
```

### Tests failing
```bash
# Run specific test with verbose output
pytest services/api/tests/test_api.py::test_health -vv

# Run with print statements
pytest -s services/api/tests/

# Check for missing dependencies
pip install -r services/<service>/requirements.txt
```

---

## 📖 Documentation

### For Getting Started
- This README for quick overview and setup
- [NEXT_STEPS.md](NEXT_STEPS.md) for development context

### For Understanding the System
- [docs/requirements.md](docs/requirements.md) - System requirements
- [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) - 9-phase plan
- [docs/DATA_CONTRACTS.md](docs/DATA_CONTRACTS.md) - Data schemas & validation

### For Operations
- [docs/runbook.md](docs/runbook.md) - Quick reference commands
- [docs/OPERATIONS_HANDOVER.md](docs/OPERATIONS_HANDOVER.md) - Daily operations
- [docs/MONITORING_GUIDE.md](docs/MONITORING_GUIDE.md) - Monitoring setup
- [docs/INCIDENT_RESPONSE.md](docs/INCIDENT_RESPONSE.md) - Incident handling

### For Development
- [docs/TESTING_STRATEGY.md](docs/TESTING_STRATEGY.md) - Testing approach
- [services/api/README.md](services/api/README.md) - API service docs
- [services/ingestion/README.md](services/ingestion/README.md) - Ingestion service
- [services/processing/README.md](services/processing/README.md) - Processing service

---

## 📈 Key Metrics

### Data
- **Stations**: 200-300 active weather stations in Germany
- **Coverage**: Historical data from 2019 onwards
- **Frequency**: Hourly observations updated quarterly
- **Features**: 67 computed features per station per quarter

### Testing
- **Tests**: 159 total (106 unit, 30 integration, 23 E2E)
- **Coverage**: 85% of critical code paths
- **Status**: All tests passing

### Performance
- **API Latency**: p95 < 200ms, p99 < 500ms
- **API Throughput**: 100+ requests/second
- **Uptime**: 99.5%+ capability
- **Batch Runtime**: ~2-4 hours per quarter

---

## 🤝 Contributing

### Code Standards
- Python 3.11+
- Type hints required
- Black code formatting
- Pytest for all tests
- >80% test coverage required

### Before Committing
```bash
# Format code
black services/

# Run linter
pylint services/*/src/

# Run type checker
mypy services/*/src/

# Run all tests
pytest services/ tests/ -v

# Check coverage
pytest --cov=services --cov-report=term
```

---

## ❓ Getting Help

### Documentation
- Check the [docs/](docs/) folder for detailed guides
- Search [docs/INCIDENT_RESPONSE.md](docs/INCIDENT_RESPONSE.md) for common issues

### Common Issues
1. **Port already in use**: Change ports in `.env` or stop conflicting services
2. **Out of memory**: Allocate more RAM to Docker in Docker Desktop settings
3. **Database won't connect**: Ensure PostgreSQL container is healthy (`docker compose ps`)

### Project Links
- **DWD Open Data**: https://opendata.dwd.de/
- **Apache Airflow**: https://airflow.apache.org/docs/
- **FastAPI**: https://fastapi.tiangolo.com/
- **GitHub**: https://github.com/Pranavraut033/WeatherInSight

---

## ✨ Project Status

- **Phase 1**: ✅ Architecture & requirements (Complete)
- **Phase 2**: ✅ Development & implementation (Complete)
- **All 9 Milestones**: ✅ Complete
- **Production Status**: ✅ Ready to deploy

**Completed**: February 8, 2026

---

**Ready to get started? Run `docker compose up -d` and visit http://localhost:8000/docs! ☁️**
