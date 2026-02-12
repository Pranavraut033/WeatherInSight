"""Configuration management for WeatherInsight API."""

import os
from typing import Optional
from pydantic_settings import BaseSettings


class APIConfig(BaseSettings):
    """API configuration with PostgreSQL connection settings."""
    
    # PostgreSQL connection
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_db: str = "weatherinsight"
    postgres_user: str = "weatherinsight"
    postgres_password: str = "weatherinsight123"
    
    # API settings
    api_title: str = "WeatherInsight API"
    api_version: str = "1.0.0"
    api_description: str = "REST API for accessing quarterly weather feature data from German DWD stations"
    
    # CORS settings
    cors_origins: list[str] = ["*"]
    cors_allow_credentials: bool = True
    cors_allow_methods: list[str] = ["*"]
    cors_allow_headers: list[str] = ["*"]
    
    # Pagination defaults
    default_page_size: int = 50
    max_page_size: int = 1000
    
    # Database connection pool
    pool_size: int = 10
    max_overflow: int = 20
    pool_timeout: int = 30
    pool_recycle: int = 3600
    
    # Logging
    log_level: str = "INFO"
    
    @property
    def postgres_url(self) -> str:
        """Construct PostgreSQL connection URL."""
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )
    
    @property
    def postgres_url_async(self) -> str:
        """Construct async PostgreSQL connection URL."""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# Global config instance
_config: Optional[APIConfig] = None


def get_config() -> APIConfig:
    """Get or create global configuration instance."""
    global _config
    if _config is None:
        _config = APIConfig()
    return _config
