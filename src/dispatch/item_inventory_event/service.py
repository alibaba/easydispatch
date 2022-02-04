import datetime
import logging

from uuid import uuid4

from typing import List, Optional

from fastapi.encoders import jsonable_encoder

from sqlalchemy.dialects.postgresql import UUID


from dispatch.depot import service as depot_service
from dispatch.item import service as item_service

from .models import ItemInventoryEvent, ItemInventoryEventCreate, ItemInventoryEventUpdate


logger = logging.getLogger(__name__)


def get(*, db_session, event_id: int) -> Optional[ItemInventoryEvent]:
    """
    Get an event by id.
    """
    return db_session.query(ItemInventoryEvent).filter(ItemInventoryEvent.id == event_id).one_or_none()


def get_by_uuid(*, db_session, uuid: UUID) -> Optional[ItemInventoryEvent]:
    """
    Get an event by uuid.
    """
    return db_session.query(ItemInventoryEvent).filter(ItemInventoryEvent.uuid == uuid).one_or_none()



def get_by_item_id_and_source(*, db_session, item_id: int, source: str) -> List[Optional[ItemInventoryEvent]]:
    """
    Get events by job id and source.
    """
    return db_session.query(ItemInventoryEvent).filter(ItemInventoryEvent.item_id == item_id).filter(ItemInventoryEvent.source == source)


def get_by_item_id_and_depot_id(
    *, db_session, item_id: int, depot_id: int
) -> List[Optional[ItemInventoryEvent]]:
    """
    Get events by job id and worker id.
    """
    return db_session.query(ItemInventoryEvent).filter(ItemInventoryEvent.item_id == item_id).filter(ItemInventoryEvent.depot_id == depot_id)


def get_all(*, db_session) -> List[Optional[ItemInventoryEvent]]:
    """
    Get all events.
    """
    return db_session.query(ItemInventoryEvent)


def create(*, db_session, event_in: ItemInventoryEventCreate) -> ItemInventoryEvent:
    """
    Create a new event.
    """
    event = ItemInventoryEvent(**event_in.dict())
    db_session.add(event)
    # db_session.commit()
    return event


def update(*, db_session, event: ItemInventoryEvent, event_in: ItemInventoryEventUpdate) -> ItemInventoryEvent:
    """
    Updates an event.
    """
    event_data = jsonable_encoder(event)
    update_data = event_in.dict(skip_defaults=True)

    for field in event_data:
        if field in update_data:
            setattr(event, field, update_data[field])

    db_session.add(event)
    db_session.commit()
    return event


def delete(*, db_session, event_id: int):
    """
    Deletes an event
    """
    event = db_session.query(ItemInventoryEvent).filter(ItemInventoryEvent.id == event_id).first()
    db_session.delete(event)
    db_session.commit()


def log(
    db_session,
    source: str,
    description: str,
    item_id: int = None,
    depot_id: int = None,
    item_code: str = None,
    depot_code: str = None,
    created_at: datetime = None,
    ended_at: datetime = None,
    details: dict = None,
) -> ItemInventoryEvent:
    """
    Logs an event
    """
    uuid = uuid4()

    if not created_at:
        created_at = datetime.datetime.utcnow()
    if not item_id:
        item = depot_service.get_by_code(db_session=db_session, code = item_code)
        item_id = item.id
    if not depot_id:
        depot = depot_service.get_by_code(db_session=db_session, code = depot_code)
        depot_id = depot.id

    event_in = ItemInventoryEventCreate(
        uuid=uuid,
        created_at=created_at,
        ended_at=ended_at,
        source=source,
        description=description,
        details=details,
        item_id  = item_id,
        depot_id = depot_id,
        item_code = item_code,
        depot_code = depot_code,
    )
    event = create(db_session=db_session, event_in=event_in)


    logger.info(f"item inventory event: {source}: {description}")

    return event
