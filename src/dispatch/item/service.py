
import json

# import random
from typing import List, Optional
from sqlalchemy.sql.functions import func
from tqdm import tqdm
from fastapi.encoders import jsonable_encoder

from dispatch.config import INCIDENT_PLUGIN_CONTACT_SLUG, SQLALCHEMY_DATABASE_URI
from dispatch.database import SessionLocal

from dispatch.location import service as location_service
from dispatch.plugin import service as plugin_service
from dispatch.plugins.base import plugins
from dispatch.team import service as team_service

from .models import Item, ItemCreate, ItemUpdate, ItemCreate


def get(*, db_session, item_id: int) -> Optional[Item]:
    """Returns an item given an item id."""
    return db_session.query(Item).filter(Item.id == item_id).one_or_none()


def get_by_code(*, db_session, code: str) -> Optional[Item]:
    """Returns an item given an item code address."""
    return db_session.query(Item).filter(Item.code == code).one_or_none()


def get_all(*, db_session) -> List[Optional[Item]]:
    """Returns all items."""
    return db_session.query(Item)


def get_by_team(*, team_id: int, db_session) -> List[Optional[Item]]:
    """Returns all items."""
    return db_session.query(Item).filter(Item.team_id == team_id).all()


def get_by_org_id_count(*, db_session, org_id: int) -> Optional[int]:
    """Returns an job based on the given code."""
    return db_session.query(func.count(Item.id)).filter(Item.org_id == org_id).scalar()


def get_or_create(*, db_session, code: str, **kwargs) -> Item:
    """Gets or creates an item."""
    item = get_by_code(db_session=db_session, code=code)

    if not item:
        item_plugin = plugin_service.get_active(db_session=db_session, plugin_type="item")
        item_info = item_plugin.instance.get(code, db_session=db_session)
        kwargs["code"] = item_info.get("code", code)
        kwargs["name"] = item_info.get("fullname", "Unknown")
        kwargs["weblink"] = item_info.get("weblink", "Unknown")
        item_in = ItemCreate(**kwargs)
        item = create(db_session=db_session, item_in=item_in)

    return item


def create(*, db_session, item_in: ItemCreate) -> Item:
    """Creates an item."""

    item = Item(**item_in.dict())
    db_session.add(item)
    db_session.commit()
    return item


def update(
    *,
    db_session,
    item: Item,
    item_in: ItemUpdate,
) -> Item:

    update_data = item_in.dict(
        skip_defaults=True,
        exclude={"flex_form_data"},
    )
    for field, field_value in update_data.items():
        setattr(item, field, field_value)

    item.flex_form_data = item_in.flex_form_data
    db_session.add(item)
    db_session.commit()
    return item


def delete(*, db_session, item_id: int):
    db_session.query(Item).filter(Item.id == item_id).delete()
    db_session.commit()
