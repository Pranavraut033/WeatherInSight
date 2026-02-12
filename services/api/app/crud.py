"""CRUD operations for database queries."""

from typing import Optional, Type
from sqlalchemy.orm import Session
from sqlalchemy import and_, func

from app.models import (
    StationMetadata,
    QuarterlyTemperatureFeatures,
    QuarterlyPrecipitationFeatures,
    QuarterlyWindFeatures,
    QuarterlyPressureFeatures,
    QuarterlyHumidityFeatures,
)


# Mapping of product types to ORM models
PRODUCT_MODEL_MAP = {
    "temperature": QuarterlyTemperatureFeatures,
    "precipitation": QuarterlyPrecipitationFeatures,
    "wind": QuarterlyWindFeatures,
    "pressure": QuarterlyPressureFeatures,
    "humidity": QuarterlyHumidityFeatures,
}


def get_product_model(product: str) -> Type:
    """
    Get ORM model for a product type.
    
    Args:
        product: Product type name (temperature, precipitation, wind, pressure, humidity)
    
    Returns:
        SQLAlchemy ORM model class
    
    Raises:
        ValueError: If product type is invalid
    """
    if product not in PRODUCT_MODEL_MAP:
        raise ValueError(
            f"Invalid product type: {product}. "
            f"Must be one of: {', '.join(PRODUCT_MODEL_MAP.keys())}"
        )
    return PRODUCT_MODEL_MAP[product]


# ============================================================================
# Station CRUD Operations
# ============================================================================

def get_stations(
    db: Session,
    limit: int = 50,
    offset: int = 0,
    is_active: Optional[bool] = None,
    state: Optional[str] = None,
) -> tuple[list[StationMetadata], int]:
    """
    Get list of stations with optional filtering.
    
    Args:
        db: Database session
        limit: Maximum number of results
        offset: Number of results to skip
        is_active: Filter by active status
        state: Filter by state name
    
    Returns:
        Tuple of (list of stations, total count)
    """
    query = db.query(StationMetadata)
    
    # Apply filters
    if is_active is not None:
        query = query.filter(StationMetadata.is_active == is_active)
    if state:
        query = query.filter(StationMetadata.state == state)
    
    # Get total count before pagination
    total = query.count()
    
    # Apply pagination and order
    stations = (
        query
        .order_by(StationMetadata.station_id)
        .limit(limit)
        .offset(offset)
        .all()
    )
    
    return stations, total


def get_station_by_id(db: Session, station_id: int) -> Optional[StationMetadata]:
    """
    Get a single station by ID.
    
    Args:
        db: Database session
        station_id: Station ID
    
    Returns:
        Station metadata or None if not found
    """
    return db.query(StationMetadata).filter(
        StationMetadata.station_id == station_id
    ).first()


def get_station_count(db: Session) -> int:
    """
    Get total number of stations.
    
    Args:
        db: Database session
    
    Returns:
        Total station count
    """
    return db.query(func.count(StationMetadata.station_id)).scalar()


# ============================================================================
# Feature CRUD Operations
# ============================================================================

def get_features(
    db: Session,
    product: str,
    limit: int = 50,
    offset: int = 0,
    station_id: Optional[int] = None,
    year: Optional[int] = None,
    quarter: Optional[int] = None,
    min_year: Optional[int] = None,
    max_year: Optional[int] = None,
) -> tuple[list, int]:
    """
    Get features for a product type with filtering and pagination.
    
    Args:
        db: Database session
        product: Product type (temperature, precipitation, wind, pressure, humidity)
        limit: Maximum number of results
        offset: Number of results to skip
        station_id: Filter by station ID
        year: Filter by specific year
        quarter: Filter by specific quarter (1-4)
        min_year: Filter by minimum year (inclusive)
        max_year: Filter by maximum year (inclusive)
    
    Returns:
        Tuple of (list of features, total count)
    
    Raises:
        ValueError: If product type is invalid or quarter is out of range
    """
    if quarter is not None and not (1 <= quarter <= 4):
        raise ValueError(f"Quarter must be between 1 and 4, got {quarter}")
    
    model = get_product_model(product)
    query = db.query(model)
    
    # Build filters
    filters = []
    if station_id is not None:
        filters.append(model.station_id == station_id)
    if year is not None:
        filters.append(model.year == year)
    if quarter is not None:
        filters.append(model.quarter == quarter)
    if min_year is not None:
        filters.append(model.year >= min_year)
    if max_year is not None:
        filters.append(model.year <= max_year)
    
    if filters:
        query = query.filter(and_(*filters))
    
    # Get total count
    total = query.count()
    
    # Apply pagination and ordering
    features = (
        query
        .order_by(model.year.desc(), model.quarter.desc(), model.station_id)
        .limit(limit)
        .offset(offset)
        .all()
    )
    
    return features, total


def get_station_features(
    db: Session,
    product: str,
    station_id: int,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list, int]:
    """
    Get all features for a specific station (time series).
    
    Args:
        db: Database session
        product: Product type
        station_id: Station ID
        limit: Maximum number of results
        offset: Number of results to skip
    
    Returns:
        Tuple of (list of features ordered by time, total count)
    """
    model = get_product_model(product)
    query = db.query(model).filter(model.station_id == station_id)
    
    total = query.count()
    
    features = (
        query
        .order_by(model.year, model.quarter)
        .limit(limit)
        .offset(offset)
        .all()
    )
    
    return features, total


def get_feature_stats(db: Session, product: str) -> dict:
    """
    Get statistics about available features for a product.
    
    Args:
        db: Database session
        product: Product type
    
    Returns:
        Dictionary with statistics (total records, date range, station count)
    """
    model = get_product_model(product)
    
    stats = db.query(
        func.count(model.feature_id).label("total_records"),
        func.count(func.distinct(model.station_id)).label("station_count"),
        func.min(model.year).label("min_year"),
        func.max(model.year).label("max_year"),
        func.min(model.quarter).label("min_quarter"),
        func.max(model.quarter).label("max_quarter"),
    ).first()
    
    return {
        "product": product,
        "total_records": stats.total_records or 0,
        "station_count": stats.station_count or 0,
        "min_year": stats.min_year,
        "max_year": stats.max_year,
        "min_quarter": stats.min_quarter,
        "max_quarter": stats.max_quarter,
    }


def get_available_products(db: Session) -> list[dict]:
    """
    Get list of available product types with record counts.
    
    Args:
        db: Database session
    
    Returns:
        List of product information dictionaries
    """
    products = []
    for product_name in PRODUCT_MODEL_MAP.keys():
        try:
            stats = get_feature_stats(db, product_name)
            products.append({
                "name": product_name,
                "table": PRODUCT_MODEL_MAP[product_name].__tablename__,
                "record_count": stats["total_records"],
                "station_count": stats["station_count"],
            })
        except Exception:
            # Skip products with errors
            continue
    
    return products
