from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from dispatch.database import get_db, search_filter_sort_paginate

from .models import (
    WorkerCreate,
    WorkerPagination,
    WorkerRead,
    WorkerUpdate,
)
from .service import create, delete, get, get_by_code, update

router = APIRouter()


@router.get("/", response_model=WorkerPagination)
def get_workers(
    db_session: Session = Depends(get_db),
    page: int = 1,
    items_per_page: int = Query(5, alias="itemsPerPage"),
    query_str: str = Query(None, alias="q"),
    sort_by: List[str] = Query(None, alias="sortBy[]"),
    descending: List[bool] = Query(None, alias="descending[]"),
    fields: List[str] = Query(None, alias="field[]"),
    ops: List[str] = Query(None, alias="op[]"),
    values: List[str] = Query(None, alias="value[]"),
):
    """
    Retrieve worker contacts.
    """
    return search_filter_sort_paginate(
        db_session=db_session,
        model="Worker",
        query_str=query_str,
        page=page,
        items_per_page=items_per_page,
        sort_by=sort_by,
        descending=descending,
        fields=fields,
        values=values,
        ops=ops,
    )


@router.post("/", response_model=WorkerRead)
def create_worker(*, db_session: Session = Depends(get_db), worker_in: WorkerCreate):
    """
    Create a new worker contact.
    """
    worker = get_by_code(db_session=db_session, code=worker_in.code)
    if worker:
        raise HTTPException(status_code=400, detail="The worker with this code already exists.")
    worker = create(db_session=db_session, worker_in=worker_in)
    return worker


# @router.get("/{worker_id}/get_planned_jobs/{working_day}", response_model=WorkerRead)
# def get_worker(*, db_session: Session = Depends(get_db), worker_id: int):
#     """
#     Get a worker contact.
#     """
#     worker = get(db_session=db_session, worker_id=worker_id)
#     if not worker:
#         raise HTTPException(status_code=404, detail="The worker with this id does not exist.")
#     return worker




@router.get("/{worker_id}", response_model=WorkerRead)
def get_worker(*, db_session: Session = Depends(get_db), worker_id: int):
    """
    Get a worker contact.
    """
    worker = get(db_session=db_session, worker_id=worker_id)
    if not worker:
        raise HTTPException(status_code=404, detail="The worker with this id does not exist.")
    return worker


@router.put("/{worker_id}", response_model=WorkerRead)
def update_worker(
    *,
    db_session: Session = Depends(get_db),
    worker_id: int,
    worker_in: WorkerUpdate,
):
    """
    Update a worker contact.
    """
    worker = get(db_session=db_session, worker_id=worker_id)
    if not worker:
        raise HTTPException(status_code=204, detail="The worker with this id does not exist.")
    if not worker_in.location:
        raise HTTPException(status_code=206, detail="Please select a valid location code.")

    worker = update(
        db_session=db_session,
        worker=worker,
        worker_in=worker_in,
    )
    return worker


@router.delete("/{worker_id}")
def delete_worker(*, db_session: Session = Depends(get_db), worker_id: int):
    """
    Delete a worker contact.
    """
    worker = get(db_session=db_session, worker_id=worker_id)
    if not worker:
        raise HTTPException(status_code=404, detail="The worker with this id does not exist.")

    delete(db_session=db_session, worker_id=worker_id)
