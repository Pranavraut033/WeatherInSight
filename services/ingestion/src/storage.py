"""MinIO storage manager for raw zone uploads."""
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from minio import Minio
from minio.error import S3Error

from .config import MinIOConfig

logger = logging.getLogger(__name__)


class RawZoneStorage:
    """Manages uploads to MinIO raw zone."""

    def __init__(self, config: MinIOConfig):
        """Initialize storage manager.

        Args:
            config: MinIO configuration
        """
        self.config = config
        self.client = Minio(
            config.endpoint,
            access_key=config.access_key,
            secret_key=config.secret_key,
            secure=config.secure,
        )
        self._ensure_bucket_exists()

    def _ensure_bucket_exists(self):
        """Create bucket if it doesn't exist."""
        try:
            if not self.client.bucket_exists(self.config.bucket_name):
                self.client.make_bucket(self.config.bucket_name)
                logger.info(f"Created bucket: {self.config.bucket_name}")
            else:
                logger.debug(f"Bucket already exists: {self.config.bucket_name}")
        except S3Error as e:
            logger.error(f"Failed to ensure bucket exists: {e}")
            raise

    def build_object_path(
        self,
        variable: str,
        station_id: str,
        year: str,
        filename: str,
    ) -> str:
        """Build object path following raw zone layout convention.

        Args:
            variable: Variable name (e.g., 'air_temperature')
            station_id: Station ID (5 digits)
            year: Year (4 digits)
            filename: Original DWD filename

        Returns:
            Object path string

        Example:
            raw/dwd/air_temperature/station_00433/2023/stundenwerte_TU_00433_20230101_20231231_hist.zip
        """
        # Ensure station_id is zero-padded to 5 digits
        station_id_padded = station_id.zfill(5)
        station_prefix = f"station_{station_id_padded}"
        
        return f"raw/dwd/{variable}/{station_prefix}/{year}/{filename}"

    def upload_file(
        self,
        local_path: Path,
        variable: str,
        station_id: str,
        year: str,
        metadata: Optional[Dict[str, str]] = None,
    ) -> str:
        """Upload a file to MinIO raw zone.

        Args:
            local_path: Local file path
            variable: Variable name
            station_id: Station ID
            year: Data year
            metadata: Optional object metadata

        Returns:
            Object path in MinIO

        Raises:
            S3Error: If upload fails
        """
        filename = local_path.name
        object_path = self.build_object_path(variable, station_id, year, filename)
        
        # Prepare metadata
        obj_metadata = {
            "ingest_timestamp": datetime.utcnow().isoformat(),
            "variable": variable,
            "station_id": station_id,
            "year": year,
            "filename": filename,
        }
        
        if metadata:
            obj_metadata.update(metadata)
        
        logger.info(f"Uploading {local_path} to {object_path}")
        
        try:
            self.client.fput_object(
                bucket_name=self.config.bucket_name,
                object_name=object_path,
                file_path=str(local_path),
                metadata=obj_metadata,
            )
            logger.info(f"Successfully uploaded to {object_path}")
            return object_path
            
        except S3Error as e:
            logger.error(f"Failed to upload {local_path}: {e}")
            raise

    def object_exists(self, object_path: str) -> bool:
        """Check if an object exists in MinIO.

        Args:
            object_path: Object path to check

        Returns:
            True if object exists, False otherwise
        """
        try:
            self.client.stat_object(self.config.bucket_name, object_path)
            return True
        except S3Error as e:
            if e.code == "NoSuchKey":
                return False
            raise

    def get_object_metadata(self, object_path: str) -> Optional[Dict[str, str]]:
        """Get metadata for an object.

        Args:
            object_path: Object path

        Returns:
            Metadata dictionary or None if object doesn't exist
        """
        try:
            stat = self.client.stat_object(self.config.bucket_name, object_path)
            return stat.metadata
        except S3Error as e:
            if e.code == "NoSuchKey":
                return None
            raise

    def list_objects(self, prefix: str) -> list:
        """List objects with a given prefix.

        Args:
            prefix: Object path prefix

        Returns:
            List of object names
        """
        try:
            objects = self.client.list_objects(
                self.config.bucket_name,
                prefix=prefix,
                recursive=True,
            )
            return [obj.object_name for obj in objects]
        except S3Error as e:
            logger.error(f"Failed to list objects with prefix {prefix}: {e}")
            raise

    def upload_checksum_file(
        self,
        checksum: str,
        variable: str,
        station_id: str,
        year: str,
        filename: str,
    ) -> str:
        """Upload a checksum file to accompany a data file.

        Args:
            checksum: Checksum value (SHA256 hex)
            variable: Variable name
            station_id: Station ID
            year: Data year
            filename: Original data filename

        Returns:
            Object path of checksum file
        """
        checksum_filename = f"{filename}.sha256"
        object_path = self.build_object_path(variable, station_id, year, checksum_filename)
        
        # Create checksum content
        checksum_content = f"{checksum}  {filename}\n"
        
        logger.info(f"Uploading checksum to {object_path}")
        
        try:
            from io import BytesIO
            data = BytesIO(checksum_content.encode('utf-8'))
            
            self.client.put_object(
                bucket_name=self.config.bucket_name,
                object_name=object_path,
                data=data,
                length=len(checksum_content),
                content_type="text/plain",
            )
            logger.info(f"Successfully uploaded checksum to {object_path}")
            return object_path
            
        except S3Error as e:
            logger.error(f"Failed to upload checksum: {e}")
            raise
