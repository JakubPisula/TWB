"""
Pytest configuration and shared fixtures for TWB test suite.
"""
import pytest
import json
import os


@pytest.fixture
def sample_config():
    """Load the example config for testing."""
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config.example.json')
    if not os.path.exists(config_path):
        # Fallback for different envs if needed
        return {}
    with open(config_path, 'r') as f:
        return json.load(f)


@pytest.fixture
def mock_village_data():
    """Return a minimal village data structure for testing."""
    return {
        "id": "12345",
        "name": "Test Village",
        "x": 500,
        "y": 500,
        "wood": 10000,
        "stone": 10000,
        "iron": 10000,
        "managed": True,
    }
