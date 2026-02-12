"""Configuration for metadata service."""
import os
from dataclasses import dataclass


@dataclass
class Config:
    """Metadata service configuration."""
    
    # PostgreSQL connection
    postgres_host: str = os.getenv("POSTGRES_HOST", "localhost")
    postgres_port: int = int(os.getenv("POSTGRES_PORT", "5432"))
    postgres_db: str = os.getenv("POSTGRES_DB", "weatherinsight")
    postgres_user: str = os.getenv("POSTGRES_USER", "weatherinsight")
    postgres_password: str = os.getenv("POSTGRES_PASSWORD", "")
    
    @property
    def postgres_dsn(self) -> str:
        """Build PostgreSQL connection string."""
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


def get_config() -> Config:
    """Get configuration instance."""
    return Config()
