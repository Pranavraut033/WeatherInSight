"""SQLAlchemy ORM models and Pydantic response schemas."""

from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Column, Integer, BigInteger, String, Float, DateTime, 
    Boolean, Date, Text, Index
)
from pydantic import BaseModel, Field, ConfigDict

from app.database import Base


# ============================================================================
# SQLAlchemy ORM Models (Database Tables)
# ============================================================================

class StationMetadata(Base):
    """Station metadata table."""
    __tablename__ = "station_metadata"
    
    station_id = Column(Integer, primary_key=True)
    station_name = Column(String(255))
    latitude = Column(Float)
    longitude = Column(Float)
    elevation_m = Column(Float)
    state = Column(String(100))
    start_date = Column(Date)
    end_date = Column(Date, nullable=True)
    is_active = Column(Boolean, default=True)
    last_updated = Column(DateTime, default=datetime.utcnow)


class DatasetVersion(Base):
    """Dataset versioning table."""
    __tablename__ = "dataset_versions"
    
    version_id = Column(Integer, primary_key=True, autoincrement=True)
    version_name = Column(String(100), unique=True, nullable=False)
    year = Column(Integer, nullable=False)
    quarter = Column(Integer, nullable=False)
    schema_version = Column(String(50), nullable=False)
    ingestion_run_id = Column(String(100))
    processing_started_at = Column(DateTime)
    processing_completed_at = Column(DateTime)
    status = Column(String(50))
    station_count = Column(Integer)
    total_observations = Column(BigInteger)
    notes = Column(Text)


class QuarterlyTemperatureFeatures(Base):
    """Temperature features table."""
    __tablename__ = "quarterly_temperature_features"
    
    feature_id = Column(BigInteger, primary_key=True, autoincrement=True)
    station_id = Column(Integer, nullable=False, index=True)
    station_name = Column(String(255))
    latitude = Column(Float)
    longitude = Column(Float)
    elevation_m = Column(Float)
    year = Column(Integer, nullable=False, index=True)
    quarter = Column(Integer, nullable=False, index=True)
    quarter_start = Column(DateTime)
    quarter_end = Column(DateTime)
    dataset_version = Column(String(100))
    computed_at = Column(DateTime)
    
    # Temperature features
    mean_temp_c = Column(Float)
    median_temp_c = Column(Float)
    min_temp_c = Column(Float)
    max_temp_c = Column(Float)
    stddev_temp_c = Column(Float)
    q25_temp_c = Column(Float)
    q75_temp_c = Column(Float)
    heating_degree_days = Column(Float)
    cooling_degree_days = Column(Float)
    frost_hours = Column(Integer)
    freeze_thaw_cycles = Column(Integer)
    count_observations = Column(Integer)
    count_missing = Column(Integer)
    missingness_ratio = Column(Float)
    
    __table_args__ = (
        Index('idx_temp_station_year_quarter', 'station_id', 'year', 'quarter', unique=True),
    )


class QuarterlyPrecipitationFeatures(Base):
    """Precipitation features table."""
    __tablename__ = "quarterly_precipitation_features"
    
    feature_id = Column(BigInteger, primary_key=True, autoincrement=True)
    station_id = Column(Integer, nullable=False, index=True)
    station_name = Column(String(255))
    latitude = Column(Float)
    longitude = Column(Float)
    elevation_m = Column(Float)
    year = Column(Integer, nullable=False, index=True)
    quarter = Column(Integer, nullable=False, index=True)
    quarter_start = Column(DateTime)
    quarter_end = Column(DateTime)
    dataset_version = Column(String(100))
    computed_at = Column(DateTime)
    
    # Precipitation features
    total_precip_mm = Column(Float)
    mean_hourly_precip_mm = Column(Float)
    median_precip_mm = Column(Float)
    max_hourly_precip_mm = Column(Float)
    stddev_precip_mm = Column(Float)
    q75_precip_mm = Column(Float)
    q95_precip_mm = Column(Float)
    wet_hours = Column(Integer)
    dry_hours = Column(Integer)
    max_dry_spell_hours = Column(Integer)
    max_wet_spell_hours = Column(Integer)
    heavy_precip_hours = Column(Integer)
    count_observations = Column(Integer)
    count_missing = Column(Integer)
    missingness_ratio = Column(Float)
    
    __table_args__ = (
        Index('idx_precip_station_year_quarter', 'station_id', 'year', 'quarter', unique=True),
    )


