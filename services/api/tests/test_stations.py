"""Tests for station endpoints."""

import pytest
from fastapi import status


def test_list_stations_empty(client):
    """Test listing stations when database is empty."""
    response = client.get("/api/v1/stations")
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    
    assert data["total"] == 0
    assert data["limit"] == 50
    assert data["offset"] == 0
    assert len(data["items"]) == 0


def test_list_stations(client, sample_stations):
    """Test listing all stations."""
    response = client.get("/api/v1/stations")
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    
    assert data["total"] == 3
    assert len(data["items"]) == 3
    
    # Check first station
    station = data["items"][0]
    assert station["station_id"] == 433
    assert station["station_name"] == "Aachen-Orsbach"
    assert station["latitude"] == pytest.approx(50.7983)
    assert station["longitude"] == pytest.approx(6.0244)
    assert station["elevation_m"] == pytest.approx(553.0)
    assert station["state"] == "Nordrhein-Westfalen"
    assert station["is_active"] is True


def test_list_stations_pagination(client, sample_stations):
    """Test station list pagination."""
    # First page
    response = client.get("/api/v1/stations?limit=2&offset=0")
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    
    assert data["total"] == 3
    assert data["limit"] == 2
    assert data["offset"] == 0
    assert len(data["items"]) == 2
    
    # Second page
    response = client.get("/api/v1/stations?limit=2&offset=2")
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    
    assert data["total"] == 3
    assert data["limit"] == 2
    assert data["offset"] == 2
    assert len(data["items"]) == 1


def test_list_stations_filter_active(client, sample_stations):
    """Test filtering stations by active status."""
    response = client.get("/api/v1/stations?is_active=true")
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    
    assert data["total"] == 2
    assert all(item["is_active"] for item in data["items"])
    
    # Test inactive filter
    response = client.get("/api/v1/stations?is_active=false")
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    
    assert data["total"] == 1
    assert not data["items"][0]["is_active"]


def test_list_stations_filter_state(client, sample_stations):
    """Test filtering stations by state."""
    response = client.get("/api/v1/stations?state=Berlin")
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    
    assert data["total"] == 1
    assert data["items"][0]["station_name"] == "Berlin-Tempelhof"
    assert data["items"][0]["state"] == "Berlin"


def test_get_station_by_id(client, sample_stations):
    """Test getting a specific station by ID."""
    response = client.get("/api/v1/stations/433")
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    
    assert data["station_id"] == 433
    assert data["station_name"] == "Aachen-Orsbach"
    assert data["latitude"] == pytest.approx(50.7983)
    assert data["elevation_m"] == pytest.approx(553.0)


def test_get_station_not_found(client, sample_stations):
    """Test getting a non-existent station."""
    response = client.get("/api/v1/stations/99999")
    
    assert response.status_code == status.HTTP_404_NOT_FOUND
    data = response.json()
    
    assert "not found" in data["detail"].lower()


def test_get_station_summary(client, sample_stations, sample_temperature_features):
    """Test getting station summary with product counts."""
    response = client.get("/api/v1/stations/433/summary")
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    
    assert data["station_id"] == 433
    assert data["station_name"] == "Aachen-Orsbach"
    
    assert "location" in data
    assert data["location"]["latitude"] == pytest.approx(50.7983)
    assert data["location"]["state"] == "Nordrhein-Westfalen"
    
    assert "operational_period" in data
    assert data["operational_period"]["is_active"] is True
    
    assert "available_products" in data
    assert data["available_products"]["temperature"] == 2
    
    assert data["total_records"] >= 2


def test_get_station_summary_not_found(client):
    """Test getting summary for non-existent station."""
    response = client.get("/api/v1/stations/99999/summary")
    
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_list_stations_pagination_limits(client, sample_stations):
    """Test pagination parameter validation."""
    # Test invalid limit (too large)
    response = client.get("/api/v1/stations?limit=2000")
    
    # Should use max limit or return validation error
    assert response.status_code in [status.HTTP_200_OK, status.HTTP_422_UNPROCESSABLE_ENTITY]
    
    # Test invalid offset (negative)
    response = client.get("/api/v1/stations?offset=-1")
    
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
