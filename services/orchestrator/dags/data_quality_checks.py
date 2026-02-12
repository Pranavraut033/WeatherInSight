"""
WeatherInsight Data Quality Checks DAG

Runs data quality validation after aggregation completes.
Can be triggered manually or scheduled to run after quarterly pipeline.

Checks performed:
1. Row count validation (min threshold per quarter)
2. Null percentage checks (max threshold for critical columns)
3. Station coverage validation (min stations per quarter)
4. Metadata consistency checks (version tracking)
5. Temporal continuity checks (no missing quarters)

Alerts are sent via email/Slack on threshold violations.
"""

from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator
from airflow.providers.postgres.operators.postgres import PostgresOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.models import Variable
import yaml
import os

# Load DAG configuration
config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'dag_config.yaml')
with open(config_path, 'r') as f:
    config = yaml.safe_load(f)

# Default arguments
default_args = {
    'owner': 'weatherinsight',
    'depends_on_past': False,
    'email': config['email']['recipients'],
    'email_on_failure': True,  # Always alert on quality failures
    'email_on_retry': False,
    'retries': config['retries']['data_quality'],
    'retry_delay': timedelta(minutes=config['retry_delay']['minutes']),
}

# Create DAG
dag = DAG(
    'weatherinsight_data_quality',
    default_args=default_args,
    description='Data quality validation for WeatherInsight curated features',
    schedule_interval='0 6 1 1,4,7,10 *',  # 6 hours after quarterly pipeline
    start_date=datetime(2020, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=['weatherinsight', 'data-quality', 'monitoring'],
)


def check_row_counts(**context):
    """Validate minimum row counts for all feature tables."""
    pg_hook = PostgresHook(postgres_conn_id='weatherinsight_postgres')
    min_rows = config['quality_thresholds']['min_rows_per_quarter']
    
    tables = [
        'quarterly_temperature_features',
        'quarterly_precipitation_features',
        'quarterly_wind_features',
        'quarterly_pressure_features',
        'quarterly_humidity_features',
    ]
    
    issues = []
    
    for table in tables:
        query = f"""
        SELECT year, quarter, COUNT(*) as row_count
        FROM {table}
        GROUP BY year, quarter
        HAVING COUNT(*) < {min_rows}
        ORDER BY year DESC, quarter DESC
        LIMIT 10
        """
        
        results = pg_hook.get_records(query)
        
        if results:
            for year, quarter, count in results:
                issues.append(f"{table}: {year}Q{quarter} has only {count} rows (min: {min_rows})")
    
    if issues:
        error_msg = "Row count validation FAILED:\n" + "\n".join(issues)
        print(error_msg)
        raise ValueError(error_msg)
    
    print(f"✓ Row count validation passed: All quarters have >= {min_rows} rows")


def check_null_percentages(**context):
    """Validate null percentages for critical columns."""
    pg_hook = PostgresHook(postgres_conn_id='weatherinsight_postgres')
    max_null_pct = config['quality_thresholds']['max_null_percentage']
    
    # Define critical columns per table
    critical_columns = {
        'quarterly_temperature_features': ['temp_mean_c', 'temp_min_c', 'temp_max_c'],
        'quarterly_precipitation_features': ['precip_sum_mm', 'precip_mean_mm'],
        'quarterly_wind_features': ['wind_mean_ms', 'wind_max_ms'],
        'quarterly_pressure_features': ['pressure_mean_hpa'],
        'quarterly_humidity_features': ['humidity_mean_pct'],
    }
    
    issues = []
    
    for table, columns in critical_columns.items():
        for column in columns:
            query = f"""
            SELECT 
                year,
                quarter,
                ROUND(100.0 * SUM(CASE WHEN {column} IS NULL THEN 1 ELSE 0 END) / COUNT(*), 2) as null_pct
            FROM {table}
            GROUP BY year, quarter
            HAVING 100.0 * SUM(CASE WHEN {column} IS NULL THEN 1 ELSE 0 END) / COUNT(*) > {max_null_pct}
            ORDER BY year DESC, quarter DESC
            LIMIT 5
            """
            
            results = pg_hook.get_records(query)
            
            if results:
                for year, quarter, null_pct in results:
                    issues.append(f"{table}.{column}: {year}Q{quarter} has {null_pct}% nulls (max: {max_null_pct}%)")
    
    if issues:
        error_msg = "Null percentage validation FAILED:\n" + "\n".join(issues)
        print(error_msg)
        raise ValueError(error_msg)
    
    print(f"✓ Null percentage validation passed: All critical columns have <= {max_null_pct}% nulls")


def check_station_coverage(**context):
    """Validate minimum station count per quarter."""
    pg_hook = PostgresHook(postgres_conn_id='weatherinsight_postgres')
    min_stations = config['quality_thresholds']['min_stations_per_quarter']
    
    tables = [
        'quarterly_temperature_features',
        'quarterly_precipitation_features',
        'quarterly_wind_features',
        'quarterly_pressure_features',
        'quarterly_humidity_features',
    ]
    
    issues = []
    
    for table in tables:
        query = f"""
        SELECT year, quarter, COUNT(DISTINCT station_id) as station_count
        FROM {table}
        GROUP BY year, quarter
        HAVING COUNT(DISTINCT station_id) < {min_stations}
        ORDER BY year DESC, quarter DESC
        LIMIT 10
        """
        
        results = pg_hook.get_records(query)
        
        if results:
            for year, quarter, count in results:
                issues.append(f"{table}: {year}Q{quarter} has only {count} stations (min: {min_stations})")
    
    if issues:
        error_msg = "Station coverage validation FAILED:\n" + "\n".join(issues)
        print(error_msg)
        raise ValueError(error_msg)
    
    print(f"✓ Station coverage validation passed: All quarters have >= {min_stations} stations")


def check_metadata_consistency(**context):
    """Validate dataset version metadata consistency."""
    pg_hook = PostgresHook(postgres_conn_id='weatherinsight_postgres')
    
    # Check for dataset versions with status != 'AVAILABLE'
    query = """
    SELECT dataset_id, status, created_at
    FROM dataset_versions
    WHERE status != 'AVAILABLE'
    AND created_at > NOW() - INTERVAL '7 days'
    ORDER BY created_at DESC
    LIMIT 20
    """
    
    results = pg_hook.get_records(query)
    
    if results:
        issues = [f"{dataset_id}: status={status} (created {created_at})" 
                  for dataset_id, status, created_at in results]
        warning_msg = "Metadata consistency WARNING (non-AVAILABLE datasets):\n" + "\n".join(issues)
        print(warning_msg)
        # Don't fail, just warn
    else:
        print("✓ Metadata consistency check passed: All recent datasets are AVAILABLE")


def check_temporal_continuity(**context):
    """Check for missing quarters in the data."""
    pg_hook = PostgresHook(postgres_conn_id='weatherinsight_postgres')
    
    # Check each feature table for gaps
    tables = [
        'quarterly_temperature_features',
        'quarterly_precipitation_features',
        'quarterly_wind_features',
        'quarterly_pressure_features',
        'quarterly_humidity_features',
    ]
    
    issues = []
    
    for table in tables:
        # Find gaps in year-quarter sequence
        query = f"""
        WITH quarters AS (
            SELECT DISTINCT year, quarter
            FROM {table}
            ORDER BY year, quarter
        ),
        expected AS (
            SELECT 
                year_val AS year,
                quarter_val AS quarter
            FROM 
                generate_series(
                    (SELECT MIN(year) FROM quarters),
                    (SELECT MAX(year) FROM quarters)
                ) AS year_val,
                generate_series(1, 4) AS quarter_val
        )
        SELECT e.year, e.quarter
        FROM expected e
        LEFT JOIN quarters q ON e.year = q.year AND e.quarter = q.quarter
        WHERE q.year IS NULL
        ORDER BY e.year, e.quarter
        LIMIT 20
        """
        
        results = pg_hook.get_records(query)
        
        if results:
            for year, quarter in results:
                issues.append(f"{table}: Missing data for {year}Q{quarter}")
    
    if issues:
        warning_msg = "Temporal continuity WARNING (missing quarters):\n" + "\n".join(issues)
        print(warning_msg)
        # Don't fail, just warn (backfill may be in progress)
    else:
        print("✓ Temporal continuity check passed: No missing quarters detected")


with dag:
    # Start marker
    start = BashOperator(
        task_id='start_quality_checks',
        bash_command='echo "Starting data quality checks for {{ execution_date }}"',
    )
    
    # Row count validation
    check_rows = PythonOperator(
        task_id='check_row_counts',
        python_callable=check_row_counts,
        provide_context=True,
    )
    
    # Null percentage validation
    check_nulls = PythonOperator(
        task_id='check_null_percentages',
        python_callable=check_null_percentages,
        provide_context=True,
    )
    
    # Station coverage validation
    check_stations = PythonOperator(
        task_id='check_station_coverage',
        python_callable=check_station_coverage,
        provide_context=True,
    )
    
    # Metadata consistency validation
    check_metadata = PythonOperator(
        task_id='check_metadata_consistency',
        python_callable=check_metadata_consistency,
        provide_context=True,
    )
    
    # Temporal continuity validation
    check_continuity = PythonOperator(
        task_id='check_temporal_continuity',
        python_callable=check_temporal_continuity,
        provide_context=True,
    )
    
    # Generate summary report
    generate_report = BashOperator(
        task_id='generate_quality_report',
        bash_command="""
        echo "==================================="
        echo "Data Quality Report"
        echo "==================================="
        echo "Execution Date: {{ execution_date }}"
        echo ""
        
        # Query overall statistics
        docker exec postgres psql -U weatherinsight -d weatherinsight << 'EOF'
        
        -- Overall feature counts
        SELECT 
            'Temperature' as product,
            COUNT(*) as total_rows,
            COUNT(DISTINCT station_id) as unique_stations,
            MIN(year) as min_year,
            MAX(year) as max_year
        FROM quarterly_temperature_features
        UNION ALL
        SELECT 
            'Precipitation',
            COUNT(*),
            COUNT(DISTINCT station_id),
            MIN(year),
            MAX(year)
        FROM quarterly_precipitation_features
        UNION ALL
        SELECT 
            'Wind',
            COUNT(*),
            COUNT(DISTINCT station_id),
            MIN(year),
            MAX(year)
        FROM quarterly_wind_features
        UNION ALL
        SELECT 
            'Pressure',
            COUNT(*),
            COUNT(DISTINCT station_id),
            MIN(year),
            MAX(year)
        FROM quarterly_pressure_features
        UNION ALL
        SELECT 
            'Humidity',
            COUNT(*),
            COUNT(DISTINCT station_id),
            MIN(year),
            MAX(year)
        FROM quarterly_humidity_features;
        
        -- Recent dataset versions
        SELECT 
            dataset_id,
            status,
            created_at
        FROM dataset_versions
        WHERE created_at > NOW() - INTERVAL '30 days'
        ORDER BY created_at DESC
        LIMIT 10;
        
EOF
        
        echo ""
        echo "==================================="
        echo "All quality checks passed!"
        echo "==================================="
        """,
    )
    
    # End marker
    end = BashOperator(
        task_id='quality_checks_complete',
        bash_command='echo "Data quality checks complete for {{ execution_date }}"',
    )
    
    # Define pipeline
    start >> [check_rows, check_nulls, check_stations, check_metadata, check_continuity]
    [check_rows, check_nulls, check_stations, check_metadata, check_continuity] >> generate_report >> end
