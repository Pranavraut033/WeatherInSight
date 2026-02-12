"""
Feature calculators for quarterly aggregations.

Each calculator takes a PySpark DataFrame of cleaned hourly observations
and computes quarterly statistical features matching the curated schema.
"""
from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql.window import Window


def calculate_temperature_features(df: DataFrame) -> DataFrame:
    """
    Calculate quarterly temperature features from air_temperature product.
    
    Expected input columns:
    - STATIONS_ID, timestamp, year, quarter, month, day, hour
    - TT_TU: air temperature (°C)
    - RF_TU: relative humidity (%)
    - quality_acceptable, dataset_version
    
    Returns DataFrame with columns matching quarterly_temperature_features schema:
    - station_id, year, quarter
    - temp_mean_c, temp_median_c, temp_min_c, temp_max_c, temp_stddev_c
    - temp_q25_c, temp_q75_c
    - heating_degree_days, cooling_degree_days
    - frost_hours, freeze_thaw_cycles
    - count_observations, count_missing, missingness_ratio
    """
    # Filter to quality-acceptable records only
    df = df.filter(F.col("quality_acceptable") == True)
    
    # Group by station, year, quarter
    grouped = df.groupBy("STATIONS_ID", "year", "quarter", "dataset_version")
    
    # Calculate basic temperature statistics
    stats = grouped.agg(
        # Temperature statistics
        F.mean("TT_TU").alias("temp_mean_c"),
        F.expr("percentile_approx(TT_TU, 0.5)").alias("temp_median_c"),
        F.min("TT_TU").alias("temp_min_c"),
        F.max("TT_TU").alias("temp_max_c"),
        F.stddev("TT_TU").alias("temp_stddev_c"),
        F.expr("percentile_approx(TT_TU, 0.25)").alias("temp_q25_c"),
        F.expr("percentile_approx(TT_TU, 0.75)").alias("temp_q75_c"),
        
        # Frost hours (temp < 0°C)
        F.sum(F.when(F.col("TT_TU") < 0, 1).otherwise(0)).alias("frost_hours"),
        
        # Observation counts
        F.count("TT_TU").alias("count_observations"),
        F.sum(F.when(F.col("TT_TU").isNull(), 1).otherwise(0)).alias("count_missing")
    )
    
    # Calculate heating and cooling degree days
    # Need daily mean temperatures first
    daily_temps = df.groupBy("STATIONS_ID", "year", "quarter", "dataset_version", "month", "day").agg(
        F.mean("TT_TU").alias("daily_mean_temp")
    )
    
    # HDD: sum of max(18 - daily_mean, 0) per day
    # CDD: sum of max(daily_mean - 18, 0) per day
    degree_days = daily_temps.groupBy("STATIONS_ID", "year", "quarter", "dataset_version").agg(
        F.sum(F.when(F.col("daily_mean_temp") < 18, 18 - F.col("daily_mean_temp")).otherwise(0)).alias("heating_degree_days"),
        F.sum(F.when(F.col("daily_mean_temp") > 18, F.col("daily_mean_temp") - 18).otherwise(0)).alias("cooling_degree_days")
    )
    
    # Calculate freeze-thaw cycles (days crossing 0°C)
    daily_extremes = df.groupBy("STATIONS_ID", "year", "quarter", "dataset_version", "month", "day").agg(
        F.min("TT_TU").alias("daily_min_temp"),
        F.max("TT_TU").alias("daily_max_temp")
    )
    
    freeze_thaw = daily_extremes.groupBy("STATIONS_ID", "year", "quarter", "dataset_version").agg(
        F.sum(
            F.when((F.col("daily_min_temp") < 0) & (F.col("daily_max_temp") > 0), 1)
            .otherwise(0)
        ).alias("freeze_thaw_cycles")
    )
    
    # Join all features together
    result = stats.join(degree_days, on=["STATIONS_ID", "year", "quarter", "dataset_version"], how="left")
    result = result.join(freeze_thaw, on=["STATIONS_ID", "year", "quarter", "dataset_version"], how="left")
    
    # Calculate missingness ratio
    result = result.withColumn(
        "missingness_ratio",
        F.col("count_missing") / (F.col("count_observations") + F.col("count_missing"))
    )
    
    # Rename STATIONS_ID to station_id for consistency
    result = result.withColumnRenamed("STATIONS_ID", "station_id")
    
    return result


