"""Main ingestion orchestrator."""
import logging
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import List, Optional

from .config import IngestionConfig
from .dwd_client import DWDClient
from .storage import RawZoneStorage
from .metadata import MetadataRegistry

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class IngestionOrchestrator:
    """Orchestrates the ingestion of DWD data to raw zone."""

    def __init__(self, config: IngestionConfig):
        """Initialize orchestrator.

        Args:
            config: Ingestion configuration
        """
        self.config = config
        self.dwd_client = DWDClient(config.dwd)
        self.storage = RawZoneStorage(config.minio)
        self.registry = MetadataRegistry(config.postgres)

    def ingest_variable(
        self,
        variable: str,
        station_ids: Optional[List[str]] = None,
        recent: bool = False,
        skip_existing: bool = True,
    ) -> dict:
        """Ingest data for a specific variable.

        Args:
            variable: Variable name (e.g., 'air_temperature')
            station_ids: Optional list of specific station IDs to ingest
            recent: If True, ingest recent data; otherwise historical
            skip_existing: If True, skip files that already exist in MinIO

        Returns:
            Dictionary with ingestion statistics
        """
        logger.info(f"Starting ingestion for variable: {variable}")
        
        # Create ingestion run record
        run_id = self.registry.create_ingestion_run(variable)
        
        try:
            # Get station list
            logger.info("Fetching station list from DWD")
            all_stations = self.dwd_client.list_stations(variable, recent=recent)
            
            # Filter by station IDs if provided
            if station_ids:
                stations = [s for s in all_stations if s['station_id'] in station_ids]
                logger.info(f"Filtered to {len(stations)} stations")
            else:
                stations = all_stations
            
            logger.info(f"Processing {len(stations)} stations")
            
            # Process each station
            stats = {
                'total_stations': len(stations),
                'processed': 0,
                'skipped': 0,
                'failed': 0,
                'total_bytes': 0,
            }
            
            with TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                
                for station_info in stations:
                    try:
                        result = self._ingest_station(
                            station_info,
                            variable,
                            temp_path,
                            skip_existing,
                        )
                        
                        if result['uploaded']:
                            stats['processed'] += 1
                            stats['total_bytes'] += result['file_size']
                        else:
                            stats['skipped'] += 1
                            
                    except Exception as e:
                        logger.error(f"Failed to ingest station {station_info['station_id']}: {e}")
                        stats['failed'] += 1
            
            # Update run record
            self.registry.update_ingestion_run(
                run_id=run_id,
                status="completed",
                station_count=stats['processed'],
                file_count=stats['processed'],
                total_bytes=stats['total_bytes'],
                notes=f"Processed: {stats['processed']}, Skipped: {stats['skipped']}, Failed: {stats['failed']}",
            )
            
            logger.info(f"Ingestion completed: {stats}")
            return stats
            
        except Exception as e:
            logger.error(f"Ingestion failed: {e}")
            self.registry.update_ingestion_run(
                run_id=run_id,
                status="failed",
                error_message=str(e),
            )
            raise

    def _ingest_station(
        self,
        station_info: dict,
        variable: str,
        temp_path: Path,
        skip_existing: bool,
    ) -> dict:
        """Ingest data for a single station.

        Args:
            station_info: Station information dictionary
            variable: Variable name
            temp_path: Temporary directory for downloads
            skip_existing: Whether to skip existing files

        Returns:
            Dictionary with ingestion result
        """
        station_id = station_info['station_id']
        filename = station_info['filename']
        
        # Extract year from filename
        # Format: stundenwerte_XX_SSSSS_YYYYMMDD_YYYYMMDD_hist.zip
        parts = filename.split('_')
        if len(parts) >= 4:
            year = parts[3][:4]  # Extract year from start date
        else:
            logger.warning(f"Could not extract year from filename: {filename}")
            year = "unknown"
        
        # Check if file already exists
        object_path = self.storage.build_object_path(variable, station_id, year, filename)
        
        if skip_existing and self.storage.object_exists(object_path):
            logger.info(f"Skipping existing file: {object_path}")
            return {'uploaded': False, 'file_size': 0}
        
        # Download file
        local_file = temp_path / filename
        downloaded_path, checksum = self.dwd_client.download_station_file(
            variable=variable,
            station_id=station_id,
            filename=filename,
            output_path=local_file,
            recent=False,
        )
        
        # Get file size
        file_size = downloaded_path.stat().st_size
        
        # Upload to MinIO
        metadata = {
            'source_url': f"{self.config.dwd.base_url}/{variable}/historical/{filename}",
            'checksum_sha256': checksum,
            'file_size_bytes': str(file_size),
        }
        
        self.storage.upload_file(
            local_path=downloaded_path,
            variable=variable,
            station_id=station_id,
            year=year,
            metadata=metadata,
        )
        
        # Upload checksum file
        self.storage.upload_checksum_file(
            checksum=checksum,
            variable=variable,
            station_id=station_id,
            year=year,
            filename=filename,
        )
        
        logger.info(f"Successfully ingested station {station_id}: {filename}")
        
        return {'uploaded': True, 'file_size': file_size}

    def ingest_all_variables(
        self,
        station_ids: Optional[List[str]] = None,
        skip_existing: bool = True,
    ) -> dict:
        """Ingest data for all supported variables.

        Args:
            station_ids: Optional list of specific station IDs
            skip_existing: Whether to skip existing files

        Returns:
            Dictionary with ingestion statistics per variable
        """
        variables = list(DWDClient.VARIABLE_MAPPING.keys())
        results = {}
        
        for variable in variables:
            try:
                logger.info(f"Ingesting variable: {variable}")
                stats = self.ingest_variable(
                    variable=variable,
                    station_ids=station_ids,
                    recent=False,
                    skip_existing=skip_existing,
                )
                results[variable] = stats
            except Exception as e:
                logger.error(f"Failed to ingest variable {variable}: {e}")
                results[variable] = {'error': str(e)}
        
        return results

    def close(self):
        """Close all connections."""
        self.dwd_client.close()
        self.registry.close()
