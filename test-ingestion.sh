#!/bin/bash
# Quick test script for ingestion service

set -e

echo "=== WeatherInsight Ingestion Service Test ==="
echo ""

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "Creating .env from .env.example..."
    cp .env.example .env
fi

# Start infrastructure
echo "1. Starting infrastructure services..."
docker compose up -d minio postgres redis
echo "   Waiting for services to be healthy..."
sleep 15

# Build ingestion service
echo ""
echo "2. Building ingestion service..."
cd services/ingestion
docker build -t weatherinsight-ingestion:latest .
cd ../..

# Get network name
NETWORK_NAME=$(docker network ls --filter name=weatherinsight --format "{{.Name}}" | head -1)
echo "   Using network: $NETWORK_NAME"

# Run test ingestion
echo ""
echo "3. Running test ingestion (air_temperature, station 00433)..."
docker run --rm \
  --network "$NETWORK_NAME" \
  -e MINIO_ENDPOINT=minio:9000 \
  -e MINIO_ROOT_USER=minioadmin \
  -e MINIO_ROOT_PASSWORD=minioadmin123 \
  -e POSTGRES_HOST=postgres \
  -e POSTGRES_USER=weatherinsight \
  -e POSTGRES_PASSWORD=weatherinsight123 \
  weatherinsight-ingestion:latest \
  python bin/ingest --variable air_temperature --station-ids 00433

echo ""
echo "=== Test Complete ==="
echo ""
echo "Next steps:"
echo "  - Check MinIO Console: http://localhost:9001 (minioadmin/minioadmin123)"
echo "  - View bucket: weatherinsight-raw/raw/dwd/air_temperature/"
echo "  - Connect to PostgreSQL to view metadata:"
echo "    docker exec -it weatherinsight-postgres psql -U weatherinsight"
echo "    SELECT * FROM ingestion_runs;"
