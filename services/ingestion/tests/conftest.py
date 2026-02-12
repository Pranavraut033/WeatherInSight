"""Test configuration for pytest."""
import pytest


def pytest_configure(config):
    """Configure pytest markers."""
    config.addinivalue_line(
        "markers", "integration: mark test as integration test (requires running services)"
    )
