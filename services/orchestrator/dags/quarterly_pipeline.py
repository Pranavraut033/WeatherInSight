"""
WeatherInsight Quarterly Pipeline DAG

Orchestrates the complete quarterly data pipeline:
1. Ingestion: Download DWD data for all product types
2. Processing: Parse and clean raw data with Spark
3. Aggregation: Compute quarterly features and write to PostgreSQL

Schedule: Runs quarterly on day 1 of Jan/Apr/Jul/Oct at midnight UTC
Catchup: Enabled for historical backfill
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

# Default arguments for all tasks
default_args = {
    'owner': 'weatherinsight',
    'depends_on_past': True,  # Each quarter depends on previous quarter
    'email': config['email']['recipients'],
    'email_on_failure': config['email']['on_failure'],
    'email_on_retry': config['email']['on_retry'],
    'retries': config['retries']['ingestion'],
    'retry_delay': timedelta(minutes=config['retry_delay']['minutes']),
    'execution_timeout': timedelta(hours=config['sla']['pipeline_hours']),
}

# Create DAG
dag = DAG(
    'weatherinsight_quarterly_pipeline',
    default_args=default_args,
    description='Quarterly DWD weather data pipeline (ingestion → processing → aggregation)',
    schedule_interval='0 0 1 1,4,7,10 *',  # Quarterly: Jan 1, Apr 1, Jul 1, Oct 1 at midnight
    start_date=datetime(2020, 1, 1),
    catchup=True,  # Enable backfill for historical quarters
    max_active_runs=1,  # Process one quarter at a time
    tags=['weatherinsight', 'quarterly', 'production'],
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


def create_ingestion_task(product_type: str, task_group: TaskGroup) -> BashOperator:
    """Create ingestion task for a product type."""
    return BashOperator(
        task_id=f'ingest_{product_type}',
        bash_command=f"""
        cd /opt/services/ingestion && \
        python bin/ingest --variable {product_type}
        """,
        env=common_env,
        retries=config['retries']['ingestion'],
        execution_timeout=timedelta(hours=config['sla']['ingestion_hours']),
        task_group=task_group,
        pool='api_calls',
    )


def create_processing_task(product_type: str, task_group: TaskGroup) -> BashOperator:
    """Create processing task for a product type."""
    # Generate version strings using Airflow templating
    raw_version = "{{ execution_date.year }}Q{{ ((execution_date.month - 1) // 3) + 1 }}_raw_v1"
    
    return BashOperator(
        task_id=f'process_{product_type}',
        bash_command=f"""
        cd /opt/services/processing && \
        python src/orchestrator.py \
            {product_type} \
            s3a://weatherinsight-raw/raw/dwd/{product_type} \
            {raw_version} \
            --master {config['spark']['master']}
        """,
        env=spark_env,
        retries=config['retries']['processing'],
        execution_timeout=timedelta(hours=config['sla']['processing_hours']),
        task_group=task_group,
        pool='spark_jobs',
    )


def create_aggregation_task(product_type: str, task_group: TaskGroup) -> BashOperator:
    """Create aggregation task for a product type."""
    staged_version = "{{ execution_date.year }}Q{{ ((execution_date.month - 1) // 3) + 1 }}_staged_v1"
    curated_version = "{{ execution_date.year }}Q{{ ((execution_date.month - 1) // 3) + 1 }}_v1"
    
    return BashOperator(
        task_id=f'aggregate_{product_type}',
        bash_command=f"""
        cd /opt/services/aggregation && \
        python src/orchestrator.py \
            {product_type} \
            {{{{ execution_date.year }}}} \
            {{{{ ((execution_date.month - 1) // 3) + 1 }}}} \
            {staged_version} \
            --output-version {curated_version} \
            --master {config['spark']['master']}
        """,
        env=spark_env,
        retries=config['retries']['aggregation'],
        execution_timeout=timedelta(hours=config['sla']['aggregation_hours']),
        task_group=task_group,
        pool='spark_jobs',
    )


# Create task groups for each pipeline stage
with dag:
    # Stage 1: Ingestion
    with TaskGroup('ingestion', tooltip='Ingest raw DWD data') as ingestion_group:
        ingestion_tasks = {
            product: create_ingestion_task(product, ingestion_group)
            for product in config['product_types']
        }
    
    # Stage 2: Processing
    with TaskGroup('processing', tooltip='Parse and clean raw data with Spark') as processing_group:
        processing_tasks = {
            product: create_processing_task(product, processing_group)
            for product in config['product_types']
        }
    
    # Stage 3: Aggregation
    with TaskGroup('aggregation', tooltip='Compute quarterly features') as aggregation_group:
        aggregation_tasks = {
            product: create_aggregation_task(product, aggregation_group)
            for product in config['product_types']
        }
    
    # Pipeline completion marker
    pipeline_complete = BashOperator(
        task_id='pipeline_complete',
        bash_command="""
        echo "Quarterly pipeline complete for {{ execution_date.year }}Q{{ ((execution_date.month - 1) // 3) + 1 }}"
        echo "Processed products: {{ params.products }}"
        """,
        params={'products': ', '.join(config['product_types'])},
    )
    
    # Define dependencies: ingestion -> processing -> aggregation
    for product in config['product_types']:
        # Each product's processing depends on its ingestion
        ingestion_tasks[product] >> processing_tasks[product]
        
        # Each product's aggregation depends on its processing
        processing_tasks[product] >> aggregation_tasks[product]
        
        # Pipeline complete depends on all aggregations
        aggregation_tasks[product] >> pipeline_complete
