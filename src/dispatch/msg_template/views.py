from typing import List

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from psycopg2 import IntegrityError
from sqlalchemy.orm import Session
from dispatch.auth.models import DispatchUser
from dispatch.auth.service import get_current_user

from dispatch.exceptions import InvalidConfiguration
from dispatch.database import get_db
from dispatch.database_util.service import common_parameters, search_filter_sort_paginate

from .models import MsgTemplateCreate, MsgTemplatePagination, MsgTemplateRead, MsgTemplateUpdate
from .service import get, update,delete,create,get_by_code

router = APIRouter()


@router.get(
    "/", response_model=MsgTemplatePagination
)
def get_routes(*, common: dict = Depends(common_parameters)):
    """
    """
    return search_filter_sort_paginate(model="MsgTemplate", **common)

@router.get("/{msg_template_id}", response_model=MsgTemplateRead)
def get_route(*, db_session: Session = Depends(get_db), msg_template_id: int):
    """
    Get a msg_template.
    """
    msg_template = get(db_session=db_session, id=msg_template_id)
    if not msg_template:
        raise HTTPException(status_code=404, detail="The msg_template with this id does not exist.")
    return msg_template

@router.post("/", response_model=MsgTemplateRead)
def create_route(
    *,
    db_session: Session = Depends(get_db),
    msg_template_in: MsgTemplateCreate = Body(
        ...,
        example={
        },
    ),
):
    """
    Create a new msg_template.
    """
    msg_template = get_by_code(db_session=db_session, code=msg_template_in.message_code)
    if msg_template:
        raise HTTPException(
            status_code=400,
            detail=f"The msg_template with this code ({msg_template_in.message_code}) already exists.",
        )
    msg_template = create(db_session=db_session, msg_template_in=msg_template_in)
    return msg_template

@router.put("/{msg_template_id}", response_model=MsgTemplateCreate)
def update_route(
    *, db_session: Session = Depends(get_db), msg_template_id: int, msg_template_in: MsgTemplateUpdate
):
    """
    Update a msg_template.
    """    
    msg_template = get(db_session=db_session, id=msg_template_id)
    if not msg_template:
        raise HTTPException(status_code=404, detail="The msg_template with this id does not exist.")

    try:
        msg_template = update(db_session=db_session, msg_template=msg_template, msg_template_in=msg_template_in)
    except InvalidConfiguration as e:
        raise HTTPException(status_code=400, detail=str(e))

    return msg_template

@router.delete("/{msg_template_id}")
def delete_route(*, db_session: Session = Depends(get_db), msg_template_id: int):
    """
    Delete a single msg_template.
    """
    data = get(db_session=db_session, id=msg_template_id)
    if not data:
        raise HTTPException(status_code=404, detail="The msg_template with this id does not exist.")
    try:
        delete(db_session=db_session, id=msg_template_id)
    except IntegrityError:
        raise HTTPException(
            status_code=400, detail="The msg_template is used by a team and can not be deleted.")
