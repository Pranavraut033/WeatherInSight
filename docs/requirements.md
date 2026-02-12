# Requirements

## Scope

### Data Source
- **Provider**: Deutscher Wetterdienst (DWD) Open Data
- **Product**: Climate Data Center (CDC) hourly station observations
- **URL**: https://opendata.dwd.de/climate_environment/CDC/observations_germany/climate/hourly/
- **Region**: Germany
- **Temporal Coverage**: Historical data from 1950 onwards
- **Update Frequency**: Hourly observations updated daily

### Variables of Interest
Core meteorological parameters:
- Temperature (air_temperature) - 2m above ground
- Precipitation (precipitation) - hourly sum
- Wind speed (wind_speed) and direction (wind_direction) - 10m above ground
- Pressure (pressure) - station level
- Relative humidity (relative_humidity)
- Cloud cover (cloud_cover)
- Solar radiation (solar) - where available

### Station Set
- All active and historical DWD weather stations
- Approximately 500-600 active stations
- Station metadata includes: ID, name, location (lat/lon/elevation), start/end dates

### Granularity
- Hourly observations
- Quarterly aggregation (Q1: Jan-Mar, Q2: Apr-Jun, Q3: Jul-Sep, Q4: Oct-Dec)

## Architecture

### Data Zones
1. **Raw Zone** (MinIO)
   - Immutable storage of original DWD files
   - Organized by: product/station/year/
   - Files stored with original checksums

2. **Curated Zone** (PostgreSQL)
   - Quarterly aggregated features
   - Station metadata tables
   - Dataset version tracking

### Processing Flow
1. **Ingestion**: Sync DWD files → MinIO raw zone
2. **Processing**: Parse and normalize raw files (Spark)
3. **Aggregation**: Compute quarterly features (Spark)
4. **Publishing**: Write to PostgreSQL curated tables
5. **Delivery**: Expose via FastAPI

### Orchestration
- **Scheduler**: Apache Airflow
- **Batch Frequency**: Quarterly
- **Execution Window**: First week of each quarter
- **Backfill Support**: Yes, idempotent runs

## Service Level Agreements (SLAs)

### Availability
- API uptime: 99% (excluding planned maintenance)
- Scheduled maintenance window: Sunday 02:00-04:00 UTC

### Performance
- Quarterly batch run: Complete within 24 hours
- API response time: p95 < 500ms for single-station queries
- API response time: p95 < 2s for multi-station aggregated queries

### Data Quality
- Completeness: Track and alert on >20% missing observations per station/quarter
- Timeliness: New quarter data available within 7 days of quarter end
- Accuracy: Preserve original DWD precision and units

### Monitoring & Alerting
- Airflow DAG failures → Slack/PagerDuty
- Data quality check failures → Slack
- API error rate >5% → PagerDuty
- MinIO storage >80% → Slack

## Outputs

### Curated Feature Tables
Stored in PostgreSQL:
- `station_metadata` - Station reference data
- `quarterly_temperature_features` - Temperature aggregates by station/quarter
- `quarterly_precipitation_features` - Precipitation aggregates
- `quarterly_wind_features` - Wind aggregates
- `quarterly_pressure_features` - Pressure aggregates
- `quarterly_humidity_features` - Humidity aggregates
- `dataset_versions` - Version tracking and lineage

### API Endpoints
FastAPI service providing:
- `/stations` - List all stations with metadata
- `/stations/{station_id}` - Get specific station details
- `/features/{variable}` - Get quarterly features for a variable
- `/features/{variable}/stations/{station_id}` - Get features for station
- `/health` - Service health check
- `/docs` - OpenAPI documentation

### Feature Schema
Each quarterly feature includes:
- Temporal: `year`, `quarter`, `timestamp_start`, `timestamp_end`
- Spatial: `station_id`, `latitude`, `longitude`, `elevation`
- Statistics: `mean`, `median`, `min`, `max`, `std`, `q25`, `q75`
- Quality: `count_observations`, `count_missing`, `missingness_ratio`

## Constraints & Assumptions

### Data Constraints
- DWD files are provided in fixed-width or semicolon-delimited format
- Station IDs remain stable over time
- Some stations have gaps or end dates (historical stations)

### System Constraints
- Local development environment (Docker Compose)
- Single-node Spark execution (local mode)
- PostgreSQL storage < 100GB (quarterly features only)
- MinIO raw storage grows ~1GB per month

### Assumptions
- DWD Open Data remains publicly available without authentication
- File format and schema remain backward-compatible
- No real-time requirements (batch processing is sufficient)
- Primary use case: ML feature engineering for weather models
