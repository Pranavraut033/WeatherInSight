"""
Data cleaning and normalization

Handles missing values, unit conversion, outlier detection,
and quality flag enforcement.
"""
import logging
from typing import Dict, List
from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql.types import FloatType

logger = logging.getLogger(__name__)


# Missing value sentinels per DWD documentation
MISSING_VALUES = [-999, -999.0]


class DataCleaner:
    """Data cleaning and normalization for DWD observations"""
    
    def __init__(self, product_type: str, quality_threshold: int = 5):
        """
        Initialize cleaner
        
        Args:
            product_type: Product type (air_temperature, precipitation, etc.)
            quality_threshold: Minimum quality flag value (1-10)
        """
        self.product_type = product_type
        self.quality_threshold = quality_threshold
        logger.info(
            f"Initialized DataCleaner for {product_type}, "
            f"quality threshold: {quality_threshold}"
        )
    
    def clean(self, df: DataFrame) -> DataFrame:
        """
        Main cleaning pipeline
        
        Args:
            df: Raw parsed DataFrame
        
        Returns:
            Cleaned DataFrame with nulls, normalized units, flags
        """
        logger.info(f"Starting cleaning pipeline for {self.product_type}")
        
        df = self._handle_missing_values(df)
        df = self._filter_by_quality(df)
        df = self._normalize_units(df)
        df = self._detect_outliers(df)
        df = self._add_processing_metadata(df)
        
        logger.info("Cleaning pipeline complete")
        return df
    
    def _handle_missing_values(self, df: DataFrame) -> DataFrame:
        """
        Replace sentinel values with NULL
        
        DWD uses -999 or blank for missing data.
        Convert these to proper nulls.
        """
        logger.info("Handling missing values")
        
        # Get numeric columns
        numeric_cols = [
            f.name for f in df.schema.fields 
            if isinstance(f.dataType, FloatType) or f.name.startswith("QN_")
        ]
        
        for col in numeric_cols:
            if col in df.columns:
                # Replace -999 with null
                df = df.withColumn(
                    col,
                    F.when(F.col(col).isin(MISSING_VALUES), None).otherwise(F.col(col))
                )
        
        return df
    
    def _filter_by_quality(self, df: DataFrame) -> DataFrame:
        """
        Filter or flag rows based on quality indicators
        
        Quality flags (QN_*):
        - 1-4: Poor quality
        - 5-7: Acceptable
        - 8-10: Good quality
        """
        logger.info(f"Filtering by quality threshold: {self.quality_threshold}")
        
        # Find quality flag column
        qn_cols = [c for c in df.columns if c.startswith("QN_")]
        
        if not qn_cols:
            logger.warning("No quality flag column found, skipping quality filter")
            return df
        
        qn_col = qn_cols[0]  # Use first QN column
        
        # Add quality flag
        df = df.withColumn(
            "quality_acceptable",
            F.when(F.col(qn_col) >= self.quality_threshold, True).otherwise(False)
        )
        
        # Log quality statistics
        total = df.count()
        acceptable = df.filter(F.col("quality_acceptable") == True).count()
        logger.info(
            f"Quality stats: {acceptable}/{total} rows "
            f"({100*acceptable/total:.1f}%) meet threshold"
        )
        
        return df
    
    def _normalize_units(self, df: DataFrame) -> DataFrame:
        """
        Normalize units to standard SI where needed
        
        Most DWD data is already in SI units, but we ensure consistency:
        - Temperature: °C (already standard)
        - Pressure: hPa → Pa (multiply by 100)
        - Wind speed: m/s (already standard)
        - Precipitation: mm (already standard)
        """
        logger.info("Normalizing units")
        
        if self.product_type == "pressure":
            # Convert hPa to Pa
            if "P" in df.columns:
                df = df.withColumn("P_pa", F.col("P") * 100)
            if "P0" in df.columns:
                df = df.withColumn("P0_pa", F.col("P0") * 100)
        
        # Add normalized timestamp components for partitioning
        df = df.withColumn("year", F.year("timestamp"))
        df = df.withColumn("month", F.month("timestamp"))
        df = df.withColumn("day", F.dayofmonth("timestamp"))
        df = df.withColumn("hour", F.hour("timestamp"))
        
        return df
    
    def _detect_outliers(self, df: DataFrame) -> DataFrame:
        """
        Detect and flag statistical outliers
        
        Uses simple range checks based on physical limits:
        - Temperature: -60°C to 60°C
        - Pressure: 850 hPa to 1100 hPa
        - Wind speed: 0 to 150 m/s
        - Precipitation: 0 to 200 mm/hour
        - Humidity: 0 to 100%
        """
        logger.info("Detecting outliers")
        
        # Define outlier conditions per product type
        outlier_conditions = {
            "air_temperature": {
                "TT_TU": (F.col("TT_TU") < -60) | (F.col("TT_TU") > 60),
                "RF_TU": (F.col("RF_TU") < 0) | (F.col("RF_TU") > 100),
            },
            "precipitation": {
                "R1": (F.col("R1") < 0) | (F.col("R1") > 200),
            },
            "wind": {
                "F": (F.col("F") < 0) | (F.col("F") > 150),
                "D": (F.col("D") < 0) | (F.col("D") > 360),
            },
            "pressure": {
                "P": (F.col("P") < 850) | (F.col("P") > 1100),
                "P0": (F.col("P0") < 850) | (F.col("P0") > 1100),
            },
            "moisture": {
                "RF_TU": (F.col("RF_TU") < 0) | (F.col("RF_TU") > 100),
                "TF_TU": (F.col("TF_TU") < -60) | (F.col("TF_TU") > 60),
            },
        }
        
        if self.product_type not in outlier_conditions:
            logger.info(f"No outlier rules defined for {self.product_type}")
            df = df.withColumn("has_outlier", F.lit(False))
            return df
        
        # Build combined outlier condition
        conditions = outlier_conditions[self.product_type]
        combined_condition = None
        
        for col_name, condition in conditions.items():
            if col_name in df.columns:
                if combined_condition is None:
                    combined_condition = condition
                else:
                    combined_condition = combined_condition | condition
        
        if combined_condition is not None:
            df = df.withColumn("has_outlier", combined_condition)
            
            # Log outlier statistics
            outlier_count = df.filter(F.col("has_outlier") == True).count()
            total = df.count()
            logger.info(
                f"Outliers detected: {outlier_count}/{total} rows "
                f"({100*outlier_count/total:.2f}%)"
            )
        else:
            df = df.withColumn("has_outlier", F.lit(False))
        
        return df
    
    def _add_processing_metadata(self, df: DataFrame) -> DataFrame:
        """Add metadata columns for traceability"""
        df = df.withColumn("cleaned_at", F.current_timestamp())
        df = df.withColumn("product_type", F.lit(self.product_type))
        return df
    
    def compute_quality_metrics(self, df: DataFrame) -> Dict[str, any]:
        """
        Compute data quality metrics for cleaned data
        
        Returns:
            Dictionary with quality statistics
        """
        logger.info("Computing quality metrics")
        
        total = df.count()
        
        metrics = {
            "total_rows": total,
            "rows_with_outliers": df.filter(F.col("has_outlier") == True).count(),
            "rows_acceptable_quality": df.filter(
                F.col("quality_acceptable") == True
            ).count(),
        }
        
        # Compute missingness per numeric column
        numeric_cols = [
            f.name for f in df.schema.fields 
            if isinstance(f.dataType, FloatType) 
            and not f.name.startswith("_")
            and f.name not in ["year", "month", "day", "hour"]
        ]
        
        metrics["missingness"] = {}
        for col in numeric_cols:
            if col in df.columns:
                missing = df.filter(F.col(col).isNull()).count()
                ratio = missing / total if total > 0 else 0
                metrics["missingness"][col] = {
                    "count": missing,
                    "ratio": round(ratio, 4)
                }
        
        logger.info(f"Quality metrics: {metrics}")
        return metrics


def create_cleaner(product_type: str, quality_threshold: int = 5) -> DataCleaner:
    """
    Factory function to create a cleaner instance
    
    Args:
        product_type: Product type (air_temperature, precipitation, etc.)
        quality_threshold: Minimum quality flag value (default 5)
    
    Returns:
        DataCleaner instance
    """
    return DataCleaner(product_type, quality_threshold)