class QuarterlyWindFeatures(Base):
    """Wind features table."""
    __tablename__ = "quarterly_wind_features"
    
    feature_id = Column(BigInteger, primary_key=True, autoincrement=True)
    station_id = Column(Integer, nullable=False, index=True)
    station_name = Column(String(255))
    latitude = Column(Float)
    longitude = Column(Float)
    elevation_m = Column(Float)
    year = Column(Integer, nullable=False, index=True)
    quarter = Column(Integer, nullable=False, index=True)
    quarter_start = Column(DateTime)
    quarter_end = Column(DateTime)
    dataset_version = Column(String(100))
    computed_at = Column(DateTime)
    
    # Wind features
    mean_wind_speed_ms = Column(Float)
    median_wind_speed_ms = Column(Float)
    min_wind_speed_ms = Column(Float)
    max_wind_speed_ms = Column(Float)
    stddev_wind_speed_ms = Column(Float)
    q75_wind_speed_ms = Column(Float)
    q95_wind_speed_ms = Column(Float)
    gust_hours = Column(Integer)
    calm_hours = Column(Integer)
    prevailing_direction = Column(String(10))
    direction_variability = Column(Float)
    count_observations = Column(Integer)
    count_missing = Column(Integer)
    missingness_ratio = Column(Float)
    
    __table_args__ = (
        Index('idx_wind_station_year_quarter', 'station_id', 'year', 'quarter', unique=True),
    )


class QuarterlyPressureFeatures(Base):
    """Pressure features table."""
    __tablename__ = "quarterly_pressure_features"
    
    feature_id = Column(BigInteger, primary_key=True, autoincrement=True)
    station_id = Column(Integer, nullable=False, index=True)
    station_name = Column(String(255))
    latitude = Column(Float)
    longitude = Column(Float)
    elevation_m = Column(Float)
    year = Column(Integer, nullable=False, index=True)
    quarter = Column(Integer, nullable=False, index=True)
    quarter_start = Column(DateTime)
    quarter_end = Column(DateTime)
    dataset_version = Column(String(100))
    computed_at = Column(DateTime)
    
    # Pressure features
    mean_pressure_hpa = Column(Float)
    median_pressure_hpa = Column(Float)
    min_pressure_hpa = Column(Float)
    max_pressure_hpa = Column(Float)
    stddev_pressure_hpa = Column(Float)
    q25_pressure_hpa = Column(Float)
    q75_pressure_hpa = Column(Float)
    pressure_range_hpa = Column(Float)
    high_pressure_hours = Column(Integer)
    low_pressure_hours = Column(Integer)
    count_observations = Column(Integer)
    count_missing = Column(Integer)
    missingness_ratio = Column(Float)
    
    __table_args__ = (
        Index('idx_pressure_station_year_quarter', 'station_id', 'year', 'quarter', unique=True),
    )


class QuarterlyHumidityFeatures(Base):
    """Humidity features table."""
    __tablename__ = "quarterly_humidity_features"
    
    feature_id = Column(BigInteger, primary_key=True, autoincrement=True)
    station_id = Column(Integer, nullable=False, index=True)
    station_name = Column(String(255))
    latitude = Column(Float)
    longitude = Column(Float)
    elevation_m = Column(Float)
    year = Column(Integer, nullable=False, index=True)
    quarter = Column(Integer, nullable=False, index=True)
    quarter_start = Column(DateTime)
    quarter_end = Column(DateTime)
    dataset_version = Column(String(100))
    computed_at = Column(DateTime)
    
    # Humidity features
    mean_humidity_pct = Column(Float)
    median_humidity_pct = Column(Float)
    min_humidity_pct = Column(Float)
    max_humidity_pct = Column(Float)
    stddev_humidity_pct = Column(Float)
    q25_humidity_pct = Column(Float)
    q75_humidity_pct = Column(Float)
    high_humidity_hours = Column(Integer)
    low_humidity_hours = Column(Integer)
    count_observations = Column(Integer)
    count_missing = Column(Integer)
    missingness_ratio = Column(Float)
    
    __table_args__ = (
        Index('idx_humidity_station_year_quarter', 'station_id', 'year', 'quarter', unique=True),
    )


# ============================================================================
# Pydantic Response Models (API Responses)
# ============================================================================

