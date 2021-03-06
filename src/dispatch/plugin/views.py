from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from dispatch.exceptions import InvalidConfiguration
from dispatch.database import get_db
from dispatch.database_util.service import common_parameters, search_filter_sort_paginate

from .models import PluginCreate, PluginPagination, PluginRead, PluginUpdate
from .service import get, update

router = APIRouter()


@router.get(
    "/", response_model=PluginPagination
)
def get_plugins(*, common: dict = Depends(common_parameters)):
    """
    """
    return search_filter_sort_paginate(model="Plugin", **common)


@router.get(
    "/{plugin_type}", response_model=PluginPagination
)
def get_plugins_by_type(*, common: dict = Depends(common_parameters)):
    """
    """
    return search_filter_sort_paginate(model="Plugin", **common)


@router.get("/{plugin_id}", response_model=PluginRead)
def get_plugin(*, db_session: Session = Depends(get_db), plugin_id: int):
    """
    Get a plugin.
    """
    plugin = get(db_session=db_session, plugin_id=plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail="The plugin with this id does not exist.")
    return plugin


@router.put("/{plugin_id}", response_model=PluginCreate)
def update_plugin(
    *, db_session: Session = Depends(get_db), plugin_id: int, plugin_in: PluginUpdate
):
    """
    Update a plugin.
    """
    plugin = get(db_session=db_session, plugin_id=plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail="The plugin with this id does not exist.")

    try:
        plugin = update(db_session=db_session, plugin=plugin, plugin_in=plugin_in)
    except InvalidConfiguration as e:
        raise HTTPException(status_code=400, detail=str(e))

    return plugin
