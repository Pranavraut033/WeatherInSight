"""Schema registry for managing data schemas and versions."""
import json
import hashlib
from datetime import datetime
from typing import Optional, Dict, Any, List
import psycopg2
from psycopg2.extras import RealDictCursor


class SchemaRegistry:
    """
    Manages data schemas with versioning.
    
    Supports:
    - Schema registration with automatic versioning
    - Schema compatibility validation
    - Schema lookup by name and version
    - Change history tracking
    """
    
    def __init__(self, dsn: str):
        """
        Initialize schema registry.
        
        Args:
            dsn: PostgreSQL connection string
        """
        self.dsn = dsn
        self._ensure_tables()
    
    def _ensure_tables(self):
        """Create schema registry tables if they don't exist."""
        with psycopg2.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                # Schema versions table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS schema_versions (
                        id SERIAL PRIMARY KEY,
                        schema_name VARCHAR(255) NOT NULL,
                        version INTEGER NOT NULL,
                        schema_definition JSONB NOT NULL,
                        schema_hash VARCHAR(64) NOT NULL,
                        description TEXT,
                        is_active BOOLEAN DEFAULT true,
                        compatibility_mode VARCHAR(50) DEFAULT 'BACKWARD',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        created_by VARCHAR(255),
                        UNIQUE(schema_name, version),
                        UNIQUE(schema_name, schema_hash)
                    );
                """)
                
                # Schema change history
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS schema_changes (
                        id SERIAL PRIMARY KEY,
                        schema_name VARCHAR(255) NOT NULL,
                        from_version INTEGER,
                        to_version INTEGER NOT NULL,
                        change_type VARCHAR(50) NOT NULL,
                        change_details JSONB,
                        applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        applied_by VARCHAR(255)
                    );
                """)
                
                # Indexes for performance
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_schema_versions_name 
                    ON schema_versions(schema_name);
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_schema_versions_active 
                    ON schema_versions(schema_name, is_active);
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_schema_changes_name 
                    ON schema_changes(schema_name);
                """)
                
                conn.commit()
    
    def _compute_hash(self, schema_def: Dict[str, Any]) -> str:
        """
        Compute deterministic hash of schema definition.
        
        Args:
            schema_def: Schema definition dictionary
            
        Returns:
            SHA256 hash of schema
        """
        # Sort keys for deterministic hashing
        schema_json = json.dumps(schema_def, sort_keys=True)
        return hashlib.sha256(schema_json.encode()).hexdigest()
    
    def register_schema(
        self,
        schema_name: str,
        schema_def: Dict[str, Any],
        description: Optional[str] = None,
        compatibility_mode: str = "BACKWARD",
        created_by: str = "system"
    ) -> int:
        """
        Register a new schema version.
        
        Args:
            schema_name: Name of the schema (e.g., 'raw_station_data')
            schema_def: Schema definition as dictionary
            description: Optional description of changes
            compatibility_mode: BACKWARD, FORWARD, FULL, or NONE
            created_by: User or system that registered the schema
            
        Returns:
            Version number of registered schema
            
        Raises:
            ValueError: If schema is incompatible with existing version
        """
        schema_hash = self._compute_hash(schema_def)
        
        with psycopg2.connect(self.dsn) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Check if identical schema already exists
                cur.execute("""
                    SELECT version FROM schema_versions
                    WHERE schema_name = %s AND schema_hash = %s
                """, (schema_name, schema_hash))
                
                existing = cur.fetchone()
                if existing:
                    return existing['version']
                
                # Get current latest version
                cur.execute("""
                    SELECT MAX(version) as max_version FROM schema_versions
                    WHERE schema_name = %s
                """, (schema_name,))
                
                result = cur.fetchone()
                current_version = result['max_version'] if result['max_version'] else 0
                new_version = current_version + 1
                
                # Validate compatibility if not first version
                if current_version > 0:
                    cur.execute("""
                        SELECT schema_definition FROM schema_versions
                        WHERE schema_name = %s AND version = %s
                    """, (schema_name, current_version))
                    
                    prev_schema = cur.fetchone()
                    if prev_schema:
                        self._validate_compatibility(
                            prev_schema['schema_definition'],
                            schema_def,
                            compatibility_mode
                        )
                
                # Insert new version
                cur.execute("""
                    INSERT INTO schema_versions 
                    (schema_name, version, schema_definition, schema_hash, 
                     description, compatibility_mode, created_by)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    schema_name, new_version, json.dumps(schema_def),
                    schema_hash, description, compatibility_mode, created_by
                ))
                
                # Log the change
                change_details = self._compute_changes(
                    prev_schema['schema_definition'] if current_version > 0 else {},
                    schema_def
                )
                
                cur.execute("""
                    INSERT INTO schema_changes
                    (schema_name, from_version, to_version, change_type, 
                     change_details, applied_by)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (
                    schema_name, current_version if current_version > 0 else None,
                    new_version, "REGISTER", json.dumps(change_details), created_by
                ))
                
                conn.commit()
                return new_version
    
    def _validate_compatibility(
        self,
        old_schema: Dict[str, Any],
        new_schema: Dict[str, Any],
        mode: str
    ):
        """
        Validate schema compatibility.
        
        Args:
            old_schema: Previous schema definition
            new_schema: New schema definition
            mode: Compatibility mode
            
        Raises:
            ValueError: If schemas are incompatible
        """
        if mode == "NONE":
            return
        
        old_fields = set(old_schema.get("fields", {}).keys())
        new_fields = set(new_schema.get("fields", {}).keys())
        
        if mode in ["BACKWARD", "FULL"]:
            # Can't remove required fields
            removed = old_fields - new_fields
            for field in removed:
                if old_schema["fields"][field].get("required", False):
                    raise ValueError(
                        f"BACKWARD incompatible: removed required field '{field}'"
                    )
        
        if mode in ["FORWARD", "FULL"]:
            # New required fields must have defaults
            added = new_fields - old_fields
            for field in added:
                field_def = new_schema["fields"][field]
                if field_def.get("required", False) and "default" not in field_def:
                    raise ValueError(
                        f"FORWARD incompatible: added required field '{field}' "
                        "without default"
                    )
    
    def _compute_changes(
        self,
        old_schema: Dict[str, Any],
        new_schema: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Compute differences between schemas."""
        old_fields = set(old_schema.get("fields", {}).keys())
        new_fields = set(new_schema.get("fields", {}).keys())
        
        return {
            "added_fields": list(new_fields - old_fields),
            "removed_fields": list(old_fields - new_fields),
            "modified_fields": [
                f for f in old_fields & new_fields
                if old_schema["fields"][f] != new_schema["fields"][f]
            ]
        }
    
    def get_schema(
        self,
        schema_name: str,
        version: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get schema definition by name and version.
        
        Args:
            schema_name: Name of the schema
            version: Specific version, or None for latest active
            
        Returns:
            Schema definition dictionary or None if not found
        """
        with psycopg2.connect(self.dsn) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                if version:
                    cur.execute("""
                        SELECT version, schema_definition, description, 
                               compatibility_mode, created_at, created_by
                        FROM schema_versions
                        WHERE schema_name = %s AND version = %s
                    """, (schema_name, version))
                else:
                    cur.execute("""
                        SELECT version, schema_definition, description,
                               compatibility_mode, created_at, created_by
                        FROM schema_versions
                        WHERE schema_name = %s AND is_active = true
                        ORDER BY version DESC
                        LIMIT 1
                    """, (schema_name,))
                
                row = cur.fetchone()
                if row:
                    return dict(row)
                return None
    
    def list_schemas(self) -> List[Dict[str, Any]]:
        """
        List all registered schemas with their latest versions.
        
        Returns:
            List of schema metadata dictionaries
        """
        with psycopg2.connect(self.dsn) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT DISTINCT ON (schema_name)
                        schema_name,
                        version,
                        description,
                        compatibility_mode,
                        created_at
                    FROM schema_versions
                    WHERE is_active = true
                    ORDER BY schema_name, version DESC
                """)
                
                return [dict(row) for row in cur.fetchall()]
    
    def get_schema_history(
        self,
        schema_name: str
    ) -> List[Dict[str, Any]]:
        """
        Get version history for a schema.
        
        Args:
            schema_name: Name of the schema
            
        Returns:
            List of version records ordered by version
        """
        with psycopg2.connect(self.dsn) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT version, description, created_at, created_by,
                           is_active, compatibility_mode
                    FROM schema_versions
                    WHERE schema_name = %s
                    ORDER BY version
                """, (schema_name,))
                
                return [dict(row) for row in cur.fetchall()]
    
    def deactivate_schema(
        self,
        schema_name: str,
        version: int,
        deactivated_by: str = "system"
    ):
        """
        Mark a schema version as inactive.
        
        Args:
            schema_name: Name of the schema
            version: Version to deactivate
            deactivated_by: User or system deactivating the schema
        """
        with psycopg2.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE schema_versions
                    SET is_active = false
                    WHERE schema_name = %s AND version = %s
                """, (schema_name, version))
                
                cur.execute("""
                    INSERT INTO schema_changes
                    (schema_name, to_version, change_type, applied_by)
                    VALUES (%s, %s, %s, %s)
                """, (schema_name, version, "DEACTIVATE", deactivated_by))
                
                conn.commit()
