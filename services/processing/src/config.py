"""
Configuration for processing service
"""
import os
from typing import Optional
from pydantic_settings import BaseSettings


class ProcessingConfig(BaseSettings):
    """Processing service configuration"""
    
    # MinIO/S3 configuration
    s3_endpoint: str = os.getenv("MINIO_ENDPOINT", "http://minio:9000")
    s3_access_key: str = os.getenv("MINIO_ROOT_USER", "minioadmin")
    s3_secret_key: str = os.getenv("MINIO_ROOT_PASSWORD", "minioadmin123")
    raw_bucket: str = os.getenv("RAW_BUCKET", "weatherinsight-raw")
    staging_bucket: str = os.getenv("STAGING_BUCKET", "weatherinsight-staging")
    
    # PostgreSQL configuration
    postgres_host: str = os.getenv("POSTGRES_HOST", "postgres")
    postgres_port: int = int(os.getenv("POSTGRES_PORT", "5432"))
    postgres_db: str = os.getenv("POSTGRES_DB", "weatherinsight")
    postgres_user: str = os.getenv("POSTGRES_USER", "weatherinsight")
    postgres_password: str = os.getenv("POSTGRES_PASSWORD", "weatherinsight123")
    
    # Processing configuration
    spark_app_name: str = "WeatherInsight-Processing"
    spark_master: Optional[str] = os.getenv("SPARK_MASTER", None)  # None = local mode
    
    # Data quality thresholds
    max_missing_ratio: float = 0.5  # Flag if >50% missing
    quality_flag_threshold: int = 5  # Only use QN >= 5
    
    @property
    def postgres_url(self) -> str:
        """Build PostgreSQL connection URL"""
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


def get_config() -> ProcessingConfig:
    """Get processing configuration instance"""
    return ProcessingConfig()
