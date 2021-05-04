from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from dispatch.enums import Visibility
from dispatch.auth.models import DispatchUser
from dispatch.auth.service import get_current_user
from dispatch.database import get_db, search_filter_sort_paginate


from dispatch.auth.models import UserRoles
from .models import JobCreate, JobPagination, JobRead, JobUpdate
from .service import create, delete, get, update, get_by_code



router = APIRouter()


@router.get("/", response_model=JobPagination, summary="Retrieve a list of all jobs.")
def get_jobs(
    db_session: Session = Depends(get_db),
    page: int = 1,
    items_per_page: int = Query(5, alias="itemsPerPage"),
    query_str: str = Query(None, alias="q"),
    sort_by: List[str] = Query(None, alias="sortBy[]"),
    descending: List[bool] = Query(None, alias="descending[]"),
    fields: List[str] = Query([], alias="fields[]"),
    ops: List[str] = Query([], alias="ops[]"),
    values: List[str] = Query([], alias="values[]"),
    current_user: DispatchUser = Depends(get_current_user),
):
    """
    Retrieve a list of all jobs.
    """
    # we want to provide additional protections around restricted jobs
    # Because we want to proactively filter (instead of when the item is returned
    # we don't use fastapi_permissions acls.

    return search_filter_sort_paginate(
        db_session=db_session,
        model="Job",
        query_str=query_str,
        page=page,
        items_per_page=items_per_page,
        sort_by=sort_by,
        descending=descending,
        fields=fields,
        values=values,
        ops=ops,
        join_attrs=[("tag","requested_primary_worker")],
    )


@router.get("/{job_id}", response_model=JobRead, summary="Retrieve a single job.")
def get_job(
    *,
    db_session: Session = Depends(get_db),
    job_id: str,
    current_user: DispatchUser = Depends(get_current_user),
):
    """
    Retrieve details about a specific job.
    """
    job = get(db_session=db_session, job_id=job_id)
    if not job:
        raise HTTPException(status_code=404, detail="The requested job does not exist.")

    return job


@router.post("/", response_model=JobRead, summary="Create a new job.")
def create_job(
    *,
    db_session: Session = Depends(get_db),
    job_in: JobCreate,
    current_user: DispatchUser = Depends(get_current_user),
    background_tasks: BackgroundTasks,
):
    """
    Create a new job.
    """
    job = get_by_code(db_session=db_session, code=job_in.code)
    if job:
        raise HTTPException(status_code=400, detail="The job with this code already exists.")
    job = create(db_session=db_session, **job_in.dict())

    # background_tasks.add_task(job_create_flow, job_id=job.id)

    return job


@router.put("/{job_id}", response_model=JobRead, summary="Update an existing job.")
def update_job(
    *,
    db_session: Session = Depends(get_db),
    job_id: str,
    job_in: JobUpdate,
    current_user: DispatchUser = Depends(get_current_user),
    background_tasks: BackgroundTasks,
):
    """
    Update an worker job.
    """
    job = get(db_session=db_session, job_id=job_id)
    if not job:
        raise HTTPException(status_code=404, detail="The requested job does not exist.")

    previous_job = JobRead.from_orm(job)

    # NOTE: Order matters we have to get the previous state for change detection
    job = update(db_session=db_session, job=job, job_in=job_in)

    return job


@router.post("/{job_id}/join", summary="Join an job.")
def join_job(
    *,
    db_session: Session = Depends(get_db),
    job_id: str,
    current_user: DispatchUser = Depends(get_current_user),
    background_tasks: BackgroundTasks,
):
    """
    Join an worker job.
    """
    job = get(db_session=db_session, job_id=job_id)
    if not job:
        raise HTTPException(status_code=404, detail="The requested job does not exist.")

    background_tasks.add_task(
        job_add_or_reactivate_participant_flow, current_user.code, job_id=job.id
    )


@router.delete("/{job_id}", response_model=JobRead, summary="Delete an job.")
def delete_job(*, db_session: Session = Depends(get_db), job_id: str):
    """
    Delete an worker job.
    """
    job = get(db_session=db_session, job_id=job_id)
    if not job:
        raise HTTPException(status_code=404, detail="The requested job does not exist.")
    delete(db_session=db_session, job_id=job.id)


@router.get("/metric/forecast/{job_type}", summary="Get job forecast data.")
def get_job_forecast(*, db_session: Session = Depends(get_db), job_type: str):
    """
    Get job forecast data.
    """
    return make_forecast(db_session=db_session, job_type=job_type)
