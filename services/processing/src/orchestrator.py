"""
Processing orchestrator

Main entry point for the processing pipeline.
Coordinates parsing, cleaning, and writing operations.
"""
import logging
import sys
from typing import Dict, Optional
from datetime import datetime
from pyspark.sql import SparkSession

from config import get_config
from parser import create_parser
from cleaner import create_cleaner
from writer import create_writer

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ProcessingOrchestrator:
    """Orchestrates the complete processing pipeline"""
    
    def __init__(self, spark: SparkSession):
        """
        Initialize orchestrator
        
        Args:
            spark: SparkSession instance
        """
        self.spark = spark
        self.config = get_config()
        logger.info("ProcessingOrchestrator initialized")
    
    def process_product(
        self,
        product_type: str,
        input_path: str,
        dataset_version: str,
        output_mode: str = "append"
    ) -> Dict[str, any]:
        """
        Process a single product type end-to-end
        
        Args:
            product_type: Product type (air_temperature, precipitation, etc.)
            input_path: S3 path to raw data
            dataset_version: Dataset version identifier
            output_mode: Write mode for staging ('append', 'overwrite')
        
        Returns:
            Processing statistics and metrics
        """
        logger.info(
            f"Starting processing: product={product_type}, "
            f"version={dataset_version}"
        )
        
        start_time = datetime.utcnow()
        
        try:
            # Step 1: Parse
            parser = create_parser(self.spark, product_type)
            df = parser.parse_directory(input_path)
            parse_metrics = parser.validate_data(df)
            
            logger.info(f"Parse complete: {parse_metrics['total_rows']} rows")
            
            # Step 2: Clean
            cleaner = create_cleaner(
                product_type, 
                quality_threshold=self.config.quality_flag_threshold
            )
            df = cleaner.clean(df)
            clean_metrics = cleaner.compute_quality_metrics(df)
            
            logger.info(
                f"Clean complete: {clean_metrics['rows_acceptable_quality']} "
                f"rows with acceptable quality"
            )
            
            # Step 3: Write to staging
            staging_path = f"s3a://{self.config.staging_bucket}/staging"
            writer = create_writer(staging_path, product_type, dataset_version)
            write_stats = writer.write_with_compaction(df)
            
            logger.info(f"Write complete: {write_stats['rows_written']} rows")
            
            # Step 4: Validate output
            validation_metrics = writer.validate_output()
            
            # Compile results
            end_time = datetime.utcnow()
            duration = (end_time - start_time).total_seconds()
            
            results = {
                "product_type": product_type,
                "dataset_version": dataset_version,
                "input_path": input_path,
                "parse_metrics": parse_metrics,
                "clean_metrics": clean_metrics,
                "write_stats": write_stats,
                "validation_metrics": validation_metrics,
                "processing_time_seconds": duration,
                "started_at": start_time.isoformat(),
                "completed_at": end_time.isoformat(),
                "status": "success"
            }
            
            logger.info(f"Processing complete in {duration:.2f}s")
            return results
            
        except Exception as e:
            logger.error(f"Processing failed: {e}", exc_info=True)
            
            end_time = datetime.utcnow()
            duration = (end_time - start_time).total_seconds()
            
            return {
                "product_type": product_type,
                "dataset_version": dataset_version,
                "input_path": input_path,
                "status": "failed",
                "error": str(e),
                "processing_time_seconds": duration,
                "started_at": start_time.isoformat(),
                "failed_at": end_time.isoformat(),
            }
    
    def process_multiple_products(
        self,
        product_types: list,
        input_base_path: str,
        dataset_version: str
    ) -> Dict[str, any]:
        """
        Process multiple product types
        
        Args:
            product_types: List of product types to process
            input_base_path: Base S3 path (product subdirs expected)
            dataset_version: Dataset version identifier
        
        Returns:
            Combined results for all products
        """
        logger.info(f"Processing {len(product_types)} products")
        
        results = {}
        
        for product_type in product_types:
            input_path = f"{input_base_path}/{product_type}"
            
            logger.info(f"Processing product: {product_type}")
            product_result = self.process_product(
                product_type, input_path, dataset_version
            )
            
            results[product_type] = product_result
        
        # Summarize
        successes = sum(1 for r in results.values() if r["status"] == "success")
        failures = len(results) - successes
        
        summary = {
            "total_products": len(product_types),
            "successful": successes,
            "failed": failures,
            "product_results": results
        }
        
        logger.info(
            f"Batch complete: {successes} succeeded, {failures} failed"
        )
        
        return summary


def create_spark_session(app_name: str, master: Optional[str] = None) -> SparkSession:
    """
    Create and configure Spark session
    
    Args:
        app_name: Spark application name
        master: Spark master URL (None for local mode)
    
    Returns:
        Configured SparkSession
    """
    config = get_config()
    
    builder = SparkSession.builder.appName(app_name)
    
    if master:
        builder = builder.master(master)
    else:
        builder = builder.master("local[*]")
    
    # S3/MinIO configuration
    builder = builder.config("spark.hadoop.fs.s3a.endpoint", config.s3_endpoint)
    builder = builder.config("spark.hadoop.fs.s3a.access.key", config.s3_access_key)
    builder = builder.config("spark.hadoop.fs.s3a.secret.key", config.s3_secret_key)
    builder = builder.config("spark.hadoop.fs.s3a.path.style.access", "true")
    builder = builder.config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
    
    # Performance tuning
    builder = builder.config("spark.sql.adaptive.enabled", "true")
    builder = builder.config("spark.sql.adaptive.coalescePartitions.enabled", "true")
    
    spark = builder.getOrCreate()
    
    logger.info(f"Spark session created: {spark.version}")
    return spark


def main():
    """Main entry point for CLI"""
    import argparse
    
    parser = argparse.ArgumentParser(description="WeatherInsight Processing Service")
    parser.add_argument(
        "product_type",
        help="Product type to process"
    )
    parser.add_argument(
        "input_path",
        help="S3 path to raw data"
    )
    parser.add_argument(
        "dataset_version",
        help="Dataset version identifier"
    )
    parser.add_argument(
        "--mode",
        default="append",
        choices=["append", "overwrite"],
        help="Write mode (default: append)"
    )
    parser.add_argument(
        "--spark-master",
        default=None,
        help="Spark master URL (default: local)"
    )
    
    args = parser.parse_args()
    
    # Create Spark session
    spark = create_spark_session("WeatherInsight-Processing", args.spark_master)
    
    try:
        # Run processing
        orchestrator = ProcessingOrchestrator(spark)
        results = orchestrator.process_product(
            args.product_type,
            args.input_path,
            args.dataset_version,
            output_mode=args.mode
        )
        
        # Print results
        import json
        print(json.dumps(results, indent=2, default=str))
        
        # Exit with appropriate code
        if results["status"] == "success":
            sys.exit(0)
        else:
            sys.exit(1)
            
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
