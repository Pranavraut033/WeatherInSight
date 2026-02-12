"""Test configuration for metadata service tests."""
import pytest
import os
import psycopg2


@pytest.fixture(scope="session")
def postgres_dsn():
    """PostgreSQL connection string for tests."""
    return (
        f"postgresql://{os.getenv('POSTGRES_USER', 'weatherinsight')}:"
        f"{os.getenv('POSTGRES_PASSWORD', 'weatherinsight123')}"
        f"@{os.getenv('POSTGRES_HOST', 'localhost')}:"
        f"{os.getenv('POSTGRES_PORT', '5432')}"
        f"/{os.getenv('POSTGRES_DB', 'weatherinsight')}"
    )


@pytest.fixture(autouse=True)
def cleanup_test_data(postgres_dsn):
    """Clean up test data after each test."""
    yield
    
    # Clean up test schemas and datasets
    with psycopg2.connect(postgres_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM schema_changes WHERE schema_name LIKE 'test_%'")
            cur.execute("DELETE FROM schema_versions WHERE schema_name LIKE 'test_%'")
            cur.execute("DELETE FROM dataset_quality_checks WHERE dataset_version_id IN "
                       "(SELECT id FROM dataset_versions WHERE dataset_name LIKE 'test_%')")
            cur.execute("DELETE FROM dataset_lineage WHERE child_dataset_id IN "
                       "(SELECT id FROM dataset_versions WHERE dataset_name LIKE 'test_%')")
            cur.execute("DELETE FROM dataset_versions WHERE dataset_name LIKE 'test_%'")
            conn.commit()
