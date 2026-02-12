"""Unit tests for MinIO storage."""
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from config import MinIOConfig
from storage import RawZoneStorage


@pytest.fixture
def minio_config():
    """Create MinIO configuration for testing."""
    return MinIOConfig(
        endpoint="localhost:9000",
        access_key="minioadmin",
        secret_key="minioadmin123",
        bucket_name="test-bucket",
    )


@pytest.fixture
def storage(minio_config):
    """Create storage manager for testing."""
    with patch('storage.Minio'):
        return RawZoneStorage(minio_config)


class TestRawZoneStorage:
    """Test raw zone storage functionality."""

    def test_init(self, storage):
        """Test storage initialization."""
        assert storage.config is not None
        assert storage.client is not None

    def test_build_object_path(self, storage):
        """Test object path construction."""
        path = storage.build_object_path(
            variable="air_temperature",
            station_id="433",
            year="2023",
            filename="stundenwerte_TU_00433_20230101_20231231_hist.zip",
        )
        
        expected = "raw/dwd/air_temperature/station_00433/2023/stundenwerte_TU_00433_20230101_20231231_hist.zip"
        assert path == expected

    def test_build_object_path_padding(self, storage):
        """Test station ID zero-padding."""
        path = storage.build_object_path(
            variable="precipitation",
            station_id="1",
            year="2023",
            filename="test.zip",
        )
        
        assert "station_00001" in path

    @patch('storage.datetime')
    def test_upload_file_metadata(self, mock_datetime, storage, tmp_path):
        """Test file upload with metadata."""
        # Create test file
        test_file = tmp_path / "test.zip"
        test_file.write_bytes(b"test data")
        
        # Mock datetime
        mock_now = Mock()
        mock_now.isoformat.return_value = "2024-01-01T00:00:00"
        mock_datetime.utcnow.return_value = mock_now
        
        # Mock MinIO client
        storage.client.fput_object = Mock()
        
        storage.upload_file(
            local_path=test_file,
            variable="wind",
            station_id="00164",
            year="2023",
        )
        
        # Verify upload was called
        storage.client.fput_object.assert_called_once()
        
        # Check metadata structure
        call_args = storage.client.fput_object.call_args
        metadata = call_args[1]['metadata']
        
        assert metadata['variable'] == "wind"
        assert metadata['station_id'] == "00164"
        assert metadata['year'] == "2023"
        assert 'ingest_timestamp' in metadata

    def test_object_exists(self, storage):
        """Test checking object existence."""
        storage.client.stat_object = Mock()
        
        result = storage.object_exists("test/path")
        
        assert result is True
        storage.client.stat_object.assert_called_once()

    def test_list_objects(self, storage):
        """Test listing objects with prefix."""
        # Mock objects
        mock_obj1 = Mock()
        mock_obj1.object_name = "raw/dwd/air_temperature/station_00001/2023/file1.zip"
        mock_obj2 = Mock()
        mock_obj2.object_name = "raw/dwd/air_temperature/station_00001/2023/file2.zip"
        
        storage.client.list_objects = Mock(return_value=[mock_obj1, mock_obj2])
        
        objects = storage.list_objects("raw/dwd/air_temperature")
        
        assert len(objects) == 2
        assert objects[0].endswith("file1.zip")
        assert objects[1].endswith("file2.zip")
