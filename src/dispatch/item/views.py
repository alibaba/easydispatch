from dispatch.database import get_db
from dispatch.org import service as orgService
import random
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from dispatch.auth.models import DispatchUser
from dispatch.auth.service import get_current_user


from dispatch.database_util.service import common_parameters, search_filter_sort_paginate
from .models import (
    Item,
    ItemCreate,
    ItemPagination,
    ItemRead,
    ItemUpdate,
)
from .service import create, delete, get, get_by_code, update

router = APIRouter()


@router.get(
    "/", response_model=ItemPagination
)
def get_items(*, common: dict = Depends(common_parameters)):
    """
    """
    return search_filter_sort_paginate(model="Item", **common)


@router.get("/select/", response_model=ItemPagination)
def select_items(
    db_session: Session = Depends(get_db),
    page: int = 1,
    items_per_page: int = Query(5, alias="itemsPerPage"),
    query_str: str = Query(None, alias="q"),
    sort_by: List[str] = Query(None, alias="sortBy[]"),
    descending: List[bool] = Query(None, alias="descending[]"),
    fields: List[str] = Query([], alias="field[]"),
    ops: List[str] = Query([], alias="op[]"),
    values: List[str] = Query([], alias="value[]"),
    current_user: DispatchUser = Depends(get_current_user),
):
    """
    Retrieve item contacts.
    """

    return {
        "items": db_session.query(Item).filter(Item.org_id == current_user.org_id, Item.code.like(f'%{query_str}%')).limit(10).all(),
        "itemsPerPage": 0,
        "page": 1,
        "total": 0,
    }


@router.post("/", response_model=ItemRead)
def create_item(*, db_session: Session = Depends(get_db), item_in: ItemCreate,
                current_user: DispatchUser = Depends(get_current_user)):
    """
    Create a new item contact.
    """
    # limit max
    org_data = orgService.get(db_session=db_session, org_code=current_user.org_code)
    if not org_data:
        raise HTTPException(status_code=400, detail="org not exists")
    # max_nbr_item = org_data.max_nbr_items

    # job_all_count = get_by_org_id_count(db_session=db_session, org_id=current_user.org_id)
    # if job_all_count >= max_nbr_item:
    #     raise HTTPException(status_code=400, detail="Item Reached the upper limit")
    item_in.org_id = current_user.org_id
    item = get_by_code(db_session=db_session, code=item_in.code)
    if item:
        raise HTTPException(status_code=400, detail="The item with this code already exists.")
    item = create(db_session=db_session, item_in=item_in)
    return item


@router.get("/{item_id}", response_model=ItemRead)
def get_item(*, db_session: Session = Depends(get_db), item_id: int):
    """
    Get a item contact.
    """
    item = get(db_session=db_session, item_id=item_id)
    if not item:
        raise HTTPException(status_code=404, detail="The item with this id does not exist.")
    return item


@router.put("/{item_id}", response_model=ItemRead)
def update_item(
    *,
    db_session: Session = Depends(get_db),
    item_id: int,
    item_in: ItemUpdate, current_user: DispatchUser = Depends(get_current_user)
):
    """
    Update a item contact.
    """
    item_in.org_id = current_user.org_id
    item = get(db_session=db_session, item_id=item_id)
    if not item:
        raise HTTPException(status_code=404, detail="The item with this id does not exist.")
    item = update(
        db_session=db_session,
        item=item,
        item_in=item_in,
    )
    return item


@router.put("/item_code/{item_code}", response_model=ItemRead)
def update_item_by_code(
    *,
    db_session: Session = Depends(get_db),
    item_code: str,
    item_in: ItemUpdate, current_user: DispatchUser = Depends(get_current_user)
):
    """
    Update a item contact.
    """
    item_in.org_id = current_user.org_id
    item = get_by_code(db_session=db_session, code=item_code)
    if not item:
        raise HTTPException(status_code=404, detail="The item with this id does not exist.")

    item = update(
        db_session=db_session,
        item=item,
        item_in=item_in,
    )

    return item


@router.delete("/{item_id}")
def delete_item(*, db_session: Session = Depends(get_db), item_id: int):
    """
    Delete a item contact.
    """
    item = get(db_session=db_session, item_id=item_id)
    if not item:
        raise HTTPException(status_code=404, detail="The item with this id does not exist.")

    delete(db_session=db_session, item_id=item_id)
