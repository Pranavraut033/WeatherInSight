"""
PostgreSQL writer for curated feature tables.
"""
import logging
from typing import Optional

import psycopg2
from pyspark.sql import DataFrame

from .config import AggregationConfig


logger = logging.getLogger(__name__)


class PostgresWriter:
    """Writes feature DataFrames to PostgreSQL curated tables."""
    
    # Mapping from product type to curated table name
    TABLE_MAP = {
        "air_temperature": "quarterly_temperature_features",
        "precipitation": "quarterly_precipitation_features",
        "wind": "quarterly_wind_features",
        "pressure": "quarterly_pressure_features",
        "moisture": "quarterly_humidity_features",
    }
    
    def __init__(self, config: AggregationConfig):
        """
        Initialize writer.
        
        Args:
            config: Configuration object
        """
        self.config = config
    
    def delete_existing_features(
        self,
        product_type: str,
        station_id: Optional[int],
        year: int,
        quarter: int,
        dataset_version: str
    ):
        """
        Delete existing feature rows for reprocessing.
        
        This allows clean upsert behavior by removing old records before
        writing new ones, avoiding unique constraint violations.
        
        Args:
            product_type: Product type (determines target table)
            station_id: Station ID to delete (None for all stations)
            year: Year
            quarter: Quarter
            dataset_version: Dataset version
        """
        table_name = self.TABLE_MAP.get(product_type)
        if not table_name:
            raise ValueError(f"Unknown product type: {product_type}")
        
        with psycopg2.connect(self.config.postgres_url) as conn:
            with conn.cursor() as cur:
                if station_id is not None:
                    sql = f"""
                        DELETE FROM {table_name}
                        WHERE station_id = %s
                          AND year = %s
                          AND quarter = %s
                          AND dataset_version = %s
                    """
                    cur.execute(sql, (station_id, year, quarter, dataset_version))
                else:
                    sql = f"""
                        DELETE FROM {table_name}
                        WHERE year = %s
                          AND quarter = %s
                          AND dataset_version = %s
                    """
                    cur.execute(sql, (year, quarter, dataset_version))
                
                deleted_count = cur.rowcount
                conn.commit()
                
                logger.info(
                    f"Deleted {deleted_count} existing rows from {table_name} "
                    f"for {year}Q{quarter} v{dataset_version}"
                )
    
    def write_features(
        self,
        features_df: DataFrame,
        product_type: str,
        year: int,
        quarter: int,
        dataset_version: str,
        mode: str = "append"
    ) -> int:
        """
        Write feature DataFrame to PostgreSQL table.
        
        Args:
            features_df: DataFrame with quarterly features
            product_type: Product type (determines target table)
            year: Year for deletion filter
            quarter: Quarter for deletion filter
            dataset_version: Dataset version for deletion filter
            mode: Write mode ('append' or 'overwrite')
        
        Returns:
            Number of rows written
        """
        table_name = self.TABLE_MAP.get(product_type)
        if not table_name:
            raise ValueError(f"Unknown product type: {product_type}")
        
        # Delete existing records before appending to avoid duplicates
        if mode == "append":
            logger.info(f"Deleting existing features for {year}Q{quarter} v{dataset_version}...")
            self.delete_existing_features(
                product_type=product_type,
                station_id=None,  # Delete all stations for this quarter
                year=year,
                quarter=quarter,
                dataset_version=dataset_version
            )
        
        # Count rows before writing
        row_count = features_df.count()
        
        logger.info(f"Writing {row_count} rows to {table_name}...")
        
        # Write to PostgreSQL using JDBC
        features_df.write.jdbc(
            url=self.config.postgres_jdbc_url,
            table=table_name,
            mode=mode,
            properties=self.config.jdbc_properties
        )
        
        logger.info(f"Successfully wrote {row_count} rows to {table_name}")
        
        return row_count
