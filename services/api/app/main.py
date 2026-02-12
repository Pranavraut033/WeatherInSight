"""FastAPI application entry point."""

import logging
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import get_config
from app.database import check_db_connection
from app.routers import health, stations, features
from app.auth import limiter, is_health_check

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Get configuration
config = get_config()

# Prometheus metrics
REQUEST_COUNT = Counter(
    "weatherinsight_api_requests_total",
    "Total API requests",
    ["method", "endpoint", "status"]
)
REQUEST_DURATION = Histogram(
    "weatherinsight_api_request_duration_seconds",
    "API request duration in seconds",
    ["method", "endpoint"]
)
DB_QUERY_DURATION = Histogram(
    "weatherinsight_api_db_query_duration_seconds",
    "Database query duration in seconds",
    ["operation"]
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """
    Lifespan context manager for startup and shutdown events.
    
    Startup:
    - Check database connectivity
    - Log configuration
    
    Shutdown:
    - Cleanup resources
    """
    # Startup
    logger.info("Starting WeatherInsight API")
    logger.info(f"PostgreSQL host: {config.postgres_host}")
    
    # Check database connection
    if check_db_connection():
        logger.info("Database connection successful")
    else:
        logger.warning("Database connection failed - API may not function properly")
    
    yield
    
    # Shutdown
    logger.info("Shutting down WeatherInsight API")


# Initialize FastAPI application
app = FastAPI(
    title=config.api_title,
    version=config.api_version,
    description=config.api_description,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# Add rate limiter state
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origins,
    allow_credentials=config.cors_allow_credentials,
    allow_methods=config.cors_allow_methods,
    allow_headers=config.cors_allow_headers,
)


# Request logging and metrics middleware
@app.middleware("http")
async def logging_and_metrics_middleware(request: Request, call_next):
    """
    Middleware to log requests and collect Prometheus metrics.
    
    Tracks:
    - Request count by method, endpoint, and status
    - Request duration by method and endpoint
    """
    # Skip rate limiting for health check endpoints
    if is_health_check(request):
        return await call_next(request)
    
    start_time = time.time()
    
    # Generate request ID
    request_id = f"{int(start_time * 1000)}-{id(request)}"
    
    # Log request
    logger.info(
        f"Request started: {request.method} {request.url.path} "
        f"[{request_id}]"
    )
    
    # Process request
    response = await call_next(request)
    
    # Calculate duration
    duration = time.time() - start_time
    
    # Extract endpoint path (without query params)
    endpoint = request.url.path
    
    # Record metrics
    REQUEST_COUNT.labels(
        method=request.method,
        endpoint=endpoint,
        status=response.status_code
    ).inc()
    
    REQUEST_DURATION.labels(
        method=request.method,
        endpoint=endpoint
    ).observe(duration)
    
    # Log response
    logger.info(
        f"Request completed: {request.method} {request.url.path} "
        f"[{request_id}] - {response.status_code} - {duration:.3f}s"
    )
    
    # Add custom headers
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Response-Time"] = f"{duration:.3f}s"
    
    return response


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Global exception handler for unhandled errors.
    
    Returns:
        500 error with sanitized error message
    """
    logger.error(
        f"Unhandled exception: {request.method} {request.url.path} - {str(exc)}",
        exc_info=True
    )
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "Internal server error",
            "type": "internal_error",
            "path": str(request.url.path)
        }
    )


# Prometheus metrics endpoint
@app.get("/metrics")
async def metrics():
    """
    Prometheus metrics endpoint.
    
    Returns:
        Prometheus metrics in text format
    """
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )


# Include routers
app.include_router(health.router)
app.include_router(stations.router)
app.include_router(features.router)


# Root endpoint (defined in health router)
# Additional API info endpoint
@app.get("/api/v1/info")
async def api_info():
    """
    Get API version and configuration information.
    
    Returns:
        API metadata and available endpoints
    """
    return {
        "api": {
            "title": config.api_title,
            "version": config.api_version,
            "description": config.api_description
        },
        "endpoints": {
            "health": "/health",
            "docs": "/docs",
            "metrics": "/metrics",
            "stations": "/api/v1/stations",
            "features": "/api/v1/features"
        },
        "products": [
            "temperature",
            "precipitation",
            "wind",
            "pressure",
            "humidity"
        ],
        "pagination": {
            "default_page_size": config.default_page_size,
            "max_page_size": config.max_page_size
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level=config.log_level.lower()
    )
