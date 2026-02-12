#!/bin/bash
# Test script for metadata service

set -e

echo "=== Testing Metadata Service ==="
echo ""

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Network name
NETWORK="new-project_weatherinsight"

# Check if services are running
echo -e "${BLUE}Checking if services are running...${NC}"
if ! docker compose ps | grep -q postgres; then
    echo "Starting services..."
    docker compose up -d
    echo "Waiting for services to be ready..."
    sleep 10
fi

# Build metadata service
echo -e "${BLUE}Building metadata service...${NC}"
cd services/metadata
docker build -t weatherinsight-metadata:latest . > /dev/null 2>&1
cd ../..

# Create test schema file
echo -e "${BLUE}Creating test schema...${NC}"
cat > /tmp/test_weather_schema.json << 'EOF'
{
  "name": "raw_weather_observations",
  "type": "record",
  "fields": {
    "station_id": {
      "type": "string",
      "required": true,
      "description": "DWD station identifier"
    },
    "measurement_timestamp": {
      "type": "datetime",
      "required": true,
      "description": "Timestamp of observation"
    },
    "temperature_celsius": {
      "type": "float",
      "required": false,
      "description": "Air temperature in Celsius"
    },
    "quality_flag": {
      "type": "integer",
      "required": false,
      "description": "DWD quality code"
    }
  }
}
EOF

# Test 1: List schemas (should be empty or show existing)
echo -e "${BLUE}Test 1: List existing schemas${NC}"
docker run --rm \
  --network $NETWORK \
  -e POSTGRES_HOST=postgres \
  -e POSTGRES_USER=weatherinsight \
  -e POSTGRES_PASSWORD=weatherinsight123 \
  weatherinsight-metadata:latest \
  python bin/metadata schema list

echo -e "${GREEN}✓ Schema list successful${NC}"
echo ""

# Test 2: Register new schema
echo -e "${BLUE}Test 2: Register test schema${NC}"
docker run --rm \
  --network $NETWORK \
  -v /tmp/test_weather_schema.json:/tmp/test_weather_schema.json \
  -e POSTGRES_HOST=postgres \
  -e POSTGRES_USER=weatherinsight \
  -e POSTGRES_PASSWORD=weatherinsight123 \
  weatherinsight-metadata:latest \
  python bin/metadata schema register \
    --name test_weather_observations \
    --schema-file /tmp/test_weather_schema.json \
    --description "Test weather observation schema" \
    --compatibility BACKWARD

echo -e "${GREEN}✓ Schema registration successful${NC}"
echo ""

# Test 3: Get schema
echo -e "${BLUE}Test 3: Retrieve registered schema${NC}"
docker run --rm \
  --network $NETWORK \
  -e POSTGRES_HOST=postgres \
  -e POSTGRES_USER=weatherinsight \
  -e POSTGRES_PASSWORD=weatherinsight123 \
  weatherinsight-metadata:latest \
  python bin/metadata schema get \
    --name test_weather_observations

echo -e "${GREEN}✓ Schema retrieval successful${NC}"
echo ""

# Test 4: Create dataset version
echo -e "${BLUE}Test 4: Create dataset version${NC}"
docker run --rm \
  --network $NETWORK \
  -e POSTGRES_HOST=postgres \
  -e POSTGRES_USER=weatherinsight \
  -e POSTGRES_PASSWORD=weatherinsight123 \
  weatherinsight-metadata:latest \
  python bin/metadata dataset create \
    --dataset-name test_temperature_raw \
    --version 2024-Q1 \
    --schema-name test_weather_observations \
    --schema-version 1 \
    --start-date 2024-01-01 \
    --end-date 2024-03-31 \
    --storage-location s3://weatherinsight-raw/2024-Q1/ \
    --metadata '{"source":"dwd","variable":"temperature"}' \
    --created-by test_script

echo -e "${GREEN}✓ Dataset version created${NC}"
echo ""

# Test 5: List datasets
echo -e "${BLUE}Test 5: List dataset versions${NC}"
docker run --rm \
  --network $NETWORK \
  -e POSTGRES_HOST=postgres \
  -e POSTGRES_USER=weatherinsight \
  -e POSTGRES_PASSWORD=weatherinsight123 \
  weatherinsight-metadata:latest \
  python bin/metadata dataset list

echo -e "${GREEN}✓ Dataset listing successful${NC}"
echo ""

# Test 6: Schema history
echo -e "${BLUE}Test 6: View schema history${NC}"
docker run --rm \
  --network $NETWORK \
  -e POSTGRES_HOST=postgres \
  -e POSTGRES_USER=weatherinsight \
  -e POSTGRES_PASSWORD=weatherinsight123 \
  weatherinsight-metadata:latest \
  python bin/metadata schema history \
    --name test_weather_observations

echo -e "${GREEN}✓ Schema history retrieval successful${NC}"
echo ""

echo -e "${GREEN}=== All Tests Passed! ===${NC}"
echo ""
echo "Next steps:"
echo "1. Access MinIO Console: http://localhost:9001 (minioadmin/minioadmin123)"
echo "2. Access Grafana: http://localhost:3002 (admin/admin123)"
echo "3. Access Airflow: http://localhost:8080 (admin/admin123)"
echo "4. Proceed to M4 - Processing Service"
