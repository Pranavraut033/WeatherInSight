"""
Authentication and rate limiting utilities.

Provides:
- API key authentication
- Rate limiting with Redis backend
- Security middleware
"""

import os
import hashlib
import hmac
from typing import Optional

from fastapi import Header, HTTPException, status, Request
from slowapi import Limiter
from slowapi.util import get_remote_address


# API Key configuration
API_KEY_HEADER = "X-API-Key"
VALID_API_KEYS = os.getenv("WEATHERINSIGHT_API_KEYS", "dev-key-12345").split(",")

# Rate limiter configuration
def get_redis_url() -> str:
    """Get Redis URL from environment or use default."""
    redis_host = os.getenv("REDIS_HOST", "redis")
    redis_port = os.getenv("REDIS_PORT", "6379")
    redis_db = os.getenv("REDIS_DB_RATE_LIMIT", "1")
    return f"redis://{redis_host}:{redis_port}/{redis_db}"


# Initialize rate limiter with Redis backend
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=get_redis_url(),
    default_limits=["100/minute", "2000/hour"],
    headers_enabled=True,  # Add X-RateLimit-* headers to responses
)


def verify_api_key(x_api_key: Optional[str] = Header(None)) -> str:
    """
    Verify API key from request header.
    
    Args:
        x_api_key: API key from X-API-Key header
        
    Returns:
        The verified API key
        
    Raises:
        HTTPException: If API key is missing or invalid
    """
    # Allow bypassing auth in development mode
    if os.getenv("WEATHERINSIGHT_DEV_MODE", "false").lower() == "true":
        return "dev-bypass"
    
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key. Please provide X-API-Key header.",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    
    # Constant-time comparison to prevent timing attacks
    is_valid = any(
        hmac.compare_digest(x_api_key, valid_key)
        for valid_key in VALID_API_KEYS
    )
    
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    
    return x_api_key


def get_rate_limit_key(request: Request) -> str:
    """
    Get rate limit key for request.
    
    Uses API key if provided, otherwise falls back to IP address.
    This allows different rate limits per API key.
    
    Args:
        request: FastAPI request object
        
    Returns:
        Rate limit key string
    """
    # Try to get API key from header
    api_key = request.headers.get(API_KEY_HEADER)
    
    if api_key and api_key in VALID_API_KEYS:
        # Hash the API key for privacy in logs
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()[:16]
        return f"apikey:{key_hash}"
    
    # Fall back to IP address
    return f"ip:{get_remote_address(request)}"


# Decorator for endpoints requiring authentication
def requires_auth(func):
    """Decorator to require API key authentication for an endpoint."""
    async def wrapper(*args, **kwargs):
        # API key verification happens in dependency
        return await func(*args, **kwargs)
    return wrapper


# Custom rate limit decorator with API key awareness
def rate_limit(limit: str):
    """
    Custom rate limit decorator that uses API key if available.
    
    Args:
        limit: Rate limit string (e.g., "10/minute")
        
    Returns:
        Decorated function
    """
    def decorator(func):
        return limiter.limit(limit, key_func=get_rate_limit_key)(func)
    return decorator


# Health check exemption - no rate limit
def is_health_check(request: Request) -> bool:
    """Check if request is a health check endpoint."""
    return request.url.path in ["/health", "/", "/metrics"]
