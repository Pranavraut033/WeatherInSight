"""Station metadata endpoints."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import StationResponse, PaginatedResponse
from app.crud import get_stations, get_station_by_id, get_station_count
from app.config import get_config

router = APIRouter(prefix="/api/v1/stations", tags=["stations"])
config = get_config()


@router.get("", response_model=PaginatedResponse)
async def list_stations(
    limit: int = Query(
        default=config.default_page_size,
        ge=1,
        le=config.max_page_size,
        description="Maximum number of results per page"
    ),
    offset: int = Query(
        default=0,
        ge=0,
        description="Number of results to skip"
    ),
    is_active: Optional[bool] = Query(
        default=None,
        description="Filter by active status"
    ),
    state: Optional[str] = Query(
        default=None,
        description="Filter by state name"
    ),
    db: Session = Depends(get_db)
) -> PaginatedResponse:
    """
    List all weather stations with pagination and filtering.
    
    Query parameters:
    - **limit**: Maximum number of results (default: 50, max: 1000)
    - **offset**: Number of results to skip for pagination
    - **is_active**: Filter by active status (true/false)
    - **state**: Filter by German state name
    
    Returns:
        Paginated list of stations with metadata
    """
    stations, total = get_stations(
        db=db,
        limit=limit,
        offset=offset,
        is_active=is_active,
        state=state
    )
    
    # Convert to Pydantic models
    station_responses = [StationResponse.model_validate(s) for s in stations]
    
    return PaginatedResponse(
        total=total,
        limit=limit,
        offset=offset,
        items=station_responses
    )


@router.get("/{station_id}", response_model=StationResponse)
async def get_station(
    station_id: int,
    db: Session = Depends(get_db)
) -> StationResponse:
    """
    Get detailed information for a specific station.
    
    Path parameters:
    - **station_id**: DWD station ID
    
    Returns:
        Station metadata including location, elevation, and operational dates
    
    Raises:
        404: Station not found
    """
    station = get_station_by_id(db, station_id)
    
    if station is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Station {station_id} not found"
        )
    
    return StationResponse.model_validate(station)


@router.get("/{station_id}/summary")
async def get_station_summary(
    station_id: int,
    db: Session = Depends(get_db)
) -> dict:
    """
    Get summary statistics for a station across all products.
    
    Path parameters:
    - **station_id**: DWD station ID
    
    Returns:
        Summary including available products and date ranges
    
    Raises:
        404: Station not found
    """
    station = get_station_by_id(db, station_id)
    
    if station is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Station {station_id} not found"
        )
    
    # Get counts for each product type
    from app.crud import PRODUCT_MODEL_MAP
    product_counts = {}
    
    for product_name, model in PRODUCT_MODEL_MAP.items():
        count = db.query(model).filter(model.station_id == station_id).count()
        product_counts[product_name] = count
    
    return {
        "station_id": station.station_id,
        "station_name": station.station_name,
        "location": {
            "latitude": station.latitude,
            "longitude": station.longitude,
            "elevation_m": station.elevation_m,
            "state": station.state
        },
        "operational_period": {
            "start_date": station.start_date,
            "end_date": station.end_date,
            "is_active": station.is_active
        },
        "available_products": product_counts,
        "total_records": sum(product_counts.values())
    }
