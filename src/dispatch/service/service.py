from typing import Optional

from fastapi.encoders import jsonable_encoder
from dispatch.config import ONCALL_PLUGIN_SLUG
from dispatch.service_plugin import flows as service_plugin_flows

from .models import Service, ServiceCreate, ServiceUpdate


def get(*, db_session, service_id: int) -> Optional[Service]:
    return db_session.query(Service).filter(Service.id == service_id).first()


def get_by_name(*, db_session, name: str) -> Optional[Service]:
    return db_session.query(Service).filter(Service.name == name).first()


def get_by_code(*, db_session, code: str) -> Optional[Service]:
    return db_session.query(Service).filter(Service.code == code).first()


def get_all(*, db_session):
    return db_session.query(Service)


def get_all_by_status(*, db_session, is_active: bool):
    return db_session.query(Service).filter(Service.is_active.is_(is_active))


def create(*, db_session, service_in: ServiceCreate) -> Service:
    service = Service(**service_in.dict())
    db_session.add(service)
    db_session.commit()
    return service


def update(*, db_session, service: Service, service_in: ServiceUpdate) -> Service:
    service_data = jsonable_encoder(service)

    update_data = service_in.dict(skip_defaults=True)

    for field in service_data:
        if field in update_data:
            setattr(service, field, update_data[field])

    db_session.add(service)
    db_session.commit()
    return service


def delete(*, db_session, service_id: int):
    service = db_session.query(Service).filter(Service.id == service_id).one()

    # TODO clear out other relationships
    # we clear out our associated items

    service.terms = []
    db_session.delete(service)
    db_session.commit()

    return service_id
