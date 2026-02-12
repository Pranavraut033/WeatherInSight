"""Configuration management for ingestion service."""
import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class DWDConfig:
    """DWD Open Data configuration."""
    base_url: str = "https://opendata.dwd.de/climate_environment/CDC/observations_germany/climate/hourly"
    timeout: int = 30
    max_retries: int = 3
    retry_delay: int = 5


@dataclass
class MinIOConfig:
    """MinIO configuration."""
    endpoint: str
    access_key: str
    secret_key: str
    bucket_name: str = "weatherinsight-raw"
    secure: bool = False

    @classmethod
    def from_env(cls) -> "MinIOConfig":
        """Load MinIO config from environment variables."""
        return cls(
            endpoint=os.getenv("MINIO_ENDPOINT", "localhost:9000"),
            access_key=os.getenv("MINIO_ROOT_USER", "minioadmin"),
            secret_key=os.getenv("MINIO_ROOT_PASSWORD", "minioadmin123"),
            bucket_name=os.getenv("MINIO_BUCKET", "weatherinsight-raw"),
            secure=os.getenv("MINIO_SECURE", "false").lower() == "true",
        )


@dataclass
class PostgresConfig:
    """PostgreSQL configuration."""
    host: str
    port: int
    database: str
    user: str
    password: str

    @classmethod
    def from_env(cls) -> "PostgresConfig":
        """Load PostgreSQL config from environment variables."""
        return cls(
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=int(os.getenv("POSTGRES_PORT", "5432")),
            database=os.getenv("POSTGRES_DB", "weatherinsight"),
            user=os.getenv("POSTGRES_USER", "weatherinsight"),
            password=os.getenv("POSTGRES_PASSWORD", "weatherinsight"),
        )

    @property
    def connection_string(self) -> str:
        """Get SQLAlchemy connection string."""
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"


@dataclass
class IngestionConfig:
    """Main ingestion configuration."""
    dwd: DWDConfig
    minio: MinIOConfig
    postgres: PostgresConfig
    dataset_version: Optional[str] = None

    @classmethod
    def from_env(cls) -> "IngestionConfig":
        """Load full configuration from environment."""
        return cls(
            dwd=DWDConfig(),
            minio=MinIOConfig.from_env(),
            postgres=PostgresConfig.from_env(),
            dataset_version=os.getenv("DATASET_VERSION"),
        )