class StationResponse(BaseModel):
    """Station metadata response."""
    model_config = ConfigDict(from_attributes=True)
    
    station_id: int
    station_name: str
    latitude: float
    longitude: float
    elevation_m: float
    state: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    is_active: bool = True


class FeatureResponseBase(BaseModel):
    """Base response for all feature types (common fields)."""
    model_config = ConfigDict(from_attributes=True)
    
    feature_id: int
    station_id: int
    station_name: str
    latitude: float
    longitude: float
    elevation_m: float
    year: int
    quarter: int = Field(ge=1, le=4)
    quarter_start: datetime
    quarter_end: datetime
    dataset_version: Optional[str] = None
    computed_at: Optional[datetime] = None


class TemperatureFeatureResponse(FeatureResponseBase):
    """Temperature feature response with all temperature-specific fields."""
    mean_temp_c: Optional[float] = None
    median_temp_c: Optional[float] = None
    min_temp_c: Optional[float] = None
    max_temp_c: Optional[float] = None
    stddev_temp_c: Optional[float] = None
    q25_temp_c: Optional[float] = None
    q75_temp_c: Optional[float] = None
    heating_degree_days: Optional[float] = None
    cooling_degree_days: Optional[float] = None
    frost_hours: Optional[int] = None
    freeze_thaw_cycles: Optional[int] = None
    count_observations: Optional[int] = None
    count_missing: Optional[int] = None
    missingness_ratio: Optional[float] = None


class PrecipitationFeatureResponse(FeatureResponseBase):
    """Precipitation feature response."""
    total_precip_mm: Optional[float] = None
    mean_hourly_precip_mm: Optional[float] = None
    median_precip_mm: Optional[float] = None
    max_hourly_precip_mm: Optional[float] = None
    stddev_precip_mm: Optional[float] = None
    q75_precip_mm: Optional[float] = None
    q95_precip_mm: Optional[float] = None
    wet_hours: Optional[int] = None
    dry_hours: Optional[int] = None
    max_dry_spell_hours: Optional[int] = None
    max_wet_spell_hours: Optional[int] = None
    heavy_precip_hours: Optional[int] = None
    count_observations: Optional[int] = None
    count_missing: Optional[int] = None
    missingness_ratio: Optional[float] = None


class WindFeatureResponse(FeatureResponseBase):
    """Wind feature response."""
    mean_wind_speed_ms: Optional[float] = None
    median_wind_speed_ms: Optional[float] = None
    min_wind_speed_ms: Optional[float] = None
    max_wind_speed_ms: Optional[float] = None
    stddev_wind_speed_ms: Optional[float] = None
    q75_wind_speed_ms: Optional[float] = None
    q95_wind_speed_ms: Optional[float] = None
    gust_hours: Optional[int] = None
    calm_hours: Optional[int] = None
    prevailing_direction: Optional[str] = None
    direction_variability: Optional[float] = None
    count_observations: Optional[int] = None
    count_missing: Optional[int] = None
    missingness_ratio: Optional[float] = None


class PressureFeatureResponse(FeatureResponseBase):
    """Pressure feature response."""
    mean_pressure_hpa: Optional[float] = None
    median_pressure_hpa: Optional[float] = None
    min_pressure_hpa: Optional[float] = None
    max_pressure_hpa: Optional[float] = None
    stddev_pressure_hpa: Optional[float] = None
    q25_pressure_hpa: Optional[float] = None
    q75_pressure_hpa: Optional[float] = None
    pressure_range_hpa: Optional[float] = None
    high_pressure_hours: Optional[int] = None
    low_pressure_hours: Optional[int] = None
    count_observations: Optional[int] = None
    count_missing: Optional[int] = None
    missingness_ratio: Optional[float] = None


class HumidityFeatureResponse(FeatureResponseBase):
    """Humidity feature response."""
    mean_humidity_pct: Optional[float] = None
    median_humidity_pct: Optional[float] = None
    min_humidity_pct: Optional[float] = None
    max_humidity_pct: Optional[float] = None
    stddev_humidity_pct: Optional[float] = None
    q25_humidity_pct: Optional[float] = None
    q75_humidity_pct: Optional[float] = None
    high_humidity_hours: Optional[int] = None
    low_humidity_hours: Optional[int] = None
    count_observations: Optional[int] = None
    count_missing: Optional[int] = None
    missingness_ratio: Optional[float] = None


class PaginatedResponse(BaseModel):
    """Paginated response wrapper."""
    total: int
    limit: int
    offset: int
    items: list
