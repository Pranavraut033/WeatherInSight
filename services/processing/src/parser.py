"""
DWD raw file parser

Reads semicolon-delimited text files from MinIO, validates against schema,
and converts to Spark DataFrame with proper types.
"""
import logging
from typing import Dict, List, Optional
from datetime import datetime
from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.types import (
    StructType, StructField, StringType, IntegerType, 
    FloatType, TimestampType
)
from pyspark.sql import functions as F

logger = logging.getLogger(__name__)


# Schema definitions for each DWD product type
SCHEMA_DEFINITIONS = {
    "air_temperature": StructType([
        StructField("STATIONS_ID", IntegerType(), False),
        StructField("MESS_DATUM", StringType(), False),
        StructField("QN_9", IntegerType(), True),
        StructField("TT_TU", FloatType(), True),
        StructField("RF_TU", FloatType(), True),
    ]),
    "precipitation": StructType([
        StructField("STATIONS_ID", IntegerType(), False),
        StructField("MESS_DATUM", StringType(), False),
        StructField("QN_8", IntegerType(), True),
        StructField("R1", FloatType(), True),
        StructField("RS_IND", IntegerType(), True),
        StructField("WRTR", IntegerType(), True),
    ]),
    "wind": StructType([
        StructField("STATIONS_ID", IntegerType(), False),
        StructField("MESS_DATUM", StringType(), False),
        StructField("QN_3", IntegerType(), True),
        StructField("F", FloatType(), True),
        StructField("D", IntegerType(), True),
    ]),
    "pressure": StructType([
        StructField("STATIONS_ID", IntegerType(), False),
        StructField("MESS_DATUM", StringType(), False),
        StructField("QN_8", IntegerType(), True),
        StructField("P", FloatType(), True),
        StructField("P0", FloatType(), True),
    ]),
    "moisture": StructType([
        StructField("STATIONS_ID", IntegerType(), False),
        StructField("MESS_DATUM", StringType(), False),
        StructField("QN_4", IntegerType(), True),
        StructField("RF_TU", FloatType(), True),
        StructField("TF_TU", FloatType(), True),
    ]),
    "cloud_cover": StructType([
        StructField("STATIONS_ID", IntegerType(), False),
        StructField("MESS_DATUM", StringType(), False),
        StructField("QN_8", IntegerType(), True),
        StructField("V_N", FloatType(), True),
        StructField("V_N_I", StringType(), True),
    ]),
}


class DWDParser:
    """Parser for DWD semicolon-delimited text files"""
    
    def __init__(self, spark: SparkSession, product_type: str):
        """
        Initialize parser
        
        Args:
            spark: SparkSession instance
            product_type: One of the keys in SCHEMA_DEFINITIONS
        """
        self.spark = spark
        self.product_type = product_type
        
        if product_type not in SCHEMA_DEFINITIONS:
            raise ValueError(
                f"Unknown product type: {product_type}. "
                f"Must be one of {list(SCHEMA_DEFINITIONS.keys())}"
            )
        
        self.schema = SCHEMA_DEFINITIONS[product_type]
        logger.info(f"Initialized DWDParser for product: {product_type}")
    
    def parse_file(self, s3_path: str) -> DataFrame:
        """
        Parse a single DWD text file from S3
        
        Args:
            s3_path: Full S3 path to file (e.g., s3a://bucket/path/file.txt)
        
        Returns:
            Spark DataFrame with validated schema
        """
        logger.info(f"Parsing file: {s3_path}")
        
        try:
            # Read CSV with semicolon delimiter
            df = self.spark.read.csv(
                s3_path,
                sep=";",
                header=True,
                schema=self.schema,
                encoding="ISO-8859-1",
                mode="PERMISSIVE",  # Return null for corrupt records
                ignoreLeadingWhiteSpace=True,
                ignoreTrailingWhiteSpace=True
            )
            
            # Add file metadata
            df = df.withColumn("_source_file", F.lit(s3_path))
            df = df.withColumn("_parsed_at", F.current_timestamp())
            
            # Convert MESS_DATUM string to proper timestamp
            df = df.withColumn(
                "timestamp",
                F.to_timestamp(F.col("MESS_DATUM"), "yyyyMMddHH")
            )
            
            # Validate row count
            row_count = df.count()
            logger.info(f"Parsed {row_count} rows from {s3_path}")
            
            if row_count == 0:
                logger.warning(f"No data rows found in {s3_path}")
            
            return df
            
        except Exception as e:
            logger.error(f"Failed to parse {s3_path}: {e}")
            raise
    
    def parse_directory(self, s3_prefix: str) -> DataFrame:
        """
        Parse all text files in an S3 directory
        
        Args:
            s3_prefix: S3 prefix (e.g., s3a://bucket/raw/dwd/air_temperature/)
        
        Returns:
            Unified DataFrame from all files
        """
        logger.info(f"Parsing directory: {s3_prefix}")
        
        try:
            # Read all CSV files matching pattern
            pattern = f"{s3_prefix}/**/*.txt"
            
            df = self.spark.read.csv(
                pattern,
                sep=";",
                header=True,
                schema=self.schema,
                encoding="ISO-8859-1",
                mode="PERMISSIVE",
                ignoreLeadingWhiteSpace=True,
                ignoreTrailingWhiteSpace=True
            )
            
            # Add metadata
            df = df.withColumn("_source_prefix", F.lit(s3_prefix))
            df = df.withColumn("_parsed_at", F.current_timestamp())
            
            # Convert timestamp
            df = df.withColumn(
                "timestamp",
                F.to_timestamp(F.col("MESS_DATUM"), "yyyyMMddHH")
            )
            
            row_count = df.count()
            logger.info(f"Parsed {row_count} total rows from {s3_prefix}")
            
            return df
            
        except Exception as e:
            logger.error(f"Failed to parse directory {s3_prefix}: {e}")
            raise
    
    def validate_data(self, df: DataFrame) -> Dict[str, any]:
        """
        Validate parsed data and collect quality metrics
        
        Args:
            df: Parsed DataFrame
        
        Returns:
            Dictionary with validation metrics
        """
        logger.info("Validating parsed data")
        
        metrics = {
            "total_rows": df.count(),
            "null_counts": {},
            "distinct_stations": None,
            "date_range": {},
        }
        
        # Count nulls per column
        for field in self.schema.fields:
            col_name = field.name
            if field.nullable:
                null_count = df.filter(F.col(col_name).isNull()).count()
                metrics["null_counts"][col_name] = null_count
        
        # Distinct stations
        if "STATIONS_ID" in df.columns:
            metrics["distinct_stations"] = df.select("STATIONS_ID").distinct().count()
        
        # Date range
        if "timestamp" in df.columns:
            date_stats = df.agg(
                F.min("timestamp").alias("min_date"),
                F.max("timestamp").alias("max_date")
            ).collect()[0]
            metrics["date_range"] = {
                "min": date_stats["min_date"],
                "max": date_stats["max_date"]
            }
        
        logger.info(f"Validation metrics: {metrics}")
        return metrics


def create_parser(spark: SparkSession, product_type: str) -> DWDParser:
    """
    Factory function to create a parser instance
    
    Args:
        spark: SparkSession
        product_type: Product type (air_temperature, precipitation, etc.)
    
    Returns:
        DWDParser instance
    """
    return DWDParser(spark, product_type)
