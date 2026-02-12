"""Test configuration and fixtures."""

import pytest
from datetime import datetime, date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.main import app
from app.database import Base, get_db
from app.models import (
    StationMetadata,
    QuarterlyTemperatureFeatures,
    QuarterlyPrecipitationFeatures,
    QuarterlyWindFeatures,
    QuarterlyPressureFeatures,
    QuarterlyHumidityFeatures,
)

# Test database URL (in-memory SQLite)
TEST_DATABASE_URL = "sqlite:///:memory:"


@pytest.fixture(scope="function")
def test_db():
    """Create a test database with tables."""
    engine = create_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False}
    )
    
    # Create all tables
    Base.metadata.create_all(bind=engine)
    
    # Create session
    TestingSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine
    )
    
    db = TestingSessionLocal()
    
    yield db
    
    db.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(test_db):
    """Create a test client with test database."""
    def override_get_db():
        try:
            yield test_db
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    
    with TestClient(app) as test_client:
        yield test_client
    
    app.dependency_overrides.clear()


@pytest.fixture
def sample_stations(test_db):
    """Create sample station metadata."""
    stations = [
        StationMetadata(
            station_id=433,
            station_name="Aachen-Orsbach",
            latitude=50.7983,
            longitude=6.0244,
            elevation_m=553.0,
            state="Nordrhein-Westfalen",
            start_date=date(2000, 1, 1),
            end_date=None,
            is_active=True,
            last_updated=datetime.utcnow()
        ),
        StationMetadata(
            station_id=1001,
            station_name="Berlin-Tempelhof",
            latitude=52.4675,
            longitude=13.4021,
            elevation_m=48.0,
            state="Berlin",
            start_date=date(2000, 1, 1),
            end_date=None,
            is_active=True,
            last_updated=datetime.utcnow()
        ),
        StationMetadata(
            station_id=1002,
            station_name="München-Stadt",
            latitude=48.1351,
            longitude=11.5820,
            elevation_m=515.0,
            state="Bayern",
            start_date=date(2000, 1, 1),
            end_date=date(2020, 12, 31),
            is_active=False,
            last_updated=datetime.utcnow()
        ),
    ]
    
    for station in stations:
        test_db.add(station)
    
    test_db.commit()
    
    return stations


@pytest.fixture
def sample_temperature_features(test_db, sample_stations):
    """Create sample temperature features."""
    features = [
        QuarterlyTemperatureFeatures(
            station_id=433,
            station_name="Aachen-Orsbach",
            latitude=50.7983,
            longitude=6.0244,
            elevation_m=553.0,
            year=2023,
            quarter=1,
            quarter_start=datetime(2023, 1, 1),
            quarter_end=datetime(2023, 3, 31, 23, 59, 59),
            dataset_version="2023Q1_v1",
            computed_at=datetime.utcnow(),
            mean_temp_c=5.2,
            median_temp_c=5.0,
            min_temp_c=-8.3,
            max_temp_c=18.7,
            stddev_temp_c=4.5,
            q25_temp_c=2.1,
            q75_temp_c=8.3,
            heating_degree_days=850.0,
            cooling_degree_days=0.0,
            frost_hours=320,
            freeze_thaw_cycles=15,
            count_observations=2160,
            count_missing=24,
            missingness_ratio=0.011
        ),
        QuarterlyTemperatureFeatures(
            station_id=433,
            station_name="Aachen-Orsbach",
            latitude=50.7983,
            longitude=6.0244,
            elevation_m=553.0,
            year=2023,
            quarter=2,
            quarter_start=datetime(2023, 4, 1),
            quarter_end=datetime(2023, 6, 30, 23, 59, 59),
            dataset_version="2023Q2_v1",
            computed_at=datetime.utcnow(),
            mean_temp_c=15.8,
            median_temp_c=16.2,
            min_temp_c=2.1,
            max_temp_c=28.9,
            stddev_temp_c=5.2,
            q25_temp_c=12.0,
            q75_temp_c=19.5,
            heating_degree_days=45.0,
            cooling_degree_days=120.0,
            frost_hours=0,
            freeze_thaw_cycles=0,
            count_observations=2184,
            count_missing=8,
            missingness_ratio=0.004
        ),
    ]
    
    for feature in features:
        test_db.add(feature)
    
    test_db.commit()
    
    return features


@pytest.fixture
def sample_precipitation_features(test_db, sample_stations):
    """Create sample precipitation features."""
    features = [
        QuarterlyPrecipitationFeatures(
            station_id=433,
            station_name="Aachen-Orsbach",
            latitude=50.7983,
            longitude=6.0244,
            elevation_m=553.0,
            year=2023,
            quarter=1,
            quarter_start=datetime(2023, 1, 1),
            quarter_end=datetime(2023, 3, 31, 23, 59, 59),
            dataset_version="2023Q1_v1",
            computed_at=datetime.utcnow(),
            total_precip_mm=185.5,
            mean_hourly_precip_mm=0.086,
            median_precip_mm=0.0,
            max_hourly_precip_mm=8.3,
            stddev_precip_mm=0.45,
            q75_precip_mm=0.0,
            q95_precip_mm=1.2,
            wet_hours=420,
            dry_hours=1740,
            max_dry_spell_hours=72,
            max_wet_spell_hours=18,
            heavy_precip_hours=12,
            count_observations=2160,
            count_missing=24,
            missingness_ratio=0.011
        ),
    ]
    
    for feature in features:
        test_db.add(feature)
    
    test_db.commit()
    
    return features
