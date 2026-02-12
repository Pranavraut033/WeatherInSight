"""Tests for feature endpoints."""

import pytest
from fastapi import status


def test_list_products(client):
    """Test listing available product types."""
    response = client.get("/api/v1/features/products")
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    
    assert "products" in data
    assert "total_products" in data
    assert data["total_products"] == 5


def test_get_product_stats_temperature(client, sample_temperature_features):
    """Test getting statistics for temperature product."""
    response = client.get("/api/v1/features/temperature/stats")
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    
    assert data["product"] == "temperature"
    assert data["total_records"] == 2
    assert data["station_count"] == 1
    assert data["min_year"] == 2023
    assert data["max_year"] == 2023


def test_get_product_stats_invalid(client):
    """Test getting stats for invalid product type."""
    response = client.get("/api/v1/features/invalid_product/stats")
    
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_list_temperature_features(client, sample_temperature_features):
    """Test listing temperature features."""
    response = client.get("/api/v1/features/temperature")
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    
    assert data["total"] == 2
    assert len(data["items"]) == 2
    
    # Check feature structure
    feature = data["items"][0]
    assert "feature_id" in feature
    assert "station_id" in feature
    assert "year" in feature
    assert "quarter" in feature
    assert "mean_temp_c" in feature
    assert "heating_degree_days" in feature
    
    # Features should be ordered by date (newest first)
    assert data["items"][0]["year"] >= data["items"][1]["year"]


def test_list_features_filter_by_station(client, sample_temperature_features):
    """Test filtering features by station ID."""
    response = client.get("/api/v1/features/temperature?station_id=433")
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    
    assert data["total"] == 2
    assert all(item["station_id"] == 433 for item in data["items"])


def test_list_features_filter_by_year(client, sample_temperature_features):
    """Test filtering features by year."""
    response = client.get("/api/v1/features/temperature?year=2023")
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    
    assert data["total"] == 2
    assert all(item["year"] == 2023 for item in data["items"])


def test_list_features_filter_by_quarter(client, sample_temperature_features):
    """Test filtering features by quarter."""
    response = client.get("/api/v1/features/temperature?quarter=1")
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    
    assert data["total"] == 1
    assert data["items"][0]["quarter"] == 1
    assert data["items"][0]["mean_temp_c"] == pytest.approx(5.2)


def test_list_features_filter_by_year_range(client, sample_temperature_features):
    """Test filtering features by year range."""
    response = client.get("/api/v1/features/temperature?min_year=2023&max_year=2023")
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    
    assert data["total"] == 2


def test_list_features_invalid_quarter(client):
    """Test validation for invalid quarter value."""
    response = client.get("/api/v1/features/temperature?quarter=5")
    
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_list_features_pagination(client, sample_temperature_features):
    """Test pagination for features."""
    response = client.get("/api/v1/features/temperature?limit=1&offset=0")
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    
    assert data["total"] == 2
    assert data["limit"] == 1
    assert data["offset"] == 0
    assert len(data["items"]) == 1


def test_get_station_timeseries(client, sample_temperature_features):
    """Test getting time series for a specific station."""
    response = client.get("/api/v1/features/temperature/stations/433")
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    
    assert data["total"] == 2
    assert len(data["items"]) == 2
    
    # All items should be for the same station
    assert all(item["station_id"] == 433 for item in data["items"])
    
    # Should be ordered chronologically (oldest first for timeseries)
    assert data["items"][0]["year"] <= data["items"][1]["year"]
    if data["items"][0]["year"] == data["items"][1]["year"]:
        assert data["items"][0]["quarter"] <= data["items"][1]["quarter"]


def test_get_station_timeseries_not_found(client):
    """Test getting timeseries for station with no data."""
    response = client.get("/api/v1/features/temperature/stations/99999")
    
    assert response.status_code == status.HTTP_404_NOT_FOUND
    data = response.json()
    
    assert "not found" in data["detail"].lower() or "no" in data["detail"].lower()


def test_list_precipitation_features(client, sample_precipitation_features):
    """Test listing precipitation features."""
    response = client.get("/api/v1/features/precipitation")
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    
    assert data["total"] == 1
    assert len(data["items"]) == 1
    
    feature = data["items"][0]
    assert feature["total_precip_mm"] == pytest.approx(185.5)
    assert feature["wet_hours"] == 420
    assert feature["dry_hours"] == 1740


def test_list_features_invalid_product(client):
    """Test listing features for invalid product type."""
    response = client.get("/api/v1/features/invalid_product")
    
    # Should fail path validation
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_features_response_structure(client, sample_temperature_features):
    """Test that feature responses have all required fields."""
    response = client.get("/api/v1/features/temperature?station_id=433&quarter=1")
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    
    feature = data["items"][0]
    
    # Common fields
    assert "feature_id" in feature
    assert "station_id" in feature
    assert "station_name" in feature
    assert "latitude" in feature
    assert "longitude" in feature
    assert "elevation_m" in feature
    assert "year" in feature
    assert "quarter" in feature
    assert "quarter_start" in feature
    assert "quarter_end" in feature
    assert "dataset_version" in feature
    assert "computed_at" in feature
    
    # Temperature-specific fields
    assert "mean_temp_c" in feature
    assert "median_temp_c" in feature
    assert "min_temp_c" in feature
    assert "max_temp_c" in feature
    assert "heating_degree_days" in feature
    assert "cooling_degree_days" in feature
    assert "frost_hours" in feature
    assert "freeze_thaw_cycles" in feature
    assert "count_observations" in feature
    assert "count_missing" in feature
    assert "missingness_ratio" in feature


def test_combined_filters(client, sample_temperature_features):
    """Test combining multiple filters."""
    response = client.get(
        "/api/v1/features/temperature?station_id=433&year=2023&quarter=2"
    )
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    
    assert data["total"] == 1
    feature = data["items"][0]
    assert feature["station_id"] == 433
    assert feature["year"] == 2023
    assert feature["quarter"] == 2
    assert feature["mean_temp_c"] == pytest.approx(15.8)
