"""Unit tests for dataset versioning."""
import pytest
from datetime import datetime, date
from dataset_versioning import DatasetVersioning, DatasetStatus


@pytest.fixture
def dataset_versioning(postgres_dsn):
    """Create dataset versioning instance."""
    return DatasetVersioning(postgres_dsn)


def test_create_version(dataset_versioning):
    """Test creating dataset version."""
    version_id = dataset_versioning.create_version(
        dataset_name="test_dataset",
        version="v1",
        schema_name="test_schema",
        schema_version=1,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 3, 31),
        storage_location="s3://bucket/path",
        metadata={"source": "dwd"},
        created_by="test"
    )
    
    assert version_id > 0


def test_get_version(dataset_versioning):
    """Test retrieving dataset version."""
    version_id = dataset_versioning.create_version(
        dataset_name="test_get",
        version="v1"
    )
    
    retrieved = dataset_versioning.get_version("test_get", "v1")
    
    assert retrieved is not None
    assert retrieved["id"] == version_id
    assert retrieved["dataset_name"] == "test_get"


def test_get_latest_version(dataset_versioning):
    """Test retrieving latest version."""
    dataset_versioning.create_version("test_latest", "v1")
    dataset_versioning.create_version("test_latest", "v2")
    
    latest = dataset_versioning.get_version("test_latest")
    
    assert latest["version"] == "v2"


def test_update_version_status(dataset_versioning):
    """Test updating version status."""
    version_id = dataset_versioning.create_version(
        "test_status",
        "v1"
    )
    
    dataset_versioning.update_version_status(
        version_id=version_id,
        status=DatasetStatus.AVAILABLE,
        record_count=1000,
        file_count=10,
        total_size_bytes=1024000,
        quality_metrics={"completeness": 0.95}
    )
    
    version = dataset_versioning.get_version("test_status", "v1")
    
    assert version["status"] == "available"
    assert version["record_count"] == 1000
    assert version["file_count"] == 10
    assert version["total_size_bytes"] == 1024000
    assert version["quality_metrics"]["completeness"] == 0.95


def test_list_versions(dataset_versioning):
    """Test listing versions."""
    dataset_versioning.create_version("test_list_a", "v1")
    dataset_versioning.create_version("test_list_a", "v2")
    dataset_versioning.create_version("test_list_b", "v1")
    
    all_versions = dataset_versioning.list_versions()
    assert len(all_versions) >= 3
    
    filtered = dataset_versioning.list_versions(dataset_name="test_list_a")
    assert len(filtered) == 2


def test_add_lineage(dataset_versioning):
    """Test adding lineage relationship."""
    parent_id = dataset_versioning.create_version("parent_ds", "v1")
    child_id = dataset_versioning.create_version("child_ds", "v1")
    
    dataset_versioning.add_lineage(
        child_id=child_id,
        parent_id=parent_id,
        transformation_type="aggregation",
        transformation_metadata={"window": "quarterly"}
    )
    
    lineage = dataset_versioning.get_lineage(child_id, "upstream")
    
    assert len(lineage["parents"]) == 1
    assert lineage["parents"][0]["id"] == parent_id


def test_get_lineage_both_directions(dataset_versioning):
    """Test getting lineage in both directions."""
    parent_id = dataset_versioning.create_version("lineage_parent", "v1")
    child_id = dataset_versioning.create_version("lineage_child", "v1")
    
    dataset_versioning.add_lineage(child_id, parent_id, "transform")
    
    # Check from parent
    parent_lineage = dataset_versioning.get_lineage(parent_id, "downstream")
    assert len(parent_lineage["children"]) == 1
    
    # Check from child
    child_lineage = dataset_versioning.get_lineage(child_id, "upstream")
    assert len(child_lineage["parents"]) == 1


def test_add_quality_check(dataset_versioning):
    """Test adding quality check."""
    version_id = dataset_versioning.create_version("test_quality", "v1")
    
    dataset_versioning.add_quality_check(
        version_id=version_id,
        check_name="completeness_check",
        check_type="completeness",
        status="passed",
        result={"score": 0.98, "missing_count": 20}
    )
    
    checks = dataset_versioning.get_quality_checks(version_id)
    
    assert len(checks) == 1
    assert checks[0]["check_name"] == "completeness_check"
    assert checks[0]["status"] == "passed"
    assert checks[0]["result"]["score"] == 0.98


def test_multiple_quality_checks(dataset_versioning):
    """Test multiple quality checks."""
    version_id = dataset_versioning.create_version("test_multi_check", "v1")
    
    dataset_versioning.add_quality_check(
        version_id, "check1", "completeness", "passed"
    )
    dataset_versioning.add_quality_check(
        version_id, "check2", "accuracy", "failed",
        error_message="Threshold not met"
    )
    
    checks = dataset_versioning.get_quality_checks(version_id)
    
    assert len(checks) == 2
    assert checks[0]["check_name"] == "check2"  # Most recent first
    assert checks[1]["check_name"] == "check1"
