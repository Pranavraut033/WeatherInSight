"""Metadata registry for tracking dataset versions and ingestion runs."""
import logging
from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import create_engine, Column, Integer, String, BigInteger, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

from .config import PostgresConfig

logger = logging.getLogger(__name__)

Base = declarative_base()


class IngestionRun(Base):
    """Track individual ingestion runs."""
    __tablename__ = "ingestion_runs"

    run_id = Column(String(100), primary_key=True)
    started_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime)
    status = Column(String(20), nullable=False)  # running, completed, failed
    variable = Column(String(50), nullable=False)
    station_count = Column(Integer)
    file_count = Column(Integer)
    total_bytes = Column(BigInteger)
    error_message = Column(Text)
    notes = Column(Text)


class DatasetVersion(Base):
    """Track dataset versions for quarterly batches."""
    __tablename__ = "dataset_versions"

    version_id = Column(Integer, primary_key=True, autoincrement=True)
    version_name = Column(String(50), nullable=False, unique=True)
    year = Column(Integer, nullable=False)
    quarter = Column(Integer, nullable=False)
    schema_version = Column(String(20), nullable=False)
    ingestion_run_id = Column(String(100), nullable=False)
    processing_started_at = Column(DateTime, nullable=False)
    processing_completed_at = Column(DateTime)
    status = Column(String(20), nullable=False)
    station_count = Column(Integer)
    total_observations = Column(BigInteger)
    notes = Column(Text)


class MetadataRegistry:
    """Registry for tracking ingestion runs and dataset versions."""

    def __init__(self, config: PostgresConfig):
        """Initialize metadata registry.

        Args:
            config: PostgreSQL configuration
        """
        self.config = config
        self.engine = create_engine(config.connection_string)
        self.SessionLocal = sessionmaker(bind=self.engine)
        self._init_tables()

    def _init_tables(self):
        """Create tables if they don't exist."""
        try:
            Base.metadata.create_all(self.engine)
            logger.info("Metadata tables initialized")
        except Exception as e:
            logger.error(f"Failed to initialize metadata tables: {e}")
            raise

    def create_ingestion_run(
        self,
        variable: str,
        run_id: Optional[str] = None,
    ) -> str:
        """Create a new ingestion run record.

        Args:
            variable: Variable being ingested
            run_id: Optional custom run ID (auto-generated if not provided)

        Returns:
            Run ID
        """
        if run_id is None:
            run_id = f"ingest_{variable}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"

        session: Session = self.SessionLocal()
        try:
            run = IngestionRun(
                run_id=run_id,
                started_at=datetime.utcnow(),
                status="running",
                variable=variable,
            )
            session.add(run)
            session.commit()
            logger.info(f"Created ingestion run: {run_id}")
            return run_id
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to create ingestion run: {e}")
            raise
        finally:
            session.close()

    def update_ingestion_run(
        self,
        run_id: str,
        status: str,
        station_count: Optional[int] = None,
        file_count: Optional[int] = None,
        total_bytes: Optional[int] = None,
        error_message: Optional[str] = None,
        notes: Optional[str] = None,
    ):
        """Update an ingestion run record.

        Args:
            run_id: Run ID
            status: Current status (running, completed, failed)
            station_count: Number of stations processed
            file_count: Number of files uploaded
            total_bytes: Total bytes uploaded
            error_message: Error message if failed
            notes: Additional notes
        """
        session: Session = self.SessionLocal()
        try:
            run = session.query(IngestionRun).filter_by(run_id=run_id).first()
            if not run:
                raise ValueError(f"Ingestion run not found: {run_id}")

            run.status = status
            if station_count is not None:
                run.station_count = station_count
            if file_count is not None:
                run.file_count = file_count
            if total_bytes is not None:
                run.total_bytes = total_bytes
            if error_message is not None:
                run.error_message = error_message
            if notes is not None:
                run.notes = notes

            if status in ["completed", "failed"]:
                run.completed_at = datetime.utcnow()

            session.commit()
            logger.info(f"Updated ingestion run {run_id}: status={status}")
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to update ingestion run: {e}")
            raise
        finally:
            session.close()

    def get_ingestion_run(self, run_id: str) -> Optional[dict]:
        """Get ingestion run details.

        Args:
            run_id: Run ID

        Returns:
            Run details as dictionary or None if not found
        """
        session: Session = self.SessionLocal()
        try:
            run = session.query(IngestionRun).filter_by(run_id=run_id).first()
            if not run:
                return None

            return {
                "run_id": run.run_id,
                "started_at": run.started_at,
                "completed_at": run.completed_at,
                "status": run.status,
                "variable": run.variable,
                "station_count": run.station_count,
                "file_count": run.file_count,
                "total_bytes": run.total_bytes,
                "error_message": run.error_message,
                "notes": run.notes,
            }
        finally:
            session.close()

    def create_dataset_version(
        self,
        version_name: str,
        year: int,
        quarter: int,
        ingestion_run_id: str,
        schema_version: str = "1.0",
    ) -> int:
        """Create a new dataset version record.

        Args:
            version_name: Version name (e.g., '2023_Q1_v1')
            year: Year
            quarter: Quarter (1-4)
            ingestion_run_id: Associated ingestion run ID
            schema_version: Schema version

        Returns:
            Version ID
        """
        session: Session = self.SessionLocal()
        try:
            version = DatasetVersion(
                version_name=version_name,
                year=year,
                quarter=quarter,
                schema_version=schema_version,
                ingestion_run_id=ingestion_run_id,
                processing_started_at=datetime.utcnow(),
                status="processing",
            )
            session.add(version)
            session.commit()
            session.refresh(version)
            logger.info(f"Created dataset version: {version_name} (ID: {version.version_id})")
            return version.version_id
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to create dataset version: {e}")
            raise
        finally:
            session.close()

    def close(self):
        """Close database connection."""
        self.engine.dispose()
