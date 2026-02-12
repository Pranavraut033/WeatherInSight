"""
Configuration management for the aggregation service.
"""
from pydantic_settings import BaseSettings


class AggregationConfig(BaseSettings):
    """Configuration for aggregation service."""
    
    # S3/MinIO configuration
    s3_endpoint: str = "http://minio:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin123"
    staging_bucket: str = "weatherinsight-staging"
    
    # PostgreSQL configuration
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_db: str = "weatherinsight"
    postgres_user: str = "weatherinsight"
    postgres_password: str = "weatherinsight123"
    
    # Spark configuration
    spark_app_name: str = "WeatherInsight-Aggregation"
    spark_master: str = "local[*]"
    
    # Processing configuration
    repartition_count: int = 10
    broadcast_threshold_mb: int = 10
    
    class Config:
        env_file = ".env"
        env_prefix = ""
    
    @property
    def postgres_url(self) -> str:
        """PostgreSQL connection URL for psycopg2."""
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )
    
    @property
    def postgres_jdbc_url(self) -> str:
        """JDBC connection URL for Spark."""
        return (
            f"jdbc:postgresql://{self.postgres_host}:{self.postgres_port}"
            f"/{self.postgres_db}"
        )
    
    @property
    def jdbc_properties(self) -> dict:
        """JDBC connection properties for Spark DataFrame writes."""
        return {
            "user": self.postgres_user,
            "password": self.postgres_password,
            "driver": "org.postgresql.Driver",
        }
    
    @property
    def staging_path(self) -> str:
        """Base path for staged data in S3."""
        return f"s3a://{self.staging_bucket}/staged/dwd"
