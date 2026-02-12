"""Health check endpoint."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db, check_db_connection

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Health check response model."""
    status: str
    database: str
    message: str


@router.get("/health", response_model=HealthResponse)
async def health_check(db: Session = Depends(get_db)) -> HealthResponse:
    """
    Health check endpoint.
    
    Verifies that the API is running and can connect to PostgreSQL.
    
    Returns:
        Health status information
    """
    db_healthy = check_db_connection()
    
    if not db_healthy:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection failed"
        )
    
    return HealthResponse(
        status="healthy",
        database="connected",
        message="WeatherInsight API is running"
    )


@router.get("/")
async def root() -> dict:
    """
    Root endpoint with API information.
    
    Returns:
        Basic API information
    """
    return {
        "service": "WeatherInsight API",
        "version": "1.0.0",
        "documentation": "/docs",
        "health_check": "/health"
    }
