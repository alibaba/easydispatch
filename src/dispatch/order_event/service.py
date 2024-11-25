import datetime
from typing import List, Optional
from sqlalchemy.orm import Session


from dispatch.order_event.models import OrderEvent, OrderEventCreate



def get(*, db_session, id: int) -> Optional[OrderEvent]:
    """Returns a plugin based on the given plugin id."""
    return db_session.query(OrderEvent).filter(OrderEvent.id == id).one_or_none()


def get_by_order_code(*, db_session, order_code: str) -> List[Optional[OrderEvent]]:
    """Fetches all Order for a given type."""
    return db_session.query(OrderEvent).filter(OrderEvent.order_code == order_code).all()

def get_by_order_code_and_type(*, db_session, order_code: str,event_type:str) -> List[Optional[OrderEvent]]:
    """Fetches all Order for a given type."""
    return db_session.query(OrderEvent).filter(OrderEvent.order_code == order_code , OrderEvent.event_type==event_type).all()

def get_by_order_code_and_source(*, db_session, order_code: str,source:str) -> List[Optional[OrderEvent]]:
    """Fetches all Order for a given type."""
    return db_session.query(OrderEvent).filter(OrderEvent.order_code == order_code , OrderEvent.source==source).all()

def get_by_order_code_and_job_id(*, db_session, order_code: str,linked_job_id:int) -> List[Optional[OrderEvent]]:
    """Fetches all Order for a given type."""
    return db_session.query(OrderEvent).filter(OrderEvent.order_code == order_code , OrderEvent.linked_job_id==linked_job_id).all()

def get_all(*, db_session) -> List[Optional[OrderEvent]]:
    """Returns all Order."""
    return db_session.query(OrderEvent)


def add(*,db_session: Session,order_event: OrderEventCreate)->OrderEvent:
    order =  OrderEvent(**order_event.dict())
    db_session.add(order)
    db_session.commit()
    return order_event



def delete(*, db_session, order_code: str,job_code:str):
    """
    Deletes an event
    """
    event = db_session.query(OrderEvent).filter(
        OrderEvent.job_code == job_code
    ).first()
    db_session.delete(event)
    db_session.commit()