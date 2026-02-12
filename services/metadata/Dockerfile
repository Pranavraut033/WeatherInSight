FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/
COPY bin/ ./bin/

# Add src to Python path
ENV PYTHONPATH=/app/src

# Default command
CMD ["python", "bin/metadata", "--help"]
