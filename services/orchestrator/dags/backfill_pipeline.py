"""
WeatherInsight Backfill Pipeline DAG

Manually triggered DAG for reprocessing historical quarters.
Accepts parameters via dag_run.conf:
  - start_year: First year to backfill (default: 2020)
  - end_year: Last year to backfill (default: 2024)
  - quarters: List of quarters to backfill (default: [1,2,3,4])
  - products: List of products to backfill (default: all 5)
  - force_reprocess: Skip existing data checks (default: false)

Example trigger via CLI:
  airflow dags trigger weatherinsight_backfill \
    --conf '{"start_year": 2022, "end_year": 2023, "quarters": [1,2], "products": ["air_temperature"]}'
"""

from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator
from airflow.utils.task_group import TaskGroup
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
    'depends_on_past': False,  # Backfill quarters can run independently
    'email': config['email']['recipients'],
    'email_on_failure': config['email']['on_failure'],
    'email_on_retry': config['email']['on_retry'],
    'retries': config['retries']['processing'],
    'retry_delay': timedelta(minutes=config['retry_delay']['minutes']),
}

# Create DAG
dag = DAG(
    'weatherinsight_backfill',
    default_args=default_args,
    description='Backfill historical quarters for WeatherInsight',
    schedule_interval=None,  # Manual trigger only
    start_date=datetime(2020, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=['weatherinsight', 'backfill', 'manual'],
)

# Environment variables for service containers
common_env = {
    'MINIO_ENDPOINT': 'http://minio:9000',
    'MINIO_ACCESS_KEY': Variable.get('MINIO_ACCESS_KEY', default_var='minioadmin'),
    'MINIO_SECRET_KEY': Variable.get('MINIO_SECRET_KEY', default_var='minioadmin123'),
    'POSTGRES_HOST': 'postgres',
    'POSTGRES_PORT': '5432',
    'POSTGRES_DB': Variable.get('POSTGRES_DB', default_var='weatherinsight'),
    'POSTGRES_USER': Variable.get('POSTGRES_USER', default_var='weatherinsight'),
    'POSTGRES_PASSWORD': Variable.get('POSTGRES_PASSWORD', default_var='weatherinsight123'),
    'S3_ENDPOINT': 'http://minio:9000',
    'S3_ACCESS_KEY': Variable.get('MINIO_ACCESS_KEY', default_var='minioadmin'),
    'S3_SECRET_KEY': Variable.get('MINIO_SECRET_KEY', default_var='minioadmin123'),
}

# Spark configuration
spark_env = {
    **common_env,
    'SPARK_MASTER': config['spark']['master'],
}


def generate_backfill_params(**context):
    """Parse dag_run.conf and generate backfill parameters."""
    conf = context['dag_run'].conf or {}
    
    # Get parameters with defaults
    start_year = conf.get('start_year', config['backfill']['default_start_year'])
    end_year = conf.get('end_year', config['backfill']['default_end_year'])
    quarters = conf.get('quarters', config['backfill']['default_quarters'])
    products = conf.get('products', config['product_types'])
    force_reprocess = conf.get('force_reprocess', False)
    
    # Generate list of (year, quarter, product) tuples
    backfill_items = []
    for year in range(start_year, end_year + 1):
        for quarter in quarters:
            for product in products:
                backfill_items.append({
                    'year': year,
                    'quarter': quarter,
                    'product': product,
                    'force': force_reprocess
                })
    
    # Push to XCom for downstream tasks
    context['task_instance'].xcom_push(key='backfill_items', value=backfill_items)
    context['task_instance'].xcom_push(key='total_items', value=len(backfill_items))
    
    print(f"Backfill plan: {len(backfill_items)} items")
    print(f"  Years: {start_year} to {end_year}")
    print(f"  Quarters: {quarters}")
    print(f"  Products: {products}")
    print(f"  Force reprocess: {force_reprocess}")
    
    return backfill_items


with dag:
    # Parse parameters
    parse_params = PythonOperator(
        task_id='parse_backfill_params',
        python_callable=generate_backfill_params,
        provide_context=True,
    )
    
    # Backfill ingestion
    backfill_ingestion = BashOperator(
        task_id='backfill_ingestion',
        bash_command="""
        echo "Starting backfill ingestion..."
        
        # Parse conf from XCom (simplified - in production use proper XCom retrieval)
        START_YEAR={{ dag_run.conf.get('start_year', 2020) }}
        END_YEAR={{ dag_run.conf.get('end_year', 2024) }}
        PRODUCTS="{{ dag_run.conf.get('products', ['air_temperature', 'precipitation', 'wind', 'pressure', 'moisture']) | join(' ') }}"
        
        cd /opt/services/ingestion
        
        # Loop through products
        for product in $PRODUCTS; do
            echo "Ingesting $product for years $START_YEAR to $END_YEAR..."
            
            # Calculate date range for all quarters
            START_DATE="${START_YEAR}-01-01"
            END_DATE="${END_YEAR}-12-31"
            
            python bin/ingest --variable "$product" || {
                echo "Failed to ingest $product"
                exit 1
            }
        done
        
        echo "Backfill ingestion complete"
        """,
        env=common_env,
        retries=config['retries']['ingestion'],
        pool='api_calls',
    )
    
    # Backfill processing
    backfill_processing = BashOperator(
        task_id='backfill_processing',
        bash_command="""
        echo "Starting backfill processing..."
        
        START_YEAR={{ dag_run.conf.get('start_year', 2020) }}
        END_YEAR={{ dag_run.conf.get('end_year', 2024) }}
        QUARTERS="{{ dag_run.conf.get('quarters', [1,2,3,4]) | join(' ') }}"
        PRODUCTS="{{ dag_run.conf.get('products', ['air_temperature', 'precipitation', 'wind', 'pressure', 'moisture']) | join(' ') }}"
        
        cd /opt/services/processing
        
        # Loop through all combinations
        for product in $PRODUCTS; do
            for year in $(seq $START_YEAR $END_YEAR); do
                for quarter in $QUARTERS; do
                    VERSION="${year}Q${quarter}_raw_v1"
                    echo "Processing $product for $year Q$quarter (version: $VERSION)..."
                    
                    python src/orchestrator.py \
                        "$product" \
                        "s3a://weatherinsight-raw/raw/dwd/$product" \
                        "$VERSION" \
                        --master {{ params.spark_master }} || {
                        echo "Failed to process $product $year Q$quarter"
                        # Continue with other quarters instead of failing completely
                    }
                done
            done
        done
        
        echo "Backfill processing complete"
        """,
        env=spark_env,
        params={'spark_master': config['spark']['master']},
        retries=config['retries']['processing'],
        pool='spark_jobs',
    )
    
    # Backfill aggregation
    backfill_aggregation = BashOperator(
        task_id='backfill_aggregation',
        bash_command="""
        echo "Starting backfill aggregation..."
        
        START_YEAR={{ dag_run.conf.get('start_year', 2020) }}
        END_YEAR={{ dag_run.conf.get('end_year', 2024) }}
        QUARTERS="{{ dag_run.conf.get('quarters', [1,2,3,4]) | join(' ') }}"
        PRODUCTS="{{ dag_run.conf.get('products', ['air_temperature', 'precipitation', 'wind', 'pressure', 'moisture']) | join(' ') }}"
        
        cd /opt/services/aggregation
        
        # Loop through all combinations
        for product in $PRODUCTS; do
            for year in $(seq $START_YEAR $END_YEAR); do
                for quarter in $QUARTERS; do
                    STAGED_VERSION="${year}Q${quarter}_staged_v1"
                    CURATED_VERSION="${year}Q${quarter}_v1"
                    echo "Aggregating $product for $year Q$quarter..."
                    
                    python src/orchestrator.py \
                        "$product" \
                        "$year" \
                        "$quarter" \
                        "$STAGED_VERSION" \
                        --output-version "$CURATED_VERSION" \
                        --master {{ params.spark_master }} || {
                        echo "Failed to aggregate $product $year Q$quarter"
                        # Continue with other quarters
                    }
                done
            done
        done
        
        echo "Backfill aggregation complete"
        """,
        env=spark_env,
        params={'spark_master': config['spark']['master']},
        retries=config['retries']['aggregation'],
        pool='spark_jobs',
    )
    
    # Summary report
    backfill_summary = BashOperator(
        task_id='backfill_summary',
        bash_command="""
        echo "==================================="
        echo "Backfill Summary"
        echo "==================================="
        echo "Year range: {{ dag_run.conf.get('start_year', 2020) }} to {{ dag_run.conf.get('end_year', 2024) }}"
        echo "Quarters: {{ dag_run.conf.get('quarters', [1,2,3,4]) }}"
        echo "Products: {{ dag_run.conf.get('products', ['air_temperature', 'precipitation', 'wind', 'pressure', 'moisture']) }}"
        echo "==================================="
        
        # Query PostgreSQL for verification
        docker exec postgres psql -U weatherinsight -d weatherinsight -c "
        SELECT 
            'quarterly_temperature_features' as table_name,
            COUNT(*) as row_count,
            MIN(year) as min_year,
            MAX(year) as max_year
        FROM quarterly_temperature_features
        UNION ALL
        SELECT 
            'quarterly_precipitation_features',
            COUNT(*),
            MIN(year),
            MAX(year)
        FROM quarterly_precipitation_features
        UNION ALL
        SELECT 
            'quarterly_wind_features',
            COUNT(*),
            MIN(year),
            MAX(year)
        FROM quarterly_wind_features
        UNION ALL
        SELECT 
            'quarterly_pressure_features',
            COUNT(*),
            MIN(year),
            MAX(year)
        FROM quarterly_pressure_features
        UNION ALL
        SELECT 
            'quarterly_humidity_features',
            COUNT(*),
            MIN(year),
            MAX(year)
        FROM quarterly_humidity_features;
        " || echo "Could not query database"
        
        echo "Backfill complete!"
        """,
    )
    
    # Define pipeline: parse -> ingest -> process -> aggregate -> summary
    parse_params >> backfill_ingestion >> backfill_processing >> backfill_aggregation >> backfill_summary
