"""
Main aggregation logic for computing quarterly features from staged data.
"""
from datetime import datetime
from typing import Optional

import psycopg2
from pyspark.sql import SparkSession, DataFrame
from pyspark.sql import functions as F

from .config import AggregationConfig
from .feature_calculators import (
    calculate_temperature_features,
    calculate_precipitation_features,
    calculate_wind_features,
    calculate_pressure_features,
    calculate_humidity_features,
)


class QuarterlyAggregator:
    """Aggregates staged hourly data into quarterly features."""
    
    def __init__(self, config: AggregationConfig, spark: SparkSession):
        """
        Initialize aggregator.
        
        Args:
            config: Configuration object
            spark: Active SparkSession
        """
        self.config = config
        self.spark = spark
        self._station_metadata_cache: Optional[DataFrame] = None
    
    def load_station_metadata(self) -> DataFrame:
        """
        Load station metadata from PostgreSQL and broadcast to cluster.
        
        Returns:
            DataFrame with columns: station_id, station_name, latitude, longitude, elevation_m
        """
        if self._station_metadata_cache is not None:
            return self._station_metadata_cache
        
        # Read station metadata from PostgreSQL
        metadata_df = self.spark.read.jdbc(
            url=self.config.postgres_jdbc_url,
            table="station_metadata",
            properties=self.config.jdbc_properties
        )
        
        # Select and rename columns as needed
        metadata_df = metadata_df.select(
            F.col("station_id"),
            F.col("name").alias("station_name"),
            F.col("latitude"),
            F.col("longitude"),
            F.col("elevation_m")
        )
        
        # Broadcast small table for efficient joins
        self._station_metadata_cache = F.broadcast(metadata_df)
        
        return self._station_metadata_cache
    
    def load_staged_data(
        self,
        product_type: str,
        year: int,
        quarter: int,
        dataset_version: str
    ) -> DataFrame:
        """
        Load staged parquet data for a specific product, year, and quarter.
        
        Args:
            product_type: Product type (e.g., 'air_temperature')
            year: Year to load
            quarter: Quarter (1-4)
            dataset_version: Dataset version identifier
        
        Returns:
            DataFrame with hourly observations
        """
        # Determine quarter date boundaries
        quarter_months = {
            1: (1, 2, 3),
            2: (4, 5, 6),
            3: (7, 8, 9),
            4: (10, 11, 12)
        }
        
        months = quarter_months[quarter]
        
        # Build path to staged data
        staged_path = f"{self.config.staging_path}/{product_type}"
        
        # Read parquet data
        df = self.spark.read.parquet(staged_path)
        
        # Filter by year, quarter, and dataset version
        df = df.filter(
            (F.col("year") == year) &
            (F.col("quarter") == quarter) &
            (F.col("dataset_version") == dataset_version)
        )
        
        return df
    
    def compute_quarterly_features(
        self,
        product_type: str,
        year: int,
        quarter: int,
        dataset_version: str
    ) -> DataFrame:
        """
        Compute quarterly features for a given product type and time period.
        
        Args:
            product_type: Product type to aggregate
            year: Year
            quarter: Quarter (1-4)
            dataset_version: Dataset version from staged data
        
        Returns:
            DataFrame with quarterly features including station metadata
        """
        # Load staged data
        staged_df = self.load_staged_data(product_type, year, quarter, dataset_version)
        
        # Select appropriate feature calculator
        calculator_map = {
            "air_temperature": calculate_temperature_features,
            "precipitation": calculate_precipitation_features,
            "wind": calculate_wind_features,
            "pressure": calculate_pressure_features,
            "moisture": calculate_humidity_features,
        }
        
        if product_type not in calculator_map:
            raise ValueError(f"Unknown product type: {product_type}")
        
        calculator = calculator_map[product_type]
        
        # Compute features
        features_df = calculator(staged_df)
        
        # Load and join station metadata
        station_metadata = self.load_station_metadata()
        
        features_with_metadata = features_df.join(
            station_metadata,
            on="station_id",
            how="left"
        )
        
        # Add quarter boundaries
        quarter_start_month = (quarter - 1) * 3 + 1
        quarter_end_month = quarter * 3
        
        # Determine last day of quarter end month
        if quarter_end_month in [1, 3, 5, 7, 8, 10, 12]:
            last_day = 31
        elif quarter_end_month in [4, 6, 9, 11]:
            last_day = 30
        else:  # February
            # Simple leap year check
            if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0):
                last_day = 29
            else:
                last_day = 28
        
        features_with_metadata = features_with_metadata.withColumn(
            "quarter_start",
            F.lit(f"{year}-{quarter_start_month:02d}-01 00:00:00").cast("timestamp")
        )
        
        features_with_metadata = features_with_metadata.withColumn(
            "quarter_end",
            F.lit(f"{year}-{quarter_end_month:02d}-{last_day} 23:59:59").cast("timestamp")
        )
        
        # Add computed_at timestamp
        features_with_metadata = features_with_metadata.withColumn(
            "computed_at",
            F.lit(datetime.utcnow()).cast("timestamp")
        )
        
        return features_with_metadata