def calculate_precipitation_features(df: DataFrame) -> DataFrame:
    """
    Calculate quarterly precipitation features from precipitation product.
    
    Expected input columns:
    - STATIONS_ID, timestamp, year, quarter, month, day, hour
    - R1: precipitation amount (mm)
    - RS_IND: precipitation indicator
    - quality_acceptable, dataset_version
    
    Returns DataFrame with columns matching quarterly_precipitation_features schema.
    """
    df = df.filter(F.col("quality_acceptable") == True)
    
    grouped = df.groupBy("STATIONS_ID", "year", "quarter", "dataset_version")
    
    # Calculate precipitation statistics
    stats = grouped.agg(
        # Precipitation statistics
        F.sum("R1").alias("precip_total_mm"),
        F.mean("R1").alias("precip_mean_mm"),
        F.expr("percentile_approx(R1, 0.5)").alias("precip_median_mm"),
        F.max("R1").alias("precip_max_mm"),
        F.stddev("R1").alias("precip_stddev_mm"),
        F.expr("percentile_approx(R1, 0.75)").alias("precip_q75_mm"),
        F.expr("percentile_approx(R1, 0.95)").alias("precip_q95_mm"),
        
        # Wet/dry hours (assuming R1 > 0 means wet)
        F.sum(F.when(F.col("R1") > 0, 1).otherwise(0)).alias("wet_hours"),
        F.sum(F.when(F.col("R1") <= 0, 1).otherwise(0)).alias("dry_hours"),
        
        # Heavy precipitation hours (> 2.5mm/hour as threshold)
        F.sum(F.when(F.col("R1") > 2.5, 1).otherwise(0)).alias("heavy_precip_hours"),
        
        # Observation counts
        F.count("R1").alias("count_observations"),
        F.sum(F.when(F.col("R1").isNull(), 1).otherwise(0)).alias("count_missing")
    )
    
    # Calculate wet and dry spells (consecutive hours)
    # Add a wet/dry indicator
    spell_df = df.withColumn("is_wet", F.when(F.col("R1") > 0, 1).otherwise(0))
    
    # Use window function to identify spell changes
    window_spec = Window.partitionBy("STATIONS_ID", "year", "quarter", "dataset_version").orderBy("timestamp")
    spell_df = spell_df.withColumn("prev_wet", F.lag("is_wet").over(window_spec))
    spell_df = spell_df.withColumn("spell_change", F.when(F.col("is_wet") != F.col("prev_wet"), 1).otherwise(0))
    spell_df = spell_df.withColumn("spell_id", F.sum("spell_change").over(window_spec))
    
    # Calculate spell lengths
    spell_lengths = spell_df.groupBy("STATIONS_ID", "year", "quarter", "dataset_version", "spell_id", "is_wet").agg(
        F.count("*").alias("spell_length")
    )
    
    # Get max wet and dry spell lengths
    max_wet_spell = spell_lengths.filter(F.col("is_wet") == 1).groupBy("STATIONS_ID", "year", "quarter", "dataset_version").agg(
        F.max("spell_length").alias("max_wet_spell_hours")
    )
    
    max_dry_spell = spell_lengths.filter(F.col("is_wet") == 0).groupBy("STATIONS_ID", "year", "quarter", "dataset_version").agg(
        F.max("spell_length").alias("max_dry_spell_hours")
    )
    
    # Join all features
    result = stats.join(max_wet_spell, on=["STATIONS_ID", "year", "quarter", "dataset_version"], how="left")
    result = result.join(max_dry_spell, on=["STATIONS_ID", "year", "quarter", "dataset_version"], how="left")
    
    # Calculate missingness ratio
    result = result.withColumn(
        "missingness_ratio",
        F.col("count_missing") / (F.col("count_observations") + F.col("count_missing"))
    )
    
    result = result.withColumnRenamed("STATIONS_ID", "station_id")
    
    return result


