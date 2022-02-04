from dispatch.auth.views import auth_router
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from dispatch.auth.models import DispatchUser
from dispatch.auth.service import get_current_user
from dispatch.database import get_db

from dispatch.database_util.service import common_parameters, search_filter_sort_paginate
from dispatch.depot.models import Depot
from dispatch.item.models import Item

from .models import (
    ItemInventory,
    ItemInventoryCreate,
    ItemInventoryPagination,
    ItemInventoryRead,
    ItemInventorySelect,
    ItemInventoryUpdate,
)
from .service import create, delete, get, get_by_code, get_by_code_org_id, get_by_item_depot, update

router = APIRouter()


@router.get(
    "/", response_model=ItemInventoryPagination
)
def get_items(*, common: dict = Depends(common_parameters)):
    """
    """
    return search_filter_sort_paginate(model="ItemInventory", **common)


@router.get("/select/", response_model=ItemInventoryPagination)
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
        "items": db_session.query(ItemInventory).filter(ItemInventory.org_id == current_user.org_id, ItemInventory.code.like(f'%{query_str}%')).limit(10).all(),
        "itemsPerPage": 0,
        "page": 1,
        "total": 0,
    }


@router.post("/", response_model=ItemInventoryRead)
def create_item(*, db_session: Session = Depends(get_db), item_inventory_in: ItemInventoryCreate,
                current_user: DispatchUser = Depends(get_current_user)):
    """
    Create a new item contact.
    """
    item = get_by_item_depot(db_session=db_session,
                             item_id=item_inventory_in.item.id, depot_id=item_inventory_in.depot.id, org_id=current_user.org_id
                             ).one_or_none()
    if item:
        raise HTTPException(
            status_code=400, detail="The item_invetory with this code already exists.")
    item_inventory_in.org_id = current_user.org_id
    item = create(db_session=db_session, item_inventory_in=item_inventory_in)
    return item


@router.get("/{item_id}", response_model=ItemInventoryRead)
def get_item(*, db_session: Session = Depends(get_db), item_id: int):
    """
    Get a item contact.
    """
    item = get(db_session=db_session, item_id=item_id)
    if not item:
        raise HTTPException(
            status_code=404, detail="The item_invetory with this id does not exist.")
    return item


@router.put("/{item_id}", response_model=ItemInventoryRead)
def update_item(
    *,
    db_session: Session = Depends(get_db),
    item_id: int,
    item_in: ItemInventoryUpdate, current_user: DispatchUser = Depends(get_current_user)
):
    """
    Update a item contact.
    """
    item_in.org_id = current_user.org_id
    item = get(db_session=db_session, item_id=item_id)
    if not item:
        raise HTTPException(
            status_code=404, detail="The item_invetory with this id does not exist.")
    item = update(
        db_session=db_session,
        item_inventory=item,
        item_inventory_in=item_in,
    )
    return item


def update_item_by_code(
    *,
    db_session: Session = Depends(get_db),
    item_code: str,
    item_in: ItemInventoryUpdate, current_user: DispatchUser = Depends(get_current_user)
):
    """
    Update a item contact.
    """
    item_in.org_id = current_user.org_id
    item = get_by_code_org_id(db_session=db_session, code=item_code, org_id=current_user.org_id)
    if not item:
        raise HTTPException(status_code=404, detail="The item with this id does not exist.")

    item = update(
        db_session=db_session,
        item_inventory=item,
        item_inventory_in=item_in,
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


@auth_router.get("/item_inventory/get_all/", response_model=List[ItemInventorySelect])
def select_all_items(
    db_session: Session = Depends(get_db),
):
    """
    Retrieve item contacts.
    """
    data = db_session.query(ItemInventory).filter(
        Item.is_active == True, Depot.is_active == True).all()
    # TODO allocated_qty - job used qty
    return_data = [] if not data else [
        {
            "text": f"{i.item.code}",
            "all": i.curr_qty,
            "input_value": 0,
        } for i in data]
    return return_data
