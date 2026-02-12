"""
Staging writer

Writes cleaned DataFrames to parquet in the staging zone,
partitioned by date and station for efficient downstream processing.
"""
import logging
from typing import Dict, Optional
from datetime import datetime
from pyspark.sql import DataFrame
from pyspark.sql import functions as F

logger = logging.getLogger(__name__)


class StagingWriter:
    """Write cleaned data to staging zone in parquet format"""
    
    def __init__(
        self, 
        staging_path: str, 
        product_type: str,
        dataset_version: str
    ):
        """
        Initialize staging writer
        
        Args:
            staging_path: S3 path to staging bucket (e.g., s3a://bucket/staging/)
            product_type: Product type (air_temperature, etc.)
            dataset_version: Version identifier for lineage tracking
        """
        self.staging_path = staging_path.rstrip("/")
        self.product_type = product_type
        self.dataset_version = dataset_version
        
        # Build output path
        self.output_path = (
            f"{self.staging_path}/{product_type}/version={dataset_version}"
        )
        
        logger.info(
            f"Initialized StagingWriter: product={product_type}, "
            f"version={dataset_version}, path={self.output_path}"
        )
    
    def write(
        self, 
        df: DataFrame, 
        partition_cols: Optional[list] = None,
        mode: str = "append"
    ) -> Dict[str, any]:
        """
        Write DataFrame to staging zone
        
        Args:
            df: Cleaned DataFrame
            partition_cols: Columns to partition by (default: year, month)
            mode: Write mode ('append', 'overwrite', 'error')
        
        Returns:
            Dictionary with write statistics
        """
        if partition_cols is None:
            partition_cols = ["year", "month"]
        
        logger.info(
            f"Writing {df.count()} rows to staging zone, "
            f"partitioned by {partition_cols}"
        )
        
        try:
            # Add version column if not present
            if "dataset_version" not in df.columns:
                df = df.withColumn("dataset_version", F.lit(self.dataset_version))
            
            # Ensure partition columns exist
            missing_cols = [c for c in partition_cols if c not in df.columns]
            if missing_cols:
                raise ValueError(
                    f"Partition columns {missing_cols} not found in DataFrame"
                )
            
            # Write partitioned parquet
            df.write.parquet(
                self.output_path,
                mode=mode,
                partitionBy=partition_cols,
                compression="snappy"
            )
            
            # Collect statistics
            stats = {
                "output_path": self.output_path,
                "rows_written": df.count(),
                "partition_cols": partition_cols,
                "mode": mode,
                "written_at": datetime.utcnow().isoformat(),
                "dataset_version": self.dataset_version
            }
            
            logger.info(f"Write complete: {stats}")
            return stats
            
        except Exception as e:
            logger.error(f"Failed to write to staging: {e}")
            raise
    
    def write_with_compaction(
        self, 
        df: DataFrame,
        partition_cols: Optional[list] = None,
        target_file_size_mb: int = 128
    ) -> Dict[str, any]:
        """
        Write with automatic compaction to control file sizes
        
        Small files are a common problem in data lakes.
        This repartitions before writing to ensure reasonable file sizes.
        
        Args:
            df: Cleaned DataFrame
            partition_cols: Columns to partition by
            target_file_size_mb: Target size per output file
        
        Returns:
            Dictionary with write statistics
        """
        if partition_cols is None:
            partition_cols = ["year", "month"]
        
        # Estimate row count and size
        row_count = df.count()
        
        # Estimate bytes per row (rough approximation)
        # Typical DWD row: ~100 bytes
        estimated_size_mb = (row_count * 100) / (1024 * 1024)
        
        # Calculate partitions
        num_partitions = max(1, int(estimated_size_mb / target_file_size_mb))
        
        logger.info(
            f"Compacting to {num_partitions} partitions "
            f"(estimated {estimated_size_mb:.1f} MB total)"
        )
        
        # Repartition before write
        df = df.repartition(num_partitions, *partition_cols)
        
        return self.write(df, partition_cols=partition_cols, mode="append")
    
    def write_by_station(
        self, 
        df: DataFrame,
        mode: str = "append"
    ) -> Dict[str, any]:
        """
        Write partitioned by station and year
        
        Useful for processing per-station data.
        
        Args:
            df: Cleaned DataFrame
            mode: Write mode
        
        Returns:
            Write statistics
        """
        partition_cols = ["STATIONS_ID", "year"]
        return self.write(df, partition_cols=partition_cols, mode=mode)
    
    def validate_output(self) -> Dict[str, any]:
        """
        Validate written output
        
        Reads back the parquet files and computes basic statistics.
        
        Returns:
            Validation metrics
        """
        logger.info(f"Validating output at {self.output_path}")
        
        try:
            from pyspark.sql import SparkSession
            spark = SparkSession.getActiveSession()
            
            if spark is None:
                raise RuntimeError("No active Spark session found")
            
            # Read back the data
            df = spark.read.parquet(self.output_path)
            
            metrics = {
                "output_path": self.output_path,
                "total_rows": df.count(),
                "partitions": df.rdd.getNumPartitions(),
                "schema_fields": len(df.columns),
                "columns": df.columns
            }
            
            # Check for specific columns
            if "timestamp" in df.columns:
                date_range = df.agg(
                    F.min("timestamp").alias("min_ts"),
                    F.max("timestamp").alias("max_ts")
                ).collect()[0]
                metrics["date_range"] = {
                    "min": date_range["min_ts"],
                    "max": date_range["max_ts"]
                }
            
            if "STATIONS_ID" in df.columns:
                metrics["distinct_stations"] = df.select("STATIONS_ID").distinct().count()
            
            logger.info(f"Validation metrics: {metrics}")
            return metrics
            
        except Exception as e:
            logger.error(f"Validation failed: {e}")
            raise


def create_writer(
    staging_path: str, 
    product_type: str, 
    dataset_version: str
) -> StagingWriter:
    """
    Factory function to create a staging writer
    
    Args:
        staging_path: S3 path to staging zone
        product_type: Product type
        dataset_version: Dataset version identifier
    
    Returns:
        StagingWriter instance
    """
    return StagingWriter(staging_path, product_type, dataset_version)
