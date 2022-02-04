
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

from .models import Depot, DepotCreate, DepotUpdate, DepotCreate


def get(*, db_session, depot_id: int) -> Optional[Depot]:
    """Returns an depot given an depot id."""
    return db_session.query(Depot).filter(Depot.id == depot_id).one_or_none()


def get_by_code(*, db_session, code: str) -> Optional[Depot]:
    """Returns an depot given an depot code address."""
    return db_session.query(Depot).filter(Depot.code == code).one_or_none()


def get_default_depot(*, db_session ) -> Optional[Depot]:
    """Returns an depot given an depot code address."""
    return db_session.query(Depot).first()


def get_all(*, db_session) -> List[Optional[Depot]]:
    """Returns all depots."""
    return db_session.query(Depot)


def get_by_code_org_id(*, db_session, code: str, org_id: int) -> Optional[Depot]:
    """Returns an worker given an worker code address."""
    return db_session.query(Depot).filter(Depot.code == code, Depot.org_id == org_id).one_or_none()


def get_by_team(*, team_id: int, db_session) -> List[Optional[Depot]]:
    """Returns all depots."""
    return db_session.query(Depot).filter(Depot.team_id == team_id).all()


def get_by_org_id_count(*, db_session, org_id: int) -> Optional[int]:
    """Returns an job based on the given code."""
    return db_session.query(func.count(Depot.id)).filter(Depot.org_id == org_id).scalar()


def get_or_create(*, db_session, code: str, **kwargs) -> Depot:
    """Gets or creates an depot."""
    contact = get_by_code(db_session=db_session, code=code)

    if not contact:
        contact_plugin = plugin_service.get_active(db_session=db_session, plugin_type="contact")
        depot_info = contact_plugin.instance.get(code, db_session=db_session)
        kwargs["code"] = depot_info.get("code", code)
        kwargs["name"] = depot_info.get("fullname", "Unknown")
        kwargs["weblink"] = depot_info.get("weblink", "Unknown")
        depot_in = DepotCreate(**kwargs)
        contact = create(db_session=db_session, depot_in=depot_in)

    return contact


def create(*, db_session, depot_in: DepotCreate) -> Depot:
    """Creates an depot."""
    location_obj = None
    if depot_in.location:
        location_obj = location_service.get_by_location_code(
            db_session=db_session, location_code=depot_in.location.location_code)
    else:
        location_obj = None

    contact = Depot(**depot_in.dict(exclude={"flex_form_data", "location"}),
                    location=location_obj, flex_form_data=depot_in.flex_form_data)
    db_session.add(contact)
    db_session.commit()
    return contact


def update(
    *,
    db_session,
    depot: Depot,
    depot_in: DepotUpdate,
) -> Depot:

    update_data = depot_in.dict(
        skip_defaults=True,
        exclude={"flex_form_data", "location"},
    )
    if depot_in.location and (not depot.location or depot_in.location.location_code != depot.location.location_code):
        location_obj = location_service.get_or_create_by_code(
            db_session=db_session, location_in=depot_in.location)
        depot.location = location_obj

    for field, field_value in update_data.items():
        setattr(depot, field, field_value)

    depot.flex_form_data = depot_in.flex_form_data
    db_session.add(depot)
    db_session.commit()
    return depot


def delete(*, db_session, depot_id: int):
    db_session.query(Depot).filter(Depot.id == depot_id).delete()
    db_session.commit()
