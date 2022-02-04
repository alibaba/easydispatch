
import json


from typing import Dict, List, Optional
from sqlalchemy.sql.functions import func
from tqdm import tqdm
from fastapi.encoders import jsonable_encoder

from dispatch.location import service as location_service
from dispatch.plugin import service as plugin_service
from dispatch.team import service as team_service
from dispatch.depot import service as depot_service
from dispatch.item import service as item_service
from dispatch.item.models import Item

from .models import ItemInventory, ItemInventoryCreate, ItemInventoryUpdate, ItemInventoryCreate


def get(*, db_session, item_id: int) -> Optional[ItemInventory]:
    """Returns an item given an item id."""
    return db_session.query(ItemInventory).filter(ItemInventory.id == item_id).one_or_none()


def get_by_code(*, db_session, code: str) -> Optional[ItemInventory]:
    """Returns an item given an item code address."""
    return db_session.query(ItemInventory).filter(ItemInventory.code == code).one_or_none()


def get_all(*, db_session) -> List[Optional[ItemInventory]]:
    """Returns all items."""
    return db_session.query(ItemInventory)


def get_by_code_org_id(*, db_session, code: str, org_id: int) -> Optional[ItemInventory]:
    """Returns an worker given an worker code address."""
    return db_session.query(ItemInventory).filter(ItemInventory.code == code, ItemInventory.org_id == org_id).one_or_none()


def get_by_item_depot(*, db_session, item_id: int, depot_id: int, org_id: int) -> Optional[ItemInventory]:
    """Returns an worker given an worker code address."""
    return db_session.query(ItemInventory).filter(
        ItemInventory.item_id == item_id, 
        ItemInventory.depot_id == depot_id, 
        ItemInventory.org_id == org_id
    )


def get_by_depot_item_list(db_session,depot_id:int, requested_items: List[str]) -> Dict:
    """Returns all items."""
    return db_session.query(ItemInventory, Item).filter(
        ItemInventory.item_id == Item.id,
        ItemInventory.depot_id == depot_id,
        Item.code.in_(requested_items),
        ).all()


def get_by_org_id_count(*, db_session, org_id: int) -> Optional[int]:
    """Returns an job based on the given code."""
    return db_session.query(func.count(ItemInventory.id)).filter(ItemInventory.org_id == org_id).scalar()


def create(*, db_session, item_inventory_in: ItemInventoryCreate) -> ItemInventory:
    """Creates an item."""
    item = item_service.get_by_code(db_session=db_session, code=item_inventory_in.item.code)
    depot = depot_service.get_by_code(db_session=db_session, code=item_inventory_in.depot.code)

    item_inventory = ItemInventory(**item_inventory_in.dict(exclude={"item", "depot"}),
                            item=item, depot=depot)
    db_session.add(item_inventory)
    db_session.commit()
    return item_inventory


def update(
    *,
    db_session,
    item_inventory: ItemInventory,
    item_inventory_in: ItemInventoryUpdate,
) -> ItemInventory:

    update_data = item_inventory_in.dict(
        skip_defaults=True,
        exclude={"item", "depot"},
    )
    if item_inventory.depot.code != item_inventory_in.depot.code:
        depot = depot_service.get_by_code(db_session=db_session, code=item_inventory_in.depot.code)
        item_inventory.depot = depot
    if item_inventory.item.code != item_inventory_in.item.code:
        depot = item_service.get_by_code(db_session=db_session, code=item_inventory_in.depot.code)
        item_inventory.depot = depot
    for field, field_value in update_data.items():
        setattr(item_inventory, field, field_value)

    db_session.add(item_inventory)
    db_session.commit()
    return item_inventory


def delete(*, db_session, item_id: int):
    db_session.query(ItemInventory).filter(ItemInventory.id == item_id).delete()
    db_session.commit()
