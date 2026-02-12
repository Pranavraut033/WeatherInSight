"""Unit tests for schema registry."""
import pytest
import json
from datetime import datetime
from schema_registry import SchemaRegistry


@pytest.fixture
def schema_registry(postgres_dsn):
    """Create schema registry instance."""
    return SchemaRegistry(postgres_dsn)


@pytest.fixture
def sample_schema():
    """Sample schema definition."""
    return {
        "name": "test_schema",
        "type": "record",
        "fields": {
            "id": {"type": "integer", "required": True},
            "name": {"type": "string", "required": True},
            "value": {"type": "float", "required": False, "default": 0.0}
        }
    }


def test_register_schema(schema_registry, sample_schema):
    """Test schema registration."""
    version = schema_registry.register_schema(
        schema_name="test_raw_data",
        schema_def=sample_schema,
        description="Test schema",
        created_by="test"
    )
    
    assert version == 1


def test_register_duplicate_schema(schema_registry, sample_schema):
    """Test registering identical schema returns same version."""
    v1 = schema_registry.register_schema(
        schema_name="test_dup",
        schema_def=sample_schema
    )
    
    v2 = schema_registry.register_schema(
        schema_name="test_dup",
        schema_def=sample_schema
    )
    
    assert v1 == v2


def test_get_schema(schema_registry, sample_schema):
    """Test retrieving schema."""
    version = schema_registry.register_schema(
        schema_name="test_get",
        schema_def=sample_schema
    )
    
    retrieved = schema_registry.get_schema("test_get", version)
    
    assert retrieved is not None
    assert retrieved["version"] == version
    assert retrieved["schema_definition"] == sample_schema


def test_get_latest_schema(schema_registry, sample_schema):
    """Test retrieving latest schema version."""
    schema_registry.register_schema("test_latest", sample_schema)
    
    # Modify and register v2
    modified = sample_schema.copy()
    modified["fields"]["extra"] = {"type": "string", "required": False}
    schema_registry.register_schema("test_latest", modified)
    
    latest = schema_registry.get_schema("test_latest")
    
    assert latest["version"] == 2
    assert "extra" in latest["schema_definition"]["fields"]


def test_backward_compatibility(schema_registry, sample_schema):
    """Test backward compatibility validation."""
    schema_registry.register_schema(
        "test_compat",
        sample_schema,
        compatibility_mode="BACKWARD"
    )
    
    # Try to remove required field (should fail)
    invalid = sample_schema.copy()
    invalid["fields"].pop("name")
    
    with pytest.raises(ValueError, match="BACKWARD incompatible"):
        schema_registry.register_schema(
            "test_compat",
            invalid,
            compatibility_mode="BACKWARD"
        )


def test_forward_compatibility(schema_registry, sample_schema):
    """Test forward compatibility validation."""
    schema_registry.register_schema(
        "test_forward",
        sample_schema,
        compatibility_mode="FORWARD"
    )
    
    # Add required field without default (should fail)
    invalid = sample_schema.copy()
    invalid["fields"]["new_required"] = {"type": "string", "required": True}
    
    with pytest.raises(ValueError, match="FORWARD incompatible"):
        schema_registry.register_schema(
            "test_forward",
            invalid,
            compatibility_mode="FORWARD"
        )


def test_list_schemas(schema_registry, sample_schema):
    """Test listing schemas."""
    schema_registry.register_schema("test_list_1", sample_schema)
    schema_registry.register_schema("test_list_2", sample_schema)
    
    schemas = schema_registry.list_schemas()
    
    schema_names = [s["schema_name"] for s in schemas]
    assert "test_list_1" in schema_names
    assert "test_list_2" in schema_names


def test_schema_history(schema_registry, sample_schema):
    """Test schema version history."""
    schema_registry.register_schema("test_history", sample_schema)
    
    modified = sample_schema.copy()
    modified["fields"]["extra"] = {"type": "string", "required": False}
    schema_registry.register_schema("test_history", modified)
    
    history = schema_registry.get_schema_history("test_history")
    
    assert len(history) == 2
    assert history[0]["version"] == 1
    assert history[1]["version"] == 2


def test_deactivate_schema(schema_registry, sample_schema):
    """Test deactivating schema version."""
    version = schema_registry.register_schema(
        "test_deactivate",
        sample_schema
    )
    
    schema_registry.deactivate_schema("test_deactivate", version)
    
    history = schema_registry.get_schema_history("test_deactivate")
    assert not history[0]["is_active"]
