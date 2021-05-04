from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from dispatch.database import get_db, paginate
from dispatch.search.service import search

from .models import (
    Location,
    LocationCreate,
    LocationPagination,
    LocationRead,
    LocationUpdate,
)
from .service import create, delete, get, get_all, get_by_location_code, update

router = APIRouter()


@router.get("/", response_model=LocationPagination)
def get_locations(
    db_session: Session = Depends(get_db), page: int = 1, itemsPerPage: int = 5, q: str = None
):
    """
    Get all locations.
    """
    if q:
        query = search(db_session=db_session, query_str=q, model=Location)
    else:
        query = get_all(db_session=db_session)

    items, total = paginate(query=query, page=page, items_per_page=itemsPerPage)
    return {"items": items, "total": total}


@router.get("/{location_id}", response_model=LocationRead)
def get_location(*, db_session: Session = Depends(get_db), location_id: int):
    """
    Update a location.
    """
    location = get(db_session=db_session, location_id=location_id)
    if not location:
        raise HTTPException(status_code=404, detail="The location with this id does not exist.")
    return location


@router.post("/", response_model=LocationRead)
def create_location(*, db_session: Session = Depends(get_db), location_in: LocationCreate):
    """
    Create a new location.
    """
    location = get_by_location_code(db_session=db_session, location_code=location_in.location_code)
    if location:
        raise HTTPException(
            status_code=400,
            detail=f"The location with this location_code ({location_in.location_code}) already exists.",
        )
    location = create(db_session=db_session, location_in=location_in)
    return location


@router.put("/{location_id}", response_model=LocationRead)
def update_location(
    *, db_session: Session = Depends(get_db), location_id: int, location_in: LocationUpdate
):
    """
    Update a location.
    """
    location = get(db_session=db_session, location_id=location_id)
    if not location:
        raise HTTPException(status_code=404, detail="The location with this id does not exist.")
    location = update(db_session=db_session, location=location, location_in=location_in)
    return location


@router.delete("/{location_id}")
def delete_location(*, db_session: Session = Depends(get_db), location_id: int):
    """
    Delete a location.
    """
    location = get(db_session=db_session, location_id=location_id)
    if not location:
        raise HTTPException(status_code=404, detail="The location with this id does not exist.")
    delete(db_session=db_session, location_id=location_id)
