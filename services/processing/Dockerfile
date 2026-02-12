FROM apache/spark-py:v3.5.0

USER root

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /opt/processing

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download AWS/Hadoop JARs for S3 support
RUN curl -o /opt/spark/jars/aws-java-sdk-bundle-1.12.262.jar \
    https://repo1.maven.org/maven2/com/amazonaws/aws-java-sdk-bundle/1.12.262/aws-java-sdk-bundle-1.12.262.jar \
    && curl -o /opt/spark/jars/hadoop-aws-3.3.4.jar \
    https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-aws/3.3.4/hadoop-aws-3.3.4.jar

# Copy source code
COPY src/ ./src/

# Add src to PYTHONPATH
ENV PYTHONPATH=/opt/processing/src:$PYTHONPATH

# Default command
CMD ["python", "src/orchestrator.py", "--help"]
