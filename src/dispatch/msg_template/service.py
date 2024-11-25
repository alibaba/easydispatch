import logging
from typing import List, Optional
from fastapi.encoders import jsonable_encoder

from .models import MsgTemplate, MsgTemplateCreate, MsgTemplateUpdate


log = logging.getLogger(__name__)


def get(*, db_session, id: int) -> Optional[MsgTemplate]:
    """Returns a msgTemplate based on the given msgTemplate id."""
    return db_session.query(MsgTemplate).filter(MsgTemplate.id == id).one_or_none()


def get_by_code(*, db_session, code: str) -> List[Optional[MsgTemplate]]:
    """Fetches all msgTemplates for a given type."""
    return db_session.query(MsgTemplate).filter(MsgTemplate.message_code == code).all()


def get_all(*, db_session) -> List[Optional[MsgTemplate]]:
    """Returns all msgTemplates."""
    return db_session.query(MsgTemplate)


def create(*, db_session, msg_template_in: MsgTemplateCreate) -> MsgTemplate:
    """Creates a new msgTemplate."""
    data = MsgTemplate(**msg_template_in.dict())
    db_session.add(data)
    db_session.commit()
    return data


def update(*, db_session, msg_template: MsgTemplate, msg_template_in: MsgTemplateUpdate) -> MsgTemplate:
    """Updates a msgTemplate."""
    _data = jsonable_encoder(msg_template)
    update_data = msg_template_in.dict(skip_defaults=True)
  
    for field in _data:
        if field in update_data:
            setattr(msg_template, field, update_data[field])

    db_session.add(msg_template)
    db_session.commit()
    return msg_template


def delete(*, db_session, id: int):
    """Deletes a msgTemplate."""
    db_session.query(MsgTemplate).filter(MsgTemplate.id == id).delete()
    db_session.commit()
