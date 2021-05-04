from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from dispatch.database import get_db, search_filter_sort_paginate

from .models import (
    TeamCreate,
    TeamRead,
    TeamUpdate,
    TeamPagination,
)
from .service import create, delete, get, get_by_code, update

router = APIRouter()


@router.get("/", response_model=TeamPagination)
def get_teams(
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
    Get all team contacts.
    """
    return search_filter_sort_paginate(
        db_session=db_session,
        model="Team",
        query_str=query_str,
        page=page,
        items_per_page=items_per_page,
        sort_by=sort_by,
        descending=descending,
        fields=fields,
        values=values,
        ops=ops,
    )


@router.post("/", response_model=TeamRead)
def create_team(*, db_session: Session = Depends(get_db), team_contact_in: TeamCreate):
    """
    Create a new team contact.
    """
    team = get_by_code(db_session=db_session, code=team_contact_in.code)
    if team:
        raise HTTPException(status_code=400, detail="The team with this email already exists.")
    team = create(db_session=db_session, team_contact_in=team_contact_in)
    return team


@router.get("/{team_id}", response_model=TeamRead)
def get_team(*, db_session: Session = Depends(get_db), team_id: int):
    """
    Get a team contact.
    """
    team = get(db_session=db_session, team_id=team_id)
    if not team:
        raise HTTPException(status_code=204, detail="The team with this id does not exist.")
    return team


@router.put("/{team_id}", response_model=TeamRead)
def update_team(
    *,
    db_session: Session = Depends(get_db),
    team_id: int,
    team_contact_in: TeamUpdate,
):
    """
    Update a team contact.
    """
    team = get(db_session=db_session, team_id=team_id)
    if not team:
        raise HTTPException(status_code=404, detail="The team with this id does not exist.")
    team = update(db_session=db_session, team_contact=team, team_contact_in=team_contact_in)
    return team


@router.delete("/{team_id}", response_model=TeamRead)
def delete_team(*, db_session: Session = Depends(get_db), team_id: int):
    """
    Delete a team contact.
    """
    team = get(db_session=db_session, team_id=team_id)
    if not team:
        raise HTTPException(status_code=404, detail="The team with this id does not exist.")

    delete(db_session=db_session, team_id=team_id)
    return team
