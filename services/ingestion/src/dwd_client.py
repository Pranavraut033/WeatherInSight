"""DWD Open Data client for fetching station observation data."""
import hashlib
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import DWDConfig

logger = logging.getLogger(__name__)


class DWDClient:
    """Client for interacting with DWD Open Data API."""

    # Variable to DWD product folder mapping
    VARIABLE_MAPPING = {
        "air_temperature": "air_temperature",
        "precipitation": "precipitation",
        "wind": "wind",
        "pressure": "pressure",
        "moisture": "moisture",
        "cloud_cover": "cloudiness",
        "solar": "solar",
    }

    # Product prefix patterns
    PRODUCT_PREFIXES = {
        "air_temperature": "stundenwerte_TU_",
        "precipitation": "stundenwerte_RR_",
        "wind": "stundenwerte_FF_",
        "pressure": "stundenwerte_P0_",
        "moisture": "stundenwerte_TF_",
        "cloud_cover": "stundenwerte_N_",
        "solar": "stundenwerte_ST_",
    }

    def __init__(self, config: DWDConfig):
        """Initialize DWD client.

        Args:
            config: DWD configuration
        """
        self.config = config
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        """Create requests session with retry logic."""
        session = requests.Session()
        retry_strategy = Retry(
            total=self.config.max_retries,
            backoff_factor=self.config.retry_delay,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "HEAD"],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def list_stations(self, variable: str, recent: bool = False) -> List[Dict[str, str]]:
        """Fetch list of available stations for a variable.

        Args:
            variable: Variable name (e.g., 'air_temperature')
            recent: If True, fetch recent data; otherwise historical

        Returns:
            List of station metadata dictionaries

        Raises:
            ValueError: If variable is not supported
            requests.HTTPError: If request fails
        """
        if variable not in self.VARIABLE_MAPPING:
            raise ValueError(f"Unsupported variable: {variable}")

        product_path = self.VARIABLE_MAPPING[variable]
        period = "recent" if recent else "historical"
        
        # Construct stations list URL
        url = f"{self.config.base_url}/{product_path}/{period}/"
        
        logger.info(f"Fetching station list from {url}")
        
        try:
            response = self.session.get(url, timeout=self.config.timeout)
            response.raise_for_status()
            
            # Parse HTML directory listing for station files
            stations = self._parse_station_list(response.text, variable)
            logger.info(f"Found {len(stations)} stations for {variable}")
            return stations
            
        except requests.RequestException as e:
            logger.error(f"Failed to fetch station list: {e}")
            raise

    def _parse_station_list(self, html: str, variable: str) -> List[Dict[str, str]]:
        """Parse HTML directory listing to extract station IDs and filenames.

        Args:
            html: HTML content from DWD directory
            variable: Variable name

        Returns:
            List of station info dictionaries
        """
        stations = []
        prefix = self.PRODUCT_PREFIXES.get(variable, "")
        
        # Simple parsing - look for .zip files with the product prefix
        for line in html.split('\n'):
            if prefix in line and '.zip"' in line:
                # Extract filename from href
                start = line.find('href="') + 6
                end = line.find('"', start)
                filename = line[start:end]
                
                if filename.endswith('.zip'):
                    # Extract station ID from filename
                    # Format: stundenwerte_XX_SSSSS_YYYYMMDD_YYYYMMDD_hist.zip
                    parts = filename.split('_')
                    if len(parts) >= 3:
                        station_id = parts[2]
                        stations.append({
                            'station_id': station_id,
                            'filename': filename,
                            'variable': variable,
                        })
        
        return stations

    def download_station_file(
        self,
        variable: str,
        station_id: str,
        filename: str,
        output_path: Path,
        recent: bool = False,
    ) -> Tuple[Path, Optional[str]]:
        """Download a station data file and its checksum.

        Args:
            variable: Variable name
            station_id: Station ID (5 digits)
            filename: DWD filename to download
            output_path: Local path to save file
            recent: If True, download from recent; otherwise historical

        Returns:
            Tuple of (downloaded_file_path, checksum_value)

        Raises:
            requests.HTTPError: If download fails
        """
        if variable not in self.VARIABLE_MAPPING:
            raise ValueError(f"Unsupported variable: {variable}")

        product_path = self.VARIABLE_MAPPING[variable]
        period = "recent" if recent else "historical"
        
        # Construct file URL
        file_url = f"{self.config.base_url}/{product_path}/{period}/{filename}"
        
        logger.info(f"Downloading {filename} from {file_url}")
        
        # Download data file
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            response = self.session.get(file_url, timeout=self.config.timeout, stream=True)
            response.raise_for_status()
            
            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            logger.info(f"Downloaded {filename} to {output_path}")
            
            # Calculate local checksum
            checksum = self._calculate_checksum(output_path)
            
            # Try to download checksum file (if available)
            checksum_remote = self._download_checksum(file_url)
            
            if checksum_remote and checksum != checksum_remote:
                logger.warning(f"Checksum mismatch for {filename}: local={checksum}, remote={checksum_remote}")
            
            return output_path, checksum
            
        except requests.RequestException as e:
            logger.error(f"Failed to download {filename}: {e}")
            raise

    def _calculate_checksum(self, file_path: Path, algorithm: str = "sha256") -> str:
        """Calculate file checksum.

        Args:
            file_path: Path to file
            algorithm: Hash algorithm (sha256 or md5)

        Returns:
            Hex digest of checksum
        """
        hash_obj = hashlib.new(algorithm)
        with open(file_path, 'rb') as f:
            while chunk := f.read(8192):
                hash_obj.update(chunk)
        return hash_obj.hexdigest()

    def _download_checksum(self, file_url: str) -> Optional[str]:
        """Try to download and parse checksum file.

        Args:
            file_url: URL of data file

        Returns:
            Checksum value if available, None otherwise
        """
        # Try both .sha256 and .md5 extensions
        for ext in ['.sha256', '.md5']:
            checksum_url = file_url + ext
            try:
                response = self.session.get(checksum_url, timeout=self.config.timeout)
                response.raise_for_status()
                
                # Parse checksum file (format: "hash filename")
                content = response.text.strip()
                if ' ' in content:
                    checksum = content.split()[0]
                else:
                    checksum = content
                
                return checksum
                
            except requests.RequestException:
                continue
        
        return None

    def get_station_metadata_url(self) -> str:
        """Get URL for station metadata file."""
        # Station metadata is typically in a separate location
        return "https://opendata.dwd.de/climate_environment/CDC/observations_germany/climate/hourly/air_temperature/historical/TU_Stundenwerte_Beschreibung_Stationen.txt"

    def download_station_metadata(self, output_path: Path) -> Path:
        """Download station metadata file.

        Args:
            output_path: Local path to save metadata

        Returns:
            Path to downloaded file

        Raises:
            requests.HTTPError: If download fails
        """
        url = self.get_station_metadata_url()
        logger.info(f"Downloading station metadata from {url}")
        
        try:
            response = self.session.get(url, timeout=self.config.timeout)
            response.raise_for_status()
            
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(response.text, encoding='latin-1')
            
            logger.info(f"Downloaded station metadata to {output_path}")
            return output_path
            
        except requests.RequestException as e:
            logger.error(f"Failed to download station metadata: {e}")
            raise

    def close(self):
        """Close the HTTP session."""
        self.session.close()
