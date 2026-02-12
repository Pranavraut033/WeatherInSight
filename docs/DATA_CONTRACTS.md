# Data Contracts

Defines all data schemas, storage layouts, and quality expectations for WeatherInsight. 

---

## Table of Contents
1. [Raw Data Schema](#raw-data-schema) — DWD file format specifications
2. [Raw Zone Layout](#raw-zone-layout) — MinIO storage structure
3. [Curated Feature Schema](#curated-feature-schema) — PostgreSQL tables

---

## Raw Data Schema

### Overview
Defines the expected schema for DWD hourly observation files after extraction from ZIP archives. All files are semicolon-delimited text with ISO-8859-1 or UTF-8 encoding.

### File Format Properties
- **Type**: Semicolon-delimited (`;`)
- **Encoding**: ISO-8859-1 or UTF-8
- **Missing Values**: `-999`, blank, or sentinel values
- **Header**: First row contains column names

### Variable-Specific Schemas

#### 1. Air Temperature (`TU`)
Product: `stundenwerte_TU_*`

| Column | Type | Unit | Description | Missing |
|--------|------|------|-------------|---------|
| STATIONS_ID | INTEGER | - | Station ID (5 digits) | N/A |
| MESS_DATUM | TIMESTAMP | yyyyMMddhh | Measurement date/time (UTC) | N/A |
| QN_9 | INTEGER | - | Quality flag (1-10) | N/A |
| TT_TU | FLOAT | °C | Air temperature at 2m | -999 |
| RF_TU | FLOAT | % | Relative humidity | -999 |

**Example:** `00433;2023010100;3;-2.4;87`

#### 2. Precipitation (`RR`)
Product: `stundenwerte_RR_*`

| Column | Type | Unit | Description | Missing |
|--------|------|------|-------------|---------|
| STATIONS_ID | INTEGER | - | Station ID | N/A |
| MESS_DATUM | TIMESTAMP | yyyyMMddhh | Measurement date/time (UTC) | N/A |
| QN_8 | INTEGER | - | Quality flag | N/A |
| R1 | FLOAT | mm | Hourly precipitation | -999 |
| RS_IND | INTEGER | - | Precipitation indicator (0/1) | -999 |
| WRTR | INTEGER | - | Precipitation form (WMO code) | -999 |

**Example:** `01766;2023010100;3;0.5;1;6`

#### 3. Wind (`FF`)
Product: `stundenwerte_FF_*`

| Column | Type | Unit | Description | Missing |
|--------|------|------|-------------|---------|
| STATIONS_ID | INTEGER | - | Station ID | N/A |
| MESS_DATUM | TIMESTAMP | yyyyMMddhh | Measurement date/time (UTC) | N/A |
| QN_3 | INTEGER | - | Quality flag | N/A |
| F | FLOAT | m/s | Mean wind speed | -999 |
| D | INTEGER | degrees | Wind direction | -999 |

**Example:** `00164;2023010100;3;3.2;270`

#### 4. Pressure (`P0`)
Product: `stundenwerte_P0_*`

| Column | Type | Unit | Description | Missing |
|--------|------|------|-------------|---------|
| STATIONS_ID | INTEGER | - | Station ID | N/A |
| MESS_DATUM | TIMESTAMP | yyyyMMddhh | Measurement date/time (UTC) | N/A |
| QN_8 | INTEGER | - | Quality flag | N/A |
| P | FLOAT | hPa | Pressure at station level | -999 |
| P0 | FLOAT | hPa | Pressure at sea level | -999 |

**Example:** `00433;2023010100;3;1013.5;1015.2`

#### 5. Moisture (`TF`)
Product: `stundenwerte_TF_*`

| Column | Type | Unit | Description | Missing |
|--------|------|------|-------------|---------|
| STATIONS_ID | INTEGER | - | Station ID | N/A |
| MESS_DATUM | TIMESTAMP | yyyyMMddhh | Measurement date/time (UTC) | N/A |
| QN_4 | INTEGER | - | Quality flag | N/A |
| RF_TU | FLOAT | % | Relative humidity | -999 |
| TF_TU | FLOAT | °C | Dew point temperature | -999 |

#### 6. Cloud Cover (`N`)
Product: `stundenwerte_N_*`

| Column | Type | Unit | Description | Missing |
|--------|------|------|-------------|---------|
| STATIONS_ID | INTEGER | - | Station ID | N/A |
| MESS_DATUM | TIMESTAMP | yyyyMMddhh | Measurement date/time (UTC) | N/A |
| QN_8 | INTEGER | - | Quality flag | N/A |
| V_N | FLOAT | 1/8 | Total cloud cover | -999 |
| V_N_I | STRING | - | Cloud cover code | N/A |

#### 7. Solar Radiation (`ST`)
Product: `stundenwerte_ST_*`

| Column | Type | Unit | Description | Missing |
|--------|------|------|-------------|---------|
| STATIONS_ID | INTEGER | - | Station ID | N/A |
| MESS_DATUM | TIMESTAMP | yyyyMMddhh | Measurement date/time (UTC) | N/A |
| QN_592 | INTEGER | - | Quality flag | N/A |
| ATMO_STRAHL | FLOAT | J/cm² | Hourly sum of solar radiation | -999 |
| FD_STRAHL | FLOAT | J/cm² | Hourly sum of diffuse solar radiation | -999 |
| FG_STRAHL | FLOAT | J/cm² | Hourly sum of longwave downward radiation | -999 |

### Station Metadata
File: `Metadaten_Geographie_*.txt`

| Column | Type | Unit | Description |
|--------|------|------|-------------|
| Stations_id | INTEGER | - | Station ID |
| von_datum | DATE | yyyyMMdd | Start date of operation |
| bis_datum | DATE | yyyyMMdd | End date (99999999 = active) |
| Stationshoehe | INTEGER | m | Elevation above sea level |
| geoBreite | FLOAT | degrees | Latitude (decimal degrees) |
| geoLaenge | FLOAT | degrees | Longitude (decimal degrees) |
| Stationsname | STRING | - | Station name |
| Bundesland | STRING | - | Federal state |

**Example:** `00433;19470101;99999999;553;50.7983;6.0244;Aachen-Orsbach;Nordrhein-Westfalen`

### Quality Flags
- **1–3**: Automated QC passed
- **5**: Automated QC passed with corrections
- **7**: Manual QC passed
- **10**: Data not quality controlled

### Validation Rules

**Required constraints:**
- `STATIONS_ID`, `MESS_DATUM` must not be null
- All timestamps must parse to valid UTC

**Range checks (excluding `-999` missing values):**
- Temperature: −50°C to +50°C
- Humidity: 0% to 100%
- Pressure: 900–1100 hPa
- Wind speed: 0–50 m/s
- Wind direction: 0°–360°

**Data quality thresholds:**
- Fail if >30% of rows have parse errors
- Warn if >20% of values missing for a station/month
- Fail if station_id not found in metadata

---

## Raw Zone Layout

### Bucket Structure
**Bucket name:** `weatherinsight-raw`

**Prefix hierarchy:**
```
raw/
├── dwd/
│   ├── air_temperature/
│   │   ├── station_00001/
│   │   │   ├── 2023/
│   │   │   │   ├── stundenwerte_TU_00001_20230101_20231231_hist.zip
│   │   │   │   └── stundenwerte_TU_00001_20230101_20231231_hist.zip.sha256
│   ├── precipitation/
│   ├── wind/
│   ├── pressure/
│   ├── moisture/
│   ├── cloud_cover/
│   ├── solar/
│   └── station_metadata/
│       └── stations_list.txt
```

### Path Template
```
raw/dwd/{variable}/{station_id}/{year}/{filename}
```

**Components:**
- `{variable}`: DWD product name (air_temperature, precipitation, wind, etc.)
- `{station_id}`: 5-digit station ID with zero-padding (station_00001)
- `{year}`: 4-digit year (2023)
- `{filename}`: Original DWD filename as downloaded

**Examples:**
- `raw/dwd/air_temperature/station_00433/2023/stundenwerte_TU_00433_20230101_20231231_hist.zip`
- `raw/dwd/precipitation/station_01766/2024/stundenwerte_RR_01766_20240101_20241231_akt.zip`

### File Types
- **DWD archives**: `.zip` files (100KB–5MB per station-year), contain data + metadata
- **Checksums**: `.sha256` files for integrity verification
- **Metadata**: Station list files in `station_metadata/` folder, updated weekly

### Immutability Rules
1. **Write-once**: Files never modified after upload
2. **No deletion**: Files retained indefinitely (or per retention policy)
3. **Re-ingestion versioning**: If needed, append version suffix: `filename_v2.zip`

### Object Metadata
Each object stores:
- `ingest_timestamp`: Upload time
- `source_url`: Original DWD URL
- `checksum_sha256`: SHA-256 hash
- `dwd_product`: Variable/product name
- `station_id`, `year`: Data identifiers
- `dataset_version`: Version from metadata registry

### Storage Estimates
- Per station-year: ~2.3MB (5 variables combined)
- 500 stations × 10 years = 11.5GB total
- Growth: ~1.15GB per year

---

## Curated Feature Schema

### Overview
Quarterly aggregated feature tables in PostgreSQL. One row per station per quarter with full statistics and quality metrics.

### Design Principles
1. **Denormalized**: Station metadata included to avoid joins
2. **Quarterly**: Aggregated by quarter (Q1–Q4)
3. **Complete**: All statistics computed together
4. **Quality tracked**: Observation counts and missingness included
5. **Versioned**: Dataset version tracked for lineage

### Common Columns
All feature tables include:

| Column | Type | Description | Constraints |
|--------|------|-------------|-------------|
| feature_id | BIGSERIAL | Primary key | PRIMARY KEY |
| station_id | INTEGER | DWD station ID | NOT NULL |
| station_name | VARCHAR(255) | Station name | NOT NULL |
| latitude | DECIMAL(8,5) | Station latitude | NOT NULL |
| longitude | DECIMAL(8,5) | Station longitude | NOT NULL |
| elevation_m | INTEGER | Elevation (meters) | NOT NULL |
| year | INTEGER | Year (e.g., 2023) | NOT NULL |
| quarter | INTEGER | Quarter (1–4) | NOT NULL, CHECK (1 ≤ quarter ≤ 4) |
| quarter_start | TIMESTAMP | Quarter start (UTC) | NOT NULL |
| quarter_end | TIMESTAMP | Quarter end (UTC) | NOT NULL |
| dataset_version | VARCHAR(50) | Version identifier | NOT NULL |
| computed_at | TIMESTAMP | Feature computation time | NOT NULL |

### Feature Tables

#### Quarterly Temperature Features
**Table:** `quarterly_temperature_features`

| Column | Type | Unit | Description |
|--------|------|------|-------------|
| mean_temp_c | DECIMAL(5,2) | °C | Mean temperature |
| median_temp_c | DECIMAL(5,2) | °C | Median |
| min_temp_c | DECIMAL(5,2) | °C | Minimum |
| max_temp_c | DECIMAL(5,2) | °C | Maximum |
| stddev_temp_c | DECIMAL(5,2) | °C | Standard deviation |
| q25_temp_c | DECIMAL(5,2) | °C | 25th percentile |
| q75_temp_c | DECIMAL(5,2) | °C | 75th percentile |
| heating_degree_days | DECIMAL(8,2) | °C·day | HDD (base 18°C) |
| cooling_degree_days | DECIMAL(8,2) | °C·day | CDD (base 18°C) |
| frost_hours | INTEGER | hours | Hours <0°C |
| freeze_thaw_cycles | INTEGER | count | Days crossing 0°C |
| count_observations | INTEGER | - | Total hourly obs |
| count_missing | INTEGER | - | Missing observations |
| missingness_ratio | DECIMAL(5,4) | - | Fraction missing |

**Unique constraint:** `(station_id, year, quarter, dataset_version)`

#### Quarterly Precipitation Features
**Table:** `quarterly_precipitation_features`

| Column | Type | Unit | Description |
|--------|------|------|-------------|
| total_precip_mm | DECIMAL(8,2) | mm | Total |
| mean_hourly_precip_mm | DECIMAL(6,3) | mm | Mean (when >0) |
| median_precip_mm | DECIMAL(6,3) | mm | Median (incl. 0s) |
| max_hourly_precip_mm | DECIMAL(6,2) | mm | Max hourly |
| stddev_precip_mm | DECIMAL(6,3) | mm | Std dev |
| q75_precip_mm | DECIMAL(6,3) | mm | 75th percentile |
| q95_precip_mm | DECIMAL(6,2) | mm | 95th percentile |
| wet_hours | INTEGER | hours | Hours >0.1mm |
| dry_hours | INTEGER | hours | Hours ≤0.1mm |
| max_dry_spell_hours | INTEGER | hours | Longest dry period |
| max_wet_spell_hours | INTEGER | hours | Longest wet period |
| heavy_precip_hours | INTEGER | hours | Hours >10mm |
| count_observations | INTEGER | - | Total obs |
| count_missing | INTEGER | - | Missing |
| missingness_ratio | DECIMAL(5,4) | - | Fraction missing |

#### Quarterly Wind Features
**Table:** `quarterly_wind_features`

| Column | Type | Unit | Description |
|--------|------|------|-------------|
| mean_wind_speed_ms | DECIMAL(5,2) | m/s | Mean |
| median_wind_speed_ms | DECIMAL(5,2) | m/s | Median |
| max_wind_speed_ms | DECIMAL(5,2) | m/s | Maximum |
| stddev_wind_speed_ms | DECIMAL(5,2) | m/s | Std dev |
| q95_wind_speed_ms | DECIMAL(5,2) | m/s | 95th percentile |
| gust_hours | INTEGER | hours | Speed >10 m/s |
| calm_hours | INTEGER | hours | Speed <1 m/s |
| prevailing_direction | INTEGER | degrees | Most frequent (16 bins) |
| direction_variability | DECIMAL(5,4) | - | Circular std (0–1) |
| count_observations | INTEGER | - | Total obs |
| count_missing | INTEGER | - | Missing |
| missingness_ratio | DECIMAL(5,4) | - | Fraction missing |

#### Quarterly Pressure Features
**Table:** `quarterly_pressure_features`

| Column | Type | Unit | Description |
|--------|------|------|-------------|
| mean_pressure_hpa | DECIMAL(6,2) | hPa | Mean (sea level) |
| median_pressure_hpa | DECIMAL(6,2) | hPa | Median |
| min_pressure_hpa | DECIMAL(6,2) | hPa | Minimum |
| max_pressure_hpa | DECIMAL(6,2) | hPa | Maximum |
| stddev_pressure_hpa | DECIMAL(5,2) | hPa | Std dev |
| q25_pressure_hpa | DECIMAL(6,2) | hPa | 25th percentile |
| q75_pressure_hpa | DECIMAL(6,2) | hPa | 75th percentile |
| pressure_range_hpa | DECIMAL(5,2) | hPa | Max − min |
| high_pressure_hours | INTEGER | hours | >1020 hPa |
| low_pressure_hours | INTEGER | hours | <1000 hPa |
| count_observations | INTEGER | - | Total obs |
| count_missing | INTEGER | - | Missing |
| missingness_ratio | DECIMAL(5,4) | - | Fraction missing |

#### Quarterly Humidity Features
**Table:** `quarterly_humidity_features`

| Column | Type | Unit | Description |
|--------|------|------|-------------|
| mean_humidity_pct | DECIMAL(5,2) | % | Mean |
| median_humidity_pct | DECIMAL(5,2) | % | Median |
| min_humidity_pct | DECIMAL(5,2) | % | Minimum |
| max_humidity_pct | DECIMAL(5,2) | % | Maximum |
| stddev_humidity_pct | DECIMAL(5,2) | % | Std dev |
| q25_humidity_pct | DECIMAL(5,2) | % | 25th percentile |
| q75_humidity_pct | DECIMAL(5,2) | % | 75th percentile |
| high_humidity_hours | INTEGER | hours | >80% |
| low_humidity_hours | INTEGER | hours | <40% |
| count_observations | INTEGER | - | Total obs |
| count_missing | INTEGER | - | Missing |
| missingness_ratio | DECIMAL(5,4) | - | Fraction missing |

### Metadata Tables

#### Station Metadata
**Table:** `station_metadata`

| Column | Type | Description |
|--------|------|-------------|
| station_id | INTEGER | DWD station ID (PK) |
| station_name | VARCHAR(255) | Station name (NOT NULL) |
| latitude | DECIMAL(8,5) | WGS84 latitude (NOT NULL) |
| longitude | DECIMAL(8,5) | WGS84 longitude (NOT NULL) |
| elevation_m | INTEGER | Elevation MSL (NOT NULL) |
| state | VARCHAR(100) | Federal state |
| start_date | DATE | Operational start (NOT NULL) |
| end_date | DATE | Operational end (NULL = active) |
| is_active | BOOLEAN | Currently active (NOT NULL, default TRUE) |
| last_updated | TIMESTAMP | Metadata update time (NOT NULL) |

#### Dataset Versions
**Table:** `dataset_versions`

| Column | Type | Description |
|--------|------|-------------|
| version_id | SERIAL | Version ID (PK) |
| version_name | VARCHAR(50) | Version ID (NOT NULL, UNIQUE) |
| year | INTEGER | Data year (NOT NULL) |
| quarter | INTEGER | Data quarter (NOT NULL) |
| schema_version | VARCHAR(20) | Schema version (NOT NULL) |
| ingestion_run_id | VARCHAR(100) | Airflow run ID (NOT NULL) |
| processing_started_at | TIMESTAMP | Start time (NOT NULL) |
| processing_completed_at | TIMESTAMP | End time |
| status | VARCHAR(20) | processing/completed/failed |
| station_count | INTEGER | Stations processed |
| total_observations | BIGINT | Total hourly obs |
| notes | TEXT | Version notes |

### Data Quality Rules

**Mandatory validations:**
1. `count_observations + count_missing` = ~2184 (expected quarter hours)
2. `missingness_ratio` = `count_missing / (count_observations + count_missing)`
3. All `station_id` values must exist in `station_metadata`
4. All `dataset_version` values must exist in `dataset_versions`

**Range checks:**
- Temperature: −50°C to +50°C
- Precipitation: ≥0 mm
- Wind: ≥0 m/s
- Humidity: 0–100%
- Pressure: 900–1100 hPa

**Alert thresholds:**
- Warn if `missingness_ratio` >0.20 for any station/quarter
- Fail if any statistic is NULL when `count_observations` >0
- Fail if `quarter_start`/`quarter_end` don't align with year/quarter

### Indexes
```sql
CREATE INDEX idx_temp_station_time ON quarterly_temperature_features(station_id, year, quarter);
CREATE INDEX idx_temp_year_quarter ON quarterly_temperature_features(year, quarter);
CREATE INDEX idx_station_location ON station_metadata(latitude, longitude);
CREATE INDEX idx_station_active ON station_metadata(is_active);
-- Similar indexes on precipitation, wind, pressure, humidity tables
```

### Storage & Growth
- **Per feature table**: ~20MB for 500 stations × 4 quarters × 10 years
- **Total curated zone**: ~80MB for 5 feature tables
- **Growth rate**: ~8MB per year

---

## Schema Versioning & Migration

### Current Version
- **v1.0** (2024-01-01): Initial schema

### Migration Strategy
- **New columns**: Add as nullable, backfill if needed
- **Breaking changes**: Create new table version (e.g., `quarterly_temperature_features_v2`)
- **Deprecation**: Maintain old tables for 2 quarters, then drop

### References
- DWD Climate Data Center: https://opendata.dwd.de/climate_environment/CDC/
- DWD Observations: https://opendata.dwd.de/climate_environment/CDC/observations_germany/climate/hourly/
