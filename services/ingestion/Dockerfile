FROM python:3.11-slim

LABEL maintainer="WeatherInsight Team"
LABEL description="Ingestion service for DWD weather data"

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/
COPY bin/ ./bin/

# Set Python path
ENV PYTHONPATH=/app/src

# Default command
CMD ["python", "bin/ingest", "--help"]
