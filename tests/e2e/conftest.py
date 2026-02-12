"""
Pytest fixtures for end-to-end tests.

Provides fixtures for:
- Docker Compose stack management
- Sample DWD data generation
- Database seeding
- Service health checking
"""

import os
import time
import pytest
import subprocess
import psycopg2
import requests
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List


# Test configuration
TEST_DATA_DIR = Path(__file__).parent / "test_data"
DOCKER_COMPOSE_FILE = Path(__file__).parent.parent.parent / "docker-compose.yml"
PROJECT_ROOT = Path(__file__).parent.parent.parent


@pytest.fixture(scope="session")
def docker_compose():
    """
    Manage Docker Compose stack for E2E tests.
    
    Starts services, waits for health checks, yields for tests,
    then provides option to keep running or tear down.
    """
    # Check if services are already running
    result = subprocess.run(
        ["docker", "compose", "-f", str(DOCKER_COMPOSE_FILE), "ps", "-q"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True
    )
    
    services_running = bool(result.stdout.strip())
    
    if not services_running:
        print("\n🚀 Starting Docker Compose stack...")
        subprocess.run(
            ["docker", "compose", "-f", str(DOCKER_COMPOSE_FILE), "up", "-d"],
            cwd=PROJECT_ROOT,
            check=True
        )
        time.sleep(10)  # Initial startup delay
    else:
        print("\n✓ Docker Compose stack already running")
    
    # Wait for services to be healthy
    wait_for_services()
    
    yield
    
    # Optionally tear down (controlled by env var)
    if os.environ.get("E2E_TEARDOWN", "false").lower() == "true":
        print("\n🧹 Tearing down Docker Compose stack...")
        subprocess.run(
            ["docker", "compose", "-f", str(DOCKER_COMPOSE_FILE), "down", "-v"],
            cwd=PROJECT_ROOT
        )


def wait_for_services(timeout: int = 180):
    """Wait for all critical services to be healthy."""
    services = {
        "postgres": ("localhost", 5432, check_postgres),
        "minio": ("http://localhost:9000/minio/health/live", None, check_http),
        "api": ("http://localhost:8000/health", None, check_http),
        "prometheus": ("http://localhost:9090/-/healthy", None, check_http),
        "grafana": ("http://localhost:3002/api/health", None, check_http),
    }
    
    print("\n⏳ Waiting for services to be healthy...")
    start_time = time.time()
    
    for service_name, check_args in services.items():
        if isinstance(check_args[0], str) and check_args[0].startswith("http"):
            # HTTP check
            url = check_args[0]
            check_func = check_args[2]
            
            while time.time() - start_time < timeout:
                try:
                    if check_func(url):
                        print(f"  ✓ {service_name} is healthy")
                        break
                except Exception:
                    pass
                time.sleep(2)
            else:
                raise TimeoutError(f"{service_name} did not become healthy within {timeout}s")
        else:
            # Custom check
            host, port, check_func = check_args
            
            while time.time() - start_time < timeout:
                try:
                    if check_func(host, port):
                        print(f"  ✓ {service_name} is healthy")
                        break
                except Exception:
                    pass
                time.sleep(2)
            else:
                raise TimeoutError(f"{service_name} did not become healthy within {timeout}s")


def check_postgres(host: str, port: int) -> bool:
    """Check if PostgreSQL is accepting connections."""
    try:
        conn = psycopg2.connect(
            host=host,
            port=port,
            user="weatherinsight",
            password="weatherinsight123",
            database="weatherinsight",
            connect_timeout=3
        )
        conn.close()
        return True
    except Exception:
        return False


def check_http(url: str) -> bool:
    """Check if HTTP endpoint responds with 2xx status."""
    try:
        response = requests.get(url, timeout=3)
        return response.status_code < 300
    except Exception:
        return False


@pytest.fixture(scope="session")
def postgres_connection(docker_compose):
    """Provide PostgreSQL connection for tests."""
    conn = psycopg2.connect(
        host="localhost",
        port=5432,
        user="weatherinsight",
        password="weatherinsight123",
        database="weatherinsight"
    )
    yield conn
    conn.close()


@pytest.fixture
def clean_database(postgres_connection):
    """Clean feature tables before each test."""
    cursor = postgres_connection.cursor()
    
    tables = [
        "quarterly_temperature_features",
        "quarterly_precipitation_features",
        "quarterly_wind_features",
        "quarterly_pressure_features",
        "quarterly_humidity_features",
        "station_metadata"
    ]
    
    for table in tables:
        try:
            cursor.execute(f"TRUNCATE TABLE {table} CASCADE")
        except psycopg2.errors.UndefinedTable:
            pass  # Table doesn't exist yet
    
    postgres_connection.commit()
    yield
    postgres_connection.rollback()


@pytest.fixture(scope="session")
def sample_dwd_data() -> Dict[str, List[str]]:
    """
    Generate sample DWD hourly data for one week of 2023 Q1.
    
    Returns dict mapping product_type to list of file contents.
    """
    # Station 433 (Erfurt) - week of Jan 1-7, 2023
    start_date = datetime(2023, 1, 1)
    
    data = {
        "air_temperature": generate_temperature_data(start_date, 433, days=7),
        "precipitation": generate_precipitation_data(start_date, 433, days=7),
        "wind": generate_wind_data(start_date, 433, days=7),
        "pressure": generate_pressure_data(start_date, 433, days=7),
        "moisture": generate_moisture_data(start_date, 433, days=7),
    }
    
    return data


def generate_temperature_data(start_date: datetime, station_id: int, days: int) -> str:
    """Generate realistic temperature data."""
    lines = ["STATIONS_ID;MESS_DATUM;QN_9;TT_TU;RF_TU;eor"]
    
    for day in range(days):
        for hour in range(24):
            timestamp = start_date + timedelta(days=day, hours=hour)
            
            # Simulate winter temperature pattern (cold at night, warmer midday)
            base_temp = -2.0
            daily_variation = 5.0 * (0.5 - abs((hour - 12) / 24.0))
            temp = base_temp + daily_variation + (day * 0.3)  # Slight warming trend
            
            # Humidity inversely related to temperature
            humidity = max(70, min(95, int(85 - daily_variation * 2)))
            
            mess_datum = timestamp.strftime("%Y%m%d%H")
            lines.append(f"{station_id:05d};{mess_datum};10;{temp:.1f};{humidity};eor")
    
    return "\n".join(lines)


def generate_precipitation_data(start_date: datetime, station_id: int, days: int) -> str:
    """Generate realistic precipitation data."""
    lines = ["STATIONS_ID;MESS_DATUM;QN_8;R1;RS_IND;WRTR;eor"]
    
    for day in range(days):
        for hour in range(24):
            timestamp = start_date + timedelta(days=day, hours=hour)
            
            # Simulate occasional precipitation (20% of hours)
            if (day + hour) % 5 == 0:
                precip = 0.5 + (hour % 3) * 0.3
                rs_ind = 1  # Precipitation occurred
                wrtr = 6  # Rain
            else:
                precip = 0.0
                rs_ind = 0
                wrtr = 0
            
            mess_datum = timestamp.strftime("%Y%m%d%H")
            lines.append(f"{station_id:05d};{mess_datum};10;{precip:.1f};{rs_ind};{wrtr};eor")
    
    return "\n".join(lines)


def generate_wind_data(start_date: datetime, station_id: int, days: int) -> str:
    """Generate realistic wind data."""
    lines = ["STATIONS_ID;MESS_DATUM;QN_3;F;D;eor"]
    
    for day in range(days):
        for hour in range(24):
            timestamp = start_date + timedelta(days=day, hours=hour)
            
            # Simulate varying wind speed (higher during day)
            wind_speed = 2.0 + ((hour + day) % 12) * 0.4
            
            # Simulate prevailing westerly winds with variation
            wind_direction = 270 + ((hour * 15) % 90) - 45
            
            mess_datum = timestamp.strftime("%Y%m%d%H")
            lines.append(f"{station_id:05d};{mess_datum};10;{wind_speed:.1f};{wind_direction};eor")
    
    return "\n".join(lines)


def generate_pressure_data(start_date: datetime, station_id: int, days: int) -> str:
    """Generate realistic pressure data."""
    lines = ["STATIONS_ID;MESS_DATUM;QN_8;P;P0;eor"]
    
    for day in range(days):
        for hour in range(24):
            timestamp = start_date + timedelta(days=day, hours=hour)
            
            # Simulate pressure variation (typical high pressure system)
            base_pressure = 1015.0
            variation = 8.0 * (0.5 - abs((hour + day * 24 - 84) / 168.0))
            pressure = base_pressure + variation
            
            # Station pressure (slightly higher due to altitude)
            pressure_station = pressure + 3.5
            
            mess_datum = timestamp.strftime("%Y%m%d%H")
            lines.append(f"{station_id:05d};{mess_datum};10;{pressure:.1f};{pressure_station:.1f};eor")
    
    return "\n".join(lines)


def generate_moisture_data(start_date: datetime, station_id: int, days: int) -> str:
    """Generate realistic moisture data."""
    lines = ["STATIONS_ID;MESS_DATUM;QN_8;RF_TU;TD;eor"]
    
    for day in range(days):
        for hour in range(24):
            timestamp = start_date + timedelta(days=day, hours=hour)
            
            # Simulate humidity (higher at night)
            humidity = 75 + int(10 * (0.5 - abs((hour - 12) / 24.0)))
            
            # Dew point (related to humidity and temperature)
            dew_point = -5.0 + (humidity - 75) * 0.2
            
            mess_datum = timestamp.strftime("%Y%m%d%H")
            lines.append(f"{station_id:05d};{mess_datum};10;{humidity};{dew_point:.1f};eor")
    
    return "\n".join(lines)


@pytest.fixture
def api_client(docker_compose) -> str:
    """Provide API base URL for tests."""
    return "http://localhost:8000"


@pytest.fixture
def seed_station_metadata(postgres_connection, clean_database):
    """Seed station metadata for test station 433."""
    cursor = postgres_connection.cursor()
    
    cursor.execute("""
        INSERT INTO station_metadata (
            station_id, name, latitude, longitude, elevation_m,
            state, is_active, start_date, end_date
        ) VALUES (
            433, 'Erfurt-Weimar', 50.9803, 10.9586, 316,
            'Thüringen', true, '1950-01-01', NULL
        )
        ON CONFLICT (station_id) DO NOTHING
    """)
    
    postgres_connection.commit()
    
    yield
    
    postgres_connection.rollback()
