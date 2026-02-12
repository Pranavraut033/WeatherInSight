-- WeatherInsight PostgreSQL Initialization Script
-- This script creates the database schema for curated feature tables

-- Create Airflow database if it doesn't exist
-- NOTE: This must be run as superuser or the statement will be ignored
SELECT 'CREATE DATABASE airflow' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'airflow')\gexec

-- Create schema
CREATE SCHEMA IF NOT EXISTS public;

-- Station Metadata Table
CREATE TABLE IF NOT EXISTS station_metadata (
    station_id INTEGER PRIMARY KEY,
    station_name VARCHAR(255) NOT NULL,
    latitude DECIMAL(8,5) NOT NULL,
    longitude DECIMAL(8,5) NOT NULL,
    elevation_m INTEGER NOT NULL,
    state VARCHAR(100),
    start_date DATE NOT NULL,
    end_date DATE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_updated TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_station_location ON station_metadata(latitude, longitude);
CREATE INDEX idx_station_active ON station_metadata(is_active);

-- Dataset Versions Table
CREATE TABLE IF NOT EXISTS dataset_versions (
    version_id SERIAL PRIMARY KEY,
    version_name VARCHAR(50) NOT NULL UNIQUE,
    year INTEGER NOT NULL,
    quarter INTEGER NOT NULL CHECK (quarter BETWEEN 1 AND 4),
    schema_version VARCHAR(20) NOT NULL,
    ingestion_run_id VARCHAR(100) NOT NULL,
    processing_started_at TIMESTAMP NOT NULL,
    processing_completed_at TIMESTAMP,
    status VARCHAR(20) NOT NULL,
    station_count INTEGER,
    total_observations BIGINT,
    notes TEXT
);

CREATE INDEX idx_dataset_version_status ON dataset_versions(status);
CREATE INDEX idx_dataset_year_quarter ON dataset_versions(year, quarter);

-- Quarterly Temperature Features
CREATE TABLE IF NOT EXISTS quarterly_temperature_features (
    feature_id BIGSERIAL PRIMARY KEY,
    station_id INTEGER NOT NULL,
    station_name VARCHAR(255) NOT NULL,
    latitude DECIMAL(8,5) NOT NULL,
    longitude DECIMAL(8,5) NOT NULL,
    elevation_m INTEGER NOT NULL,
    year INTEGER NOT NULL,
    quarter INTEGER NOT NULL CHECK (quarter BETWEEN 1 AND 4),
    quarter_start TIMESTAMP NOT NULL,
    quarter_end TIMESTAMP NOT NULL,
    dataset_version VARCHAR(50) NOT NULL,
    computed_at TIMESTAMP NOT NULL DEFAULT NOW(),
    mean_temp_c DECIMAL(5,2),
    median_temp_c DECIMAL(5,2),
    min_temp_c DECIMAL(5,2),
    max_temp_c DECIMAL(5,2),
    stddev_temp_c DECIMAL(5,2),
    q25_temp_c DECIMAL(5,2),
    q75_temp_c DECIMAL(5,2),
    count_observations INTEGER,
    count_missing INTEGER,
    missingness_ratio DECIMAL(5,4),
    heating_degree_days DECIMAL(8,2),
    cooling_degree_days DECIMAL(8,2),
    frost_hours INTEGER,
    freeze_thaw_cycles INTEGER,
    UNIQUE(station_id, year, quarter, dataset_version)
);

CREATE INDEX idx_temp_station_time ON quarterly_temperature_features(station_id, year, quarter);
CREATE INDEX idx_temp_year_quarter ON quarterly_temperature_features(year, quarter);

-- Quarterly Precipitation Features
CREATE TABLE IF NOT EXISTS quarterly_precipitation_features (
    feature_id BIGSERIAL PRIMARY KEY,
    station_id INTEGER NOT NULL,
    station_name VARCHAR(255) NOT NULL,
    latitude DECIMAL(8,5) NOT NULL,
    longitude DECIMAL(8,5) NOT NULL,
    elevation_m INTEGER NOT NULL,
    year INTEGER NOT NULL,
    quarter INTEGER NOT NULL CHECK (quarter BETWEEN 1 AND 4),
    quarter_start TIMESTAMP NOT NULL,
    quarter_end TIMESTAMP NOT NULL,
    dataset_version VARCHAR(50) NOT NULL,
    computed_at TIMESTAMP NOT NULL DEFAULT NOW(),
    total_precip_mm DECIMAL(8,2),
    mean_hourly_precip_mm DECIMAL(6,3),
    median_precip_mm DECIMAL(6,3),
    max_hourly_precip_mm DECIMAL(6,2),
    stddev_precip_mm DECIMAL(6,3),
    q75_precip_mm DECIMAL(6,3),
    q95_precip_mm DECIMAL(6,2),
    wet_hours INTEGER,
    dry_hours INTEGER,
    max_dry_spell_hours INTEGER,
    max_wet_spell_hours INTEGER,
    heavy_precip_hours INTEGER,
    count_observations INTEGER,
    count_missing INTEGER,
    missingness_ratio DECIMAL(5,4),
    UNIQUE(station_id, year, quarter, dataset_version)
);

CREATE INDEX idx_precip_station_time ON quarterly_precipitation_features(station_id, year, quarter);
CREATE INDEX idx_precip_year_quarter ON quarterly_precipitation_features(year, quarter);

-- Quarterly Wind Features
CREATE TABLE IF NOT EXISTS quarterly_wind_features (
    feature_id BIGSERIAL PRIMARY KEY,
    station_id INTEGER NOT NULL,
    station_name VARCHAR(255) NOT NULL,
    latitude DECIMAL(8,5) NOT NULL,
    longitude DECIMAL(8,5) NOT NULL,
    elevation_m INTEGER NOT NULL,
    year INTEGER NOT NULL,
    quarter INTEGER NOT NULL CHECK (quarter BETWEEN 1 AND 4),
    quarter_start TIMESTAMP NOT NULL,
    quarter_end TIMESTAMP NOT NULL,
    dataset_version VARCHAR(50) NOT NULL,
    computed_at TIMESTAMP NOT NULL DEFAULT NOW(),
    mean_wind_speed_ms DECIMAL(5,2),
    median_wind_speed_ms DECIMAL(5,2),
    min_wind_speed_ms DECIMAL(5,2),
    max_wind_speed_ms DECIMAL(5,2),
    stddev_wind_speed_ms DECIMAL(5,2),
    q75_wind_speed_ms DECIMAL(5,2),
    q95_wind_speed_ms DECIMAL(5,2),
    gust_hours INTEGER,
    calm_hours INTEGER,
    prevailing_direction INTEGER,
    direction_variability DECIMAL(5,4),
    count_observations INTEGER,
    count_missing INTEGER,
    missingness_ratio DECIMAL(5,4),
    UNIQUE(station_id, year, quarter, dataset_version)
);

CREATE INDEX idx_wind_station_time ON quarterly_wind_features(station_id, year, quarter);
CREATE INDEX idx_wind_year_quarter ON quarterly_wind_features(year, quarter);

-- Quarterly Pressure Features
CREATE TABLE IF NOT EXISTS quarterly_pressure_features (
    feature_id BIGSERIAL PRIMARY KEY,
    station_id INTEGER NOT NULL,
    station_name VARCHAR(255) NOT NULL,
    latitude DECIMAL(8,5) NOT NULL,
    longitude DECIMAL(8,5) NOT NULL,
    elevation_m INTEGER NOT NULL,
    year INTEGER NOT NULL,
    quarter INTEGER NOT NULL CHECK (quarter BETWEEN 1 AND 4),
    quarter_start TIMESTAMP NOT NULL,
    quarter_end TIMESTAMP NOT NULL,
    dataset_version VARCHAR(50) NOT NULL,
    computed_at TIMESTAMP NOT NULL DEFAULT NOW(),
    mean_pressure_hpa DECIMAL(6,2),
    median_pressure_hpa DECIMAL(6,2),
    min_pressure_hpa DECIMAL(6,2),
    max_pressure_hpa DECIMAL(6,2),
    stddev_pressure_hpa DECIMAL(5,2),
    q25_pressure_hpa DECIMAL(6,2),
    q75_pressure_hpa DECIMAL(6,2),
    pressure_range_hpa DECIMAL(5,2),
    high_pressure_hours INTEGER,
    low_pressure_hours INTEGER,
    count_observations INTEGER,
    count_missing INTEGER,
    missingness_ratio DECIMAL(5,4),
    UNIQUE(station_id, year, quarter, dataset_version)
);

CREATE INDEX idx_pressure_station_time ON quarterly_pressure_features(station_id, year, quarter);
CREATE INDEX idx_pressure_year_quarter ON quarterly_pressure_features(year, quarter);

-- Quarterly Humidity Features
CREATE TABLE IF NOT EXISTS quarterly_humidity_features (
    feature_id BIGSERIAL PRIMARY KEY,
    station_id INTEGER NOT NULL,
    station_name VARCHAR(255) NOT NULL,
    latitude DECIMAL(8,5) NOT NULL,
    longitude DECIMAL(8,5) NOT NULL,
    elevation_m INTEGER NOT NULL,
    year INTEGER NOT NULL,
    quarter INTEGER NOT NULL CHECK (quarter BETWEEN 1 AND 4),
    quarter_start TIMESTAMP NOT NULL,
    quarter_end TIMESTAMP NOT NULL,
    dataset_version VARCHAR(50) NOT NULL,
    computed_at TIMESTAMP NOT NULL DEFAULT NOW(),
    mean_humidity_pct DECIMAL(5,2),
    median_humidity_pct DECIMAL(5,2),
    min_humidity_pct DECIMAL(5,2),
    max_humidity_pct DECIMAL(5,2),
    stddev_humidity_pct DECIMAL(5,2),
    q25_humidity_pct DECIMAL(5,2),
    q75_humidity_pct DECIMAL(5,2),
    high_humidity_hours INTEGER,
    low_humidity_hours INTEGER,
    count_observations INTEGER,
    count_missing INTEGER,
    missingness_ratio DECIMAL(5,4),
    UNIQUE(station_id, year, quarter, dataset_version)
);

CREATE INDEX idx_humidity_station_time ON quarterly_humidity_features(station_id, year, quarter);
CREATE INDEX idx_humidity_year_quarter ON quarterly_humidity_features(year, quarter);

-- Grant permissions
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO weatherinsight;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO weatherinsight;
