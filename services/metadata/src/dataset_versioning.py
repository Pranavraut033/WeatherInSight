"""Dataset versioning and lineage tracking."""
from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum
import psycopg2
from psycopg2.extras import RealDictCursor


class DatasetStatus(Enum):
    """Dataset version status."""
    PENDING = "pending"
    PROCESSING = "processing"
    AVAILABLE = "available"
    DEPRECATED = "deprecated"
    FAILED = "failed"


class DatasetVersioning:
    """
    Manages dataset versions and lineage.
    
    Tracks:
    - Dataset versions linked to ingestion runs
    - Parent-child relationships (lineage)
    - Processing metadata and statistics
    - Quality metrics per version
    """
    
    def __init__(self, dsn: str):
        """
        Initialize dataset versioning.
        
        Args:
            dsn: PostgreSQL connection string
        """
        self.dsn = dsn
        self._ensure_tables()
    
    def _ensure_tables(self):
        """Create dataset versioning tables if they don't exist."""
        with psycopg2.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                # Dataset versions table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS dataset_versions (
                        id SERIAL PRIMARY KEY,
                        dataset_name VARCHAR(255) NOT NULL,
                        version VARCHAR(100) NOT NULL,
                        schema_name VARCHAR(255),
                        schema_version INTEGER,
                        status VARCHAR(50) DEFAULT 'pending',
                        ingestion_run_id INTEGER REFERENCES ingestion_runs(id),
                        start_date DATE,
                        end_date DATE,
                        record_count BIGINT,
                        file_count INTEGER,
                        total_size_bytes BIGINT,
                        storage_location TEXT,
                        quality_metrics JSONB,
                        metadata JSONB,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        created_by VARCHAR(255),
                        UNIQUE(dataset_name, version)
                    );
                """)
                
                # Dataset lineage table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS dataset_lineage (
                        id SERIAL PRIMARY KEY,
                        child_dataset_id INTEGER NOT NULL REFERENCES dataset_versions(id),
                        parent_dataset_id INTEGER NOT NULL REFERENCES dataset_versions(id),
                        transformation_type VARCHAR(100),
                        transformation_metadata JSONB,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(child_dataset_id, parent_dataset_id)
                    );
                """)
                
                # Dataset quality checks table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS dataset_quality_checks (
                        id SERIAL PRIMARY KEY,
                        dataset_version_id INTEGER NOT NULL REFERENCES dataset_versions(id),
                        check_name VARCHAR(255) NOT NULL,
                        check_type VARCHAR(100) NOT NULL,
                        status VARCHAR(50) NOT NULL,
                        result JSONB,
                        error_message TEXT,
                        checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                
                # Indexes
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_dataset_versions_name 
                    ON dataset_versions(dataset_name);
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_dataset_versions_status 
                    ON dataset_versions(status);
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_dataset_versions_dates 
                    ON dataset_versions(start_date, end_date);
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_dataset_lineage_child 
                    ON dataset_lineage(child_dataset_id);
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_dataset_lineage_parent 
                    ON dataset_lineage(parent_dataset_id);
                """)
                
                conn.commit()
    
    def create_version(
        self,
        dataset_name: str,
        version: str,
        schema_name: Optional[str] = None,
        schema_version: Optional[int] = None,
        ingestion_run_id: Optional[int] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        storage_location: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        created_by: str = "system"
    ) -> int:
        """
        Create a new dataset version.
        
        Args:
            dataset_name: Name of the dataset
            version: Version identifier (e.g., 'v1', '2024-Q1')
            schema_name: Associated schema name
            schema_version: Associated schema version
            ingestion_run_id: Link to ingestion run
            start_date: Data coverage start date
            end_date: Data coverage end date
            storage_location: Path or URI to data
            metadata: Additional metadata
            created_by: Creator identifier
            
        Returns:
            Dataset version ID
        """
        with psycopg2.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO dataset_versions
                    (dataset_name, version, schema_name, schema_version,
                     ingestion_run_id, start_date, end_date, storage_location,
                     metadata, created_by)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    dataset_name, version, schema_name, schema_version,
                    ingestion_run_id, start_date, end_date, storage_location,
                    psycopg2.extras.Json(metadata) if metadata else None,
                    created_by
                ))
                
                version_id = cur.fetchone()[0]
                conn.commit()
                return version_id
    
    def update_version_status(
        self,
        version_id: int,
        status: DatasetStatus,
        record_count: Optional[int] = None,
        file_count: Optional[int] = None,
        total_size_bytes: Optional[int] = None,
        quality_metrics: Optional[Dict[str, Any]] = None
    ):
        """
        Update dataset version status and statistics.
        
        Args:
            version_id: Dataset version ID
            status: New status
            record_count: Total record count
            file_count: Number of files
            total_size_bytes: Total size in bytes
            quality_metrics: Quality metrics dictionary
        """
        with psycopg2.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                updates = ["status = %s", "updated_at = CURRENT_TIMESTAMP"]
                params = [status.value]
                
                if record_count is not None:
                    updates.append("record_count = %s")
                    params.append(record_count)
                
                if file_count is not None:
                    updates.append("file_count = %s")
                    params.append(file_count)
                
                if total_size_bytes is not None:
                    updates.append("total_size_bytes = %s")
                    params.append(total_size_bytes)
                
                if quality_metrics is not None:
                    updates.append("quality_metrics = %s")
                    params.append(psycopg2.extras.Json(quality_metrics))
                
                params.append(version_id)
                
                cur.execute(f"""
                    UPDATE dataset_versions
                    SET {', '.join(updates)}
                    WHERE id = %s
                """, params)
                
                conn.commit()
    
    def add_lineage(
        self,
        child_id: int,
        parent_id: int,
        transformation_type: str,
        transformation_metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Record lineage between dataset versions.
        
        Args:
            child_id: Child dataset version ID
            parent_id: Parent dataset version ID
            transformation_type: Type of transformation (e.g., 'aggregation', 'filter')
            transformation_metadata: Additional transformation details
        """
        with psycopg2.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO dataset_lineage
                    (child_dataset_id, parent_dataset_id, transformation_type,
                     transformation_metadata)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (child_dataset_id, parent_dataset_id) DO NOTHING
                """, (
                    child_id, parent_id, transformation_type,
                    psycopg2.extras.Json(transformation_metadata) if transformation_metadata else None
                ))
                
                conn.commit()
    
    def get_version(
        self,
        dataset_name: str,
        version: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get dataset version by name and version.
        
        Args:
            dataset_name: Name of the dataset
            version: Specific version, or None for latest
            
        Returns:
            Dataset version dictionary or None
        """
        with psycopg2.connect(self.dsn) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                if version:
                    cur.execute("""
                        SELECT * FROM dataset_versions
                        WHERE dataset_name = %s AND version = %s
                    """, (dataset_name, version))
                else:
                    cur.execute("""
                        SELECT * FROM dataset_versions
                        WHERE dataset_name = %s
                        ORDER BY created_at DESC
                        LIMIT 1
                    """, (dataset_name,))
                
                row = cur.fetchone()
                return dict(row) if row else None
    
    def list_versions(
        self,
        dataset_name: Optional[str] = None,
        status: Optional[DatasetStatus] = None
    ) -> List[Dict[str, Any]]:
        """
        List dataset versions with optional filters.
        
        Args:
            dataset_name: Filter by dataset name
            status: Filter by status
            
        Returns:
            List of dataset version dictionaries
        """
        with psycopg2.connect(self.dsn) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = "SELECT * FROM dataset_versions WHERE 1=1"
                params = []
                
                if dataset_name:
                    query += " AND dataset_name = %s"
                    params.append(dataset_name)
                
                if status:
                    query += " AND status = %s"
                    params.append(status.value)
                
                query += " ORDER BY created_at DESC"
                
                cur.execute(query, params)
                return [dict(row) for row in cur.fetchall()]
    
    def get_lineage(
        self,
        version_id: int,
        direction: str = "both"
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get lineage for a dataset version.
        
        Args:
            version_id: Dataset version ID
            direction: 'upstream', 'downstream', or 'both'
            
        Returns:
            Dictionary with 'parents' and/or 'children' lists
        """
        result = {}
        
        with psycopg2.connect(self.dsn) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                if direction in ["upstream", "both"]:
                    cur.execute("""
                        SELECT 
                            dv.id, dv.dataset_name, dv.version, dv.status,
                            dl.transformation_type, dl.transformation_metadata
                        FROM dataset_lineage dl
                        JOIN dataset_versions dv ON dl.parent_dataset_id = dv.id
                        WHERE dl.child_dataset_id = %s
                    """, (version_id,))
                    result["parents"] = [dict(row) for row in cur.fetchall()]
                
                if direction in ["downstream", "both"]:
                    cur.execute("""
                        SELECT 
                            dv.id, dv.dataset_name, dv.version, dv.status,
                            dl.transformation_type, dl.transformation_metadata
                        FROM dataset_lineage dl
                        JOIN dataset_versions dv ON dl.child_dataset_id = dv.id
                        WHERE dl.parent_dataset_id = %s
                    """, (version_id,))
                    result["children"] = [dict(row) for row in cur.fetchall()]
        
        return result
    
    def add_quality_check(
        self,
        version_id: int,
        check_name: str,
        check_type: str,
        status: str,
        result: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None
    ):
        """
        Record a quality check result.
        
        Args:
            version_id: Dataset version ID
            check_name: Name of the check
            check_type: Type of check (e.g., 'completeness', 'accuracy')
            status: Check status ('passed', 'failed', 'warning')
            result: Check result details
            error_message: Error message if failed
        """
        with psycopg2.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO dataset_quality_checks
                    (dataset_version_id, check_name, check_type, status, 
                     result, error_message)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (
                    version_id, check_name, check_type, status,
                    psycopg2.extras.Json(result) if result else None,
                    error_message
                ))
                
                conn.commit()
    
    def get_quality_checks(
        self,
        version_id: int
    ) -> List[Dict[str, Any]]:
        """
        Get quality check results for a dataset version.
        
        Args:
            version_id: Dataset version ID
            
        Returns:
            List of quality check dictionaries
        """
        with psycopg2.connect(self.dsn) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM dataset_quality_checks
                    WHERE dataset_version_id = %s
                    ORDER BY checked_at DESC
                """, (version_id,))
                
                return [dict(row) for row in cur.fetchall()]
