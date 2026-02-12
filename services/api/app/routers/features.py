"""Feature endpoints for all product types."""

from typing import Optional, Union
from fastapi import APIRouter, Depends, HTTPException, Query, Path, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    PaginatedResponse,
    TemperatureFeatureResponse,
    PrecipitationFeatureResponse,
    WindFeatureResponse,
    PressureFeatureResponse,
    HumidityFeatureResponse,
)
from app.crud import (
    get_features,
    get_station_features,
    get_feature_stats,
    get_available_products,
    PRODUCT_MODEL_MAP,
)
from app.config import get_config

router = APIRouter(prefix="/api/v1/features", tags=["features"])
config = get_config()

# Map product types to response models
RESPONSE_MODEL_MAP = {
    "temperature": TemperatureFeatureResponse,
    "precipitation": PrecipitationFeatureResponse,
    "wind": WindFeatureResponse,
    "pressure": PressureFeatureResponse,
    "humidity": HumidityFeatureResponse,
}


@router.get("/products")
async def list_products(db: Session = Depends(get_db)) -> dict:
    """
    List all available product types with statistics.
    
    Returns:
        List of products with record counts and metadata
    """
    products = get_available_products(db)
    
    return {
        "products": products,
        "total_products": len(products)
    }


@router.get("/{product}/stats")
async def get_product_stats(
    product: str = Path(
        ...,
        description="Product type",
        pattern="^(temperature|precipitation|wind|pressure|humidity)$"
    ),
    db: Session = Depends(get_db)
) -> dict:
    """
    Get statistics for a specific product type.
    
    Path parameters:
    - **product**: One of temperature, precipitation, wind, pressure, humidity
    
    Returns:
        Statistics including record counts, date ranges, and station coverage
    """
    try:
        stats = get_feature_stats(db, product)
        return stats
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/{product}", response_model=PaginatedResponse)
async def list_features(
    product: str = Path(
        ...,
        description="Product type",
        pattern="^(temperature|precipitation|wind|pressure|humidity)$"
    ),
    limit: int = Query(
        default=config.default_page_size,
        ge=1,
        le=config.max_page_size,
        description="Maximum number of results"
    ),
    offset: int = Query(
        default=0,
        ge=0,
        description="Number of results to skip"
    ),
    station_id: Optional[int] = Query(
        default=None,
        description="Filter by station ID"
    ),
    year: Optional[int] = Query(
        default=None,
        ge=2000,
        le=2100,
        description="Filter by specific year"
    ),
    quarter: Optional[int] = Query(
        default=None,
        ge=1,
        le=4,
        description="Filter by quarter (1-4)"
    ),
    min_year: Optional[int] = Query(
        default=None,
        ge=2000,
        description="Minimum year (inclusive)"
    ),
    max_year: Optional[int] = Query(
        default=None,
        le=2100,
        description="Maximum year (inclusive)"
    ),
    db: Session = Depends(get_db)
) -> PaginatedResponse:
    """
    Get quarterly features for a product type with filtering and pagination.
    
    Path parameters:
    - **product**: Product type (temperature, precipitation, wind, pressure, humidity)
    
    Query parameters:
    - **limit**: Maximum number of results (default: 50, max: 1000)
    - **offset**: Number of results to skip for pagination
    - **station_id**: Filter by specific station
    - **year**: Filter by specific year
    - **quarter**: Filter by specific quarter (1=Q1, 2=Q2, 3=Q3, 4=Q4)
    - **min_year**: Filter by minimum year (inclusive)
    - **max_year**: Filter by maximum year (inclusive)
    
    Returns:
        Paginated list of quarterly features ordered by date (newest first)
    """
    try:
        features, total = get_features(
            db=db,
            product=product,
            limit=limit,
            offset=offset,
            station_id=station_id,
            year=year,
            quarter=quarter,
            min_year=min_year,
            max_year=max_year
        )
        
        # Convert to appropriate response model
        response_model = RESPONSE_MODEL_MAP[product]
        feature_responses = [response_model.model_validate(f) for f in features]
        
        return PaginatedResponse(
            total=total,
            limit=limit,
            offset=offset,
            items=feature_responses
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/{product}/stations/{station_id}", response_model=PaginatedResponse)
async def get_station_timeseries(
    product: str = Path(
        ...,
        description="Product type",
        pattern="^(temperature|precipitation|wind|pressure|humidity)$"
    ),
    station_id: int = Path(
        ...,
        description="Station ID"
    ),
    limit: int = Query(
        default=config.default_page_size,
        ge=1,
        le=config.max_page_size,
        description="Maximum number of results"
    ),
    offset: int = Query(
        default=0,
        ge=0,
        description="Number of results to skip"
    ),
    db: Session = Depends(get_db)
) -> PaginatedResponse:
    """
    Get time series of quarterly features for a specific station.
    
    Path parameters:
    - **product**: Product type (temperature, precipitation, wind, pressure, humidity)
    - **station_id**: DWD station ID
    
    Query parameters:
    - **limit**: Maximum number of results (default: 50, max: 1000)
    - **offset**: Number of results to skip for pagination
    
    Returns:
        Paginated time series of quarterly features ordered chronologically
    """
    try:
        features, total = get_station_features(
            db=db,
            product=product,
            station_id=station_id,
            limit=limit,
            offset=offset
        )
        
        if not features and total == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No {product} data found for station {station_id}"
            )
        
        # Convert to appropriate response model
        response_model = RESPONSE_MODEL_MAP[product]
        feature_responses = [response_model.model_validate(f) for f in features]
        
        return PaginatedResponse(
            total=total,
            limit=limit,
            offset=offset,
            items=feature_responses
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
