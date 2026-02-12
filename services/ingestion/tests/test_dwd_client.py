"""Unit tests for DWD client."""
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from config import DWDConfig
from dwd_client import DWDClient


@pytest.fixture
def dwd_config():
    """Create DWD configuration for testing."""
    return DWDConfig()


@pytest.fixture
def dwd_client(dwd_config):
    """Create DWD client for testing."""
    return DWDClient(dwd_config)


class TestDWDClient:
    """Test DWD client functionality."""

    def test_init(self, dwd_client):
        """Test client initialization."""
        assert dwd_client.config is not None
        assert dwd_client.session is not None

    def test_variable_mapping(self):
        """Test variable mapping exists."""
        assert "air_temperature" in DWDClient.VARIABLE_MAPPING
        assert "precipitation" in DWDClient.VARIABLE_MAPPING
        assert "wind" in DWDClient.VARIABLE_MAPPING

    def test_product_prefixes(self):
        """Test product prefix mapping."""
        assert DWDClient.PRODUCT_PREFIXES["air_temperature"] == "stundenwerte_TU_"
        assert DWDClient.PRODUCT_PREFIXES["precipitation"] == "stundenwerte_RR_"

    def test_parse_station_list(self, dwd_client):
        """Test parsing of HTML station list."""
        html_sample = '''
        <html>
        <a href="stundenwerte_TU_00001_19500101_20231231_hist.zip">file1</a>
        <a href="stundenwerte_TU_00002_19600101_20231231_hist.zip">file2</a>
        </html>
        '''
        
        stations = dwd_client._parse_station_list(html_sample, "air_temperature")
        
        assert len(stations) == 2
        assert stations[0]['station_id'] == '00001'
        assert stations[1]['station_id'] == '00002'
        assert stations[0]['filename'].endswith('.zip')

    @patch('dwd_client.hashlib')
    def test_calculate_checksum(self, mock_hashlib, dwd_client, tmp_path):
        """Test checksum calculation."""
        # Create test file
        test_file = tmp_path / "test.zip"
        test_file.write_bytes(b"test data")
        
        # Mock hash object
        mock_hash = MagicMock()
        mock_hash.hexdigest.return_value = "abcd1234"
        mock_hashlib.new.return_value = mock_hash
        
        checksum = dwd_client._calculate_checksum(test_file)
        
        assert checksum == "abcd1234"
        mock_hashlib.new.assert_called_once()

    def test_invalid_variable(self, dwd_client):
        """Test error handling for invalid variable."""
        with pytest.raises(ValueError):
            dwd_client.list_stations("invalid_variable")

    def test_station_metadata_url(self, dwd_client):
        """Test station metadata URL generation."""
        url = dwd_client.get_station_metadata_url()
        assert url.startswith("https://opendata.dwd.de")
        assert "Stationen" in url
