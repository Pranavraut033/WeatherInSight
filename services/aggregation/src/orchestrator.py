"""
Orchestration and CLI for quarterly feature aggregation.

This module coordinates the aggregation pipeline:
1. Create Spark session with S3 and PostgreSQL connectivity
2. Load staged data for specified product, year, quarter
3. Compute quarterly features
4. Write to PostgreSQL curated tables
5. Track dataset versions and lineage
6. Collect and report metrics
"""
import argparse
import logging
import sys
import time
from datetime import datetime
from typing import Dict, Any

from pyspark.sql import SparkSession

from .config import AggregationConfig
from .aggregator import QuarterlyAggregator
from .postgres_writer import PostgresWriter

# Import metadata service components
sys.path.append("/opt/metadata/src")
try:
    from dataset_versioning import DatasetVersioning, DatasetStatus
except ImportError:
    # Fallback for local development
    DatasetVersioning = None
    DatasetStatus = None


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


class AggregationOrchestrator:
    """Orchestrates quarterly feature aggregation pipeline."""
    
    # Mapping from product type to curated dataset name
    DATASET_MAP = {
        "air_temperature": "curated_temperature_features",
        "precipitation": "curated_precipitation_features",
        "wind": "curated_wind_features",
        "pressure": "curated_pressure_features",
        "moisture": "curated_humidity_features",
    }
    
    # Schema names for each feature type
    SCHEMA_MAP = {
        "air_temperature": "quarterly_temperature",
        "precipitation": "quarterly_precipitation",
        "wind": "quarterly_wind",
        "pressure": "quarterly_pressure",
        "moisture": "quarterly_humidity",
    }
    
    def __init__(self, config: AggregationConfig):
        """
        Initialize orchestrator.
        
        Args:
            config: Configuration object
        """
        self.config = config
        self.spark: SparkSession = None
        self.aggregator: QuarterlyAggregator = None
        self.writer: PostgresWriter = None
        self.versioning: DatasetVersioning = None
    
    def setup_spark(self) -> SparkSession:
        """
        Create and configure Spark session with S3 and PostgreSQL support.
        
        Returns:
            Configured SparkSession
        """
        logger.info("Initializing Spark session...")
        
        builder = SparkSession.builder.appName(self.config.spark_app_name)
        
        # Configure S3/MinIO access
        builder.config("spark.hadoop.fs.s3a.endpoint", self.config.s3_endpoint)
        builder.config("spark.hadoop.fs.s3a.access.key", self.config.s3_access_key)
        builder.config("spark.hadoop.fs.s3a.secret.key", self.config.s3_secret_key)
        builder.config("spark.hadoop.fs.s3a.path.style.access", "true")
        builder.config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
        builder.config("spark.hadoop.fs.s3a.connection.ssl.enabled", "false")
        
        # Configure broadcast threshold
        builder.config(
            "spark.sql.autoBroadcastJoinThreshold",
            self.config.broadcast_threshold_mb * 1024 * 1024
        )
        
        # Set master
        builder.config("spark.master", self.config.spark_master)
        
        spark = builder.getOrCreate()
        
        logger.info(f"Spark session created: {spark.version}")
        
        return spark
    
    def setup_components(self):
        """Initialize all pipeline components."""
        self.spark = self.setup_spark()
        self.aggregator = QuarterlyAggregator(self.config, self.spark)
        self.writer = PostgresWriter(self.config)
        
        # Initialize versioning if available
        if DatasetVersioning is not None:
            self.versioning = DatasetVersioning(self.config.postgres_url)
            logger.info("Dataset versioning enabled")
        else:
            logger.warning("Dataset versioning not available (metadata service not found)")
    
    def run_aggregation(
        self,
        product_type: str,
        year: int,
        quarter: int,
        staged_dataset_version: str,
        curated_dataset_version: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Run complete aggregation pipeline for a product/quarter.
        
        Args:
            product_type: Product type to aggregate
            year: Year
            quarter: Quarter (1-4)
            staged_dataset_version: Version of staged data to read
            curated_dataset_version: Version tag for curated output (default: YYYYQN_v1)
        
        Returns:
            Dictionary with pipeline metrics and status
        """
        start_time = time.time()
        
        # Generate curated version if not provided
        if curated_dataset_version is None:
            curated_dataset_version = f"{year}Q{quarter}_v1"
        
        logger.info(
            f"Starting aggregation: {product_type} {year}Q{quarter} "
            f"(staged: {staged_dataset_version}, curated: {curated_dataset_version})"
        )
        
        metrics = {
            "product_type": product_type,
            "year": year,
            "quarter": quarter,
            "staged_version": staged_dataset_version,
            "curated_version": curated_dataset_version,
            "status": "running",
            "start_time": datetime.utcnow().isoformat(),
        }
        
        curated_version_id = None
        
        try:
            # Create dataset version entry
            if self.versioning:
                dataset_name = self.DATASET_MAP[product_type]
                schema_name = self.SCHEMA_MAP[product_type]
                
                # Determine quarter boundaries for metadata
                quarter_start_month = (quarter - 1) * 3 + 1
                quarter_end_month = quarter * 3
                quarter_start = f"{year}-{quarter_start_month:02d}-01"
                
                if quarter_end_month in [1, 3, 5, 7, 8, 10, 12]:
                    last_day = 31
                elif quarter_end_month in [4, 6, 9, 11]:
                    last_day = 30
                else:
                    last_day = 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28
                
                quarter_end = f"{year}-{quarter_end_month:02d}-{last_day}"
                
                curated_version_id = self.versioning.create_version(
                    dataset_name=dataset_name,
                    version=curated_dataset_version,
                    schema_name=schema_name,
                    schema_version=1,
                    start_date=quarter_start,
                    end_date=quarter_end,
                    storage_location=f"postgres://{self.writer.TABLE_MAP[product_type]}",
                    metadata={
                        "product_type": product_type,
                        "quarter": quarter,
                        "year": year,
                        "staged_version": staged_dataset_version
                    }
                )
                
                logger.info(f"Created curated dataset version: {curated_version_id}")
                
                # Update status to processing
                self.versioning.update_version_status(
                    version_id=curated_version_id,
                    status=DatasetStatus.PROCESSING
                )
            
            # Compute quarterly features
            logger.info("Computing quarterly features...")
            features_df = self.aggregator.compute_quarterly_features(
                product_type=product_type,
                year=year,
                quarter=quarter,
                dataset_version=staged_dataset_version
            )
            
            # Cache the DataFrame for counting and writing
            features_df.cache()
            
            row_count = features_df.count()
            logger.info(f"Computed {row_count} feature records")
            
            metrics["feature_count"] = row_count
            
            # Write to PostgreSQL
            logger.info("Writing features to PostgreSQL...")
            written_count = self.writer.write_features(
                features_df=features_df,
                product_type=product_type,
                year=year,
                quarter=quarter,
                dataset_version=staged_dataset_version,
                mode="append"
            )
            
            metrics["written_count"] = written_count
            
            # Unpersist cached DataFrame
            features_df.unpersist()
            
            # Calculate quality metrics
            # Get sample stats from the computed features
            sample_row = features_df.select("missingness_ratio").first()
            if sample_row:
                avg_missingness = float(sample_row["missingness_ratio"]) if sample_row["missingness_ratio"] else 0.0
            else:
                avg_missingness = 0.0
            
            quality_metrics = {
                "avg_missingness_ratio": avg_missingness,
                "total_stations": row_count
            }
            
            metrics["quality_metrics"] = quality_metrics
            
            # Update dataset version with success status
            if self.versioning and curated_version_id:
                self.versioning.update_version_status(
                    version_id=curated_version_id,
                    status=DatasetStatus.AVAILABLE,
                    record_count=written_count,
                    quality_metrics=quality_metrics
                )
                
                logger.info(f"Updated dataset version status to AVAILABLE")
            
            # Record processing time
            elapsed_time = time.time() - start_time
            metrics["elapsed_seconds"] = round(elapsed_time, 2)
            metrics["status"] = "success"
            metrics["end_time"] = datetime.utcnow().isoformat()
            
            logger.info(
                f"Aggregation completed successfully in {elapsed_time:.2f}s: "
                f"{written_count} features written"
            )
            
        except Exception as e:
            elapsed_time = time.time() - start_time
            metrics["elapsed_seconds"] = round(elapsed_time, 2)
            metrics["status"] = "failed"
            metrics["error"] = str(e)
            metrics["end_time"] = datetime.utcnow().isoformat()
            
            logger.error(f"Aggregation failed: {e}", exc_info=True)
            
            # Update dataset version with failure status
            if self.versioning and curated_version_id:
                self.versioning.update_version_status(
                    version_id=curated_version_id,
                    status=DatasetStatus.FAILED,
                    quality_metrics={"error": str(e)}
                )
            
            raise
        
        return metrics
    
    def cleanup(self):
        """Clean up resources."""
        if self.spark:
            logger.info("Stopping Spark session...")
            self.spark.stop()


def create_temperature_aggregation(year: int, quarter: int, staged_version: str) -> Dict[str, Any]:
    """Factory: Temperature feature aggregation."""
    config = AggregationConfig()
    orchestrator = AggregationOrchestrator(config)
    
    try:
        orchestrator.setup_components()
        return orchestrator.run_aggregation("air_temperature", year, quarter, staged_version)
    finally:
        orchestrator.cleanup()


def create_precipitation_aggregation(year: int, quarter: int, staged_version: str) -> Dict[str, Any]:
    """Factory: Precipitation feature aggregation."""
    config = AggregationConfig()
    orchestrator = AggregationOrchestrator(config)
    
    try:
        orchestrator.setup_components()
        return orchestrator.run_aggregation("precipitation", year, quarter, staged_version)
    finally:
        orchestrator.cleanup()


def create_wind_aggregation(year: int, quarter: int, staged_version: str) -> Dict[str, Any]:
    """Factory: Wind feature aggregation."""
    config = AggregationConfig()
    orchestrator = AggregationOrchestrator(config)
    
    try:
        orchestrator.setup_components()
        return orchestrator.run_aggregation("wind", year, quarter, staged_version)
    finally:
        orchestrator.cleanup()


def create_pressure_aggregation(year: int, quarter: int, staged_version: str) -> Dict[str, Any]:
    """Factory: Pressure feature aggregation."""
    config = AggregationConfig()
    orchestrator = AggregationOrchestrator(config)
    
    try:
        orchestrator.setup_components()
        return orchestrator.run_aggregation("pressure", year, quarter, staged_version)
    finally:
        orchestrator.cleanup()


def create_humidity_aggregation(year: int, quarter: int, staged_version: str) -> Dict[str, Any]:
    """Factory: Humidity feature aggregation."""
    config = AggregationConfig()
    orchestrator = AggregationOrchestrator(config)
    
    try:
        orchestrator.setup_components()
        return orchestrator.run_aggregation("moisture", year, quarter, staged_version)
    finally:
        orchestrator.cleanup()


def main():
    """CLI entry point for aggregation service."""
    parser = argparse.ArgumentParser(
        description="WeatherInsight Quarterly Feature Aggregation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Aggregate temperature features for 2023 Q1
  python orchestrator.py air_temperature 2023 1 v1.0.0
  
  # Aggregate precipitation with custom curated version
  python orchestrator.py precipitation 2023 2 v1.0.0 --curated-version 2023Q2_v2
        """
    )
    
    parser.add_argument(
        "product_type",
        choices=["air_temperature", "precipitation", "wind", "pressure", "moisture"],
        help="Product type to aggregate"
    )
    
    parser.add_argument(
        "year",
        type=int,
        help="Year to aggregate"
    )
    
    parser.add_argument(
        "quarter",
        type=int,
        choices=[1, 2, 3, 4],
        help="Quarter to aggregate (1-4)"
    )
    
    parser.add_argument(
        "staged_version",
        help="Dataset version of staged data to read"
    )
    
    parser.add_argument(
        "--curated-version",
        help="Version tag for curated output (default: YYYYQN_v1)"
    )
    
    args = parser.parse_args()
    
    # Run aggregation
    config = AggregationConfig()
    orchestrator = AggregationOrchestrator(config)
    
    try:
        orchestrator.setup_components()
        
        metrics = orchestrator.run_aggregation(
            product_type=args.product_type,
            year=args.year,
            quarter=args.quarter,
            staged_dataset_version=args.staged_version,
            curated_dataset_version=args.curated_version
        )
        
        # Print summary
        print("\n" + "=" * 60)
        print("AGGREGATION SUMMARY")
        print("=" * 60)
        print(f"Product Type:      {metrics['product_type']}")
        print(f"Period:            {metrics['year']}Q{metrics['quarter']}")
        print(f"Staged Version:    {metrics['staged_version']}")
        print(f"Curated Version:   {metrics['curated_version']}")
        print(f"Status:            {metrics['status']}")
        print(f"Features Computed: {metrics.get('feature_count', 'N/A')}")
        print(f"Features Written:  {metrics.get('written_count', 'N/A')}")
        print(f"Elapsed Time:      {metrics['elapsed_seconds']}s")
        
        if "quality_metrics" in metrics:
            qm = metrics["quality_metrics"]
            print(f"\nQuality Metrics:")
            print(f"  Stations:           {qm.get('total_stations', 'N/A')}")
            print(f"  Avg Missingness:    {qm.get('avg_missingness_ratio', 'N/A'):.2%}")
        
        print("=" * 60 + "\n")
        
        # Exit with appropriate code
        sys.exit(0 if metrics["status"] == "success" else 1)
        
    except Exception as e:
        logger.error(f"Aggregation failed: {e}", exc_info=True)
        sys.exit(1)
    finally:
        orchestrator.cleanup()


if __name__ == "__main__":
    main()
