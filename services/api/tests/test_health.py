"""Tests for health check endpoint."""

import pytest
from fastapi import status


def test_health_check(client):
    """Test health check endpoint returns healthy status."""
    response = client.get("/health")
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    
    assert data["status"] == "healthy"
    assert "database" in data
    assert "message" in data


def test_root_endpoint(client):
    """Test root endpoint returns API information."""
    response = client.get("/")
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    
    assert data["service"] == "WeatherInsight API"
    assert data["version"] == "1.0.0"
    assert "/docs" in data["documentation"]
    assert "/health" in data["health_check"]


def test_api_info_endpoint(client):
    """Test API info endpoint returns configuration."""
    response = client.get("/api/v1/info")
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    
    assert "api" in data
    assert "endpoints" in data
    assert "products" in data
    assert "pagination" in data
    
    # Check product types
    assert "temperature" in data["products"]
    assert "precipitation" in data["products"]
    assert "wind" in data["products"]
    assert "pressure" in data["products"]
    assert "humidity" in data["products"]


def test_metrics_endpoint(client):
    """Test Prometheus metrics endpoint."""
    response = client.get("/metrics")
    
    assert response.status_code == status.HTTP_200_OK
    assert "text/plain" in response.headers["content-type"]
    
    # Check for some expected metrics
    content = response.text
    assert "weatherinsight_api_requests_total" in content or "python_" in content