def calculate_wind_features(df: DataFrame) -> DataFrame:
    """
    Calculate quarterly wind features from wind product.
    
    Expected input columns:
    - STATIONS_ID, timestamp, year, quarter
    - F: wind speed (m/s)
    - D: wind direction (degrees, 0-360)
    - quality_acceptable, dataset_version
    
    Returns DataFrame with columns matching quarterly_wind_features schema.
    """
    df = df.filter(F.col("quality_acceptable") == True)
    
    grouped = df.groupBy("STATIONS_ID", "year", "quarter", "dataset_version")
    
    # Calculate wind speed statistics
    stats = grouped.agg(
        # Wind speed statistics
        F.mean("F").alias("wind_speed_mean_mps"),
        F.expr("percentile_approx(F, 0.5)").alias("wind_speed_median_mps"),
        F.min("F").alias("wind_speed_min_mps"),
        F.max("F").alias("wind_speed_max_mps"),
        F.stddev("F").alias("wind_speed_stddev_mps"),
        F.expr("percentile_approx(F, 0.75)").alias("wind_speed_q75_mps"),
        F.expr("percentile_approx(F, 0.95)").alias("wind_speed_q95_mps"),
        
        # Gust hours (wind speed > 10.8 m/s = Beaufort 6)
        F.sum(F.when(F.col("F") > 10.8, 1).otherwise(0)).alias("gust_hours"),
        
        # Calm hours (wind speed < 0.3 m/s)
        F.sum(F.when(F.col("F") < 0.3, 1).otherwise(0)).alias("calm_hours"),
        
        # Observation counts
        F.count("F").alias("count_observations"),
        F.sum(F.when(F.col("F").isNull(), 1).otherwise(0)).alias("count_missing")
    )
    
    # Calculate prevailing wind direction (mode of 16 compass bins)
    # Bin directions into 16 sectors (22.5° each)
    direction_df = df.withColumn(
        "direction_bin",
        F.floor((F.col("D") + 11.25) / 22.5) % 16
    )
    
    direction_mode = direction_df.groupBy("STATIONS_ID", "year", "quarter", "dataset_version", "direction_bin").agg(
        F.count("*").alias("bin_count")
    )
    
    # Get the most frequent bin
    window_spec = Window.partitionBy("STATIONS_ID", "year", "quarter", "dataset_version").orderBy(F.desc("bin_count"))
    prevailing = direction_mode.withColumn("rank", F.row_number().over(window_spec))
    prevailing = prevailing.filter(F.col("rank") == 1).select(
        "STATIONS_ID", "year", "quarter", "dataset_version",
        (F.col("direction_bin") * 22.5).alias("prevailing_direction")
    )
    
    # Calculate direction variability (circular standard deviation approximation)
    # Using coefficient of variation of directional components
    direction_stats = df.groupBy("STATIONS_ID", "year", "quarter", "dataset_version").agg(
        F.stddev(F.sin(F.radians(F.col("D")))).alias("sin_stddev"),
        F.stddev(F.cos(F.radians(F.col("D")))).alias("cos_stddev")
    )
    
    direction_stats = direction_stats.withColumn(
        "direction_variability",
        F.sqrt(F.col("sin_stddev") ** 2 + F.col("cos_stddev") ** 2)
    )
    
    # Join all features
    result = stats.join(prevailing, on=["STATIONS_ID", "year", "quarter", "dataset_version"], how="left")
    result = result.join(
        direction_stats.select("STATIONS_ID", "year", "quarter", "dataset_version", "direction_variability"),
        on=["STATIONS_ID", "year", "quarter", "dataset_version"],
        how="left"
    )
    
    # Calculate missingness ratio
    result = result.withColumn(
        "missingness_ratio",
        F.col("count_missing") / (F.col("count_observations") + F.col("count_missing"))
    )
    
    result = result.withColumnRenamed("STATIONS_ID", "station_id")
    
    return result


def calculate_pressure_features(df: DataFrame) -> DataFrame:
    """
    Calculate quarterly pressure features from pressure product.
    
    Expected input columns:
    - STATIONS_ID, timestamp, year, quarter
    - P: station pressure (hPa) or P_pa (Pa)
    - P0: sea-level pressure (hPa) or P0_pa (Pa)
    - quality_acceptable, dataset_version
    
    Returns DataFrame with columns matching quarterly_pressure_features schema.
    """
    df = df.filter(F.col("quality_acceptable") == True)
    
    # Use P_pa if available, otherwise P (convert from hPa to Pa)
    df = df.withColumn(
        "pressure_pa",
        F.coalesce(F.col("P_pa"), F.col("P") * 100)
    )
    
    grouped = df.groupBy("STATIONS_ID", "year", "quarter", "dataset_version")
    
    # Calculate pressure statistics (in Pa)
    stats = grouped.agg(
        # Pressure statistics
        F.mean("pressure_pa").alias("pressure_mean_pa"),
        F.expr("percentile_approx(pressure_pa, 0.5)").alias("pressure_median_pa"),
        F.min("pressure_pa").alias("pressure_min_pa"),
        F.max("pressure_pa").alias("pressure_max_pa"),
        F.stddev("pressure_pa").alias("pressure_stddev_pa"),
        F.expr("percentile_approx(pressure_pa, 0.25)").alias("pressure_q25_pa"),
        F.expr("percentile_approx(pressure_pa, 0.75)").alias("pressure_q75_pa"),
        
        # High pressure hours (> 102000 Pa = 1020 hPa)
        F.sum(F.when(F.col("pressure_pa") > 102000, 1).otherwise(0)).alias("high_pressure_hours"),
        
        # Low pressure hours (< 99000 Pa = 990 hPa)
        F.sum(F.when(F.col("pressure_pa") < 99000, 1).otherwise(0)).alias("low_pressure_hours"),
        
        # Observation counts
        F.count("pressure_pa").alias("count_observations"),
        F.sum(F.when(F.col("pressure_pa").isNull(), 1).otherwise(0)).alias("count_missing")
    )
    
    # Calculate pressure range
    stats = stats.withColumn(
        "pressure_range_pa",
        F.col("pressure_max_pa") - F.col("pressure_min_pa")
    )
    
    # Calculate missingness ratio
    stats = stats.withColumn(
        "missingness_ratio",
        F.col("count_missing") / (F.col("count_observations") + F.col("count_missing"))
    )
    
    stats = stats.withColumnRenamed("STATIONS_ID", "station_id")
    
    return stats


def calculate_humidity_features(df: DataFrame) -> DataFrame:
    """
    Calculate quarterly humidity features from moisture product.
    
    Expected input columns:
    - STATIONS_ID, timestamp, year, quarter
    - RF_TU: relative humidity (%)
    - TF_TU: dew point temperature (°C) - not directly used in current schema
    - quality_acceptable, dataset_version
    
    Returns DataFrame with columns matching quarterly_humidity_features schema.
    """
    df = df.filter(F.col("quality_acceptable") == True)
    
    grouped = df.groupBy("STATIONS_ID", "year", "quarter", "dataset_version")
    
    # Calculate humidity statistics
    stats = grouped.agg(
        # Humidity statistics
        F.mean("RF_TU").alias("humidity_mean_pct"),
        F.expr("percentile_approx(RF_TU, 0.5)").alias("humidity_median_pct"),
        F.min("RF_TU").alias("humidity_min_pct"),
        F.max("RF_TU").alias("humidity_max_pct"),
        F.stddev("RF_TU").alias("humidity_stddev_pct"),
        F.expr("percentile_approx(RF_TU, 0.25)").alias("humidity_q25_pct"),
        F.expr("percentile_approx(RF_TU, 0.75)").alias("humidity_q75_pct"),
        
        # High humidity hours (> 80%)
        F.sum(F.when(F.col("RF_TU") > 80, 1).otherwise(0)).alias("high_humidity_hours"),
        
        # Low humidity hours (< 30%)
        F.sum(F.when(F.col("RF_TU") < 30, 1).otherwise(0)).alias("low_humidity_hours"),
        
        # Observation counts
        F.count("RF_TU").alias("count_observations"),
        F.sum(F.when(F.col("RF_TU").isNull(), 1).otherwise(0)).alias("count_missing")
    )
    
    # Calculate missingness ratio
    stats = stats.withColumn(
        "missingness_ratio",
        F.col("count_missing") / (F.col("count_observations") + F.col("count_missing"))
    )
    
    stats = stats.withColumnRenamed("STATIONS_ID", "station_id")
    
    return stats
