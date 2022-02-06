from sqlalchemy.sql.expression import true
from sqlalchemy_utils import get_mapper
from pydantic.error_wrappers import ErrorWrapper, ValidationError
from pydantic.main import BaseModel
from sqlalchemy import or_, orm, func, desc
from pydantic.types import Json, constr
from fastapi import Depends, Query

from sqlalchemy.orm import sessionmaker, object_session

from dispatch.exceptions import InvalidFilterError, NotFoundError
from dispatch.fulltext import make_searchable
from dispatch.plugins.kandbox_planner.util.cache_dict import CacheDict
from .config import SQLALCHEMY_DATABASE_URI
from dispatch.common.utils.composite_search import CompositeSearch
from starlette.requests import Request
from sqlalchemy.orm import Query, sessionmaker
from sqlalchemy.ext.declarative import declarative_base, declared_attr
from sqlalchemy import create_engine
from typing import Any, List
import re
import logging
from sqlalchemy import Table, Column, Integer, String, MetaData, ForeignKey

log = logging.getLogger(__file__)


QueryStr = constr(regex=r"^[ -~]+$", min_length=1)

engine = create_engine(
    str(SQLALCHEMY_DATABASE_URI),
    pool_size=40,
    max_overflow=20,
    # echo=True,
)
log.debug(f"database engine created:{engine}")
SessionLocal = sessionmaker(bind=engine)
engine_dict = CacheDict(cache_len=5)
session_dict = CacheDict(cache_len=5)
# sqlalchemy core
try:
    conn_core = engine.connect()
except:
    pass
metadata = MetaData(engine)
try:
    worker_table = Table('worker', metadata, autoload=True)
    job_table = Table('job', metadata, autoload=True)
    location_table = Table('location', metadata, autoload=True)
    event_table = Table('event', metadata, autoload=True)
except:
    print("Failed to load tables ... Ignore this if you are creating database ...")


def resolve_table_name(name):
    """Resolves table names to their mapped names."""
    # print("resolve_table_name", name)
    names = re.split("(?=[A-Z])", name)  # noqa
    return "_".join([x.lower() for x in names if x])


class CustomBase:
    # __table_args__ = {"schema": "duan2"}

    @declared_attr
    def __tablename__(self):
        return resolve_table_name(self.__name__)


Base = declarative_base(cls=CustomBase)
make_searchable(Base.metadata)


def init_schema(org_code, db_session):
    dump_file = "./org_template.sql"

    # import sh
    from sh import psql
    from dispatch.config import (
        DATABASE_HOSTNAME,
        DATABASE_NAME,
        DATABASE_PORT,  # DATABASE_CREDENTIALS,
    )

    #
    db_session.execute("CREATE USER org_template WITH ENCRYPTED PASSWORD  'org_template'")
    db_session.execute("CREATE SCHEMA org_template  AUTHORIZATION org_template ")
    db_session.commit()
    log.debug("USER org_template created ...")
    # DATABASE_CREDENTIALS=

    # username, password = str(DATABASE_CREDENTIALS).split(":")
    username = "org_template"

    password = None  # This should fail.
    raise Exception("Not implemented!")

    print(
        psql(
            "-h",
            DATABASE_HOSTNAME,
            "-p",
            DATABASE_PORT,
            "-U",
            username,
            "-d",
            DATABASE_NAME,
            "-f",
            dump_file,
            _env={"PGPASSWORD": password},
        )
    )

    db_session.execute(f"ALTER USER org_template rename to {org_code} ")
    db_session.execute(f"ALTER USER {org_code} PASSWORD '{org_code}' ")
    db_session.execute(f"ALTER SCHEMA org_template rename to {org_code} ")
    db_session.commit()
    log.debug(f"USER org_template is renamed to {org_code}...")


def get_db(request: Request):
    # https://docs.sqlalchemy.org/en/13/changelog/migration_11.html
    """
    request.state.db.connection(
        execution_options={"schema_translate_map": {None: request.state.org_code}}
    )
    """
    # TODO
    return request.state.auth_db
    # return request.state.db


def get_auth_db(request: Request):
    # return request.state.auth_db

    return request.state.auth_db


def get_model_name_by_tablename(table_fullname: str) -> str:
    """Returns the model name of a given table."""
    return get_class_by_tablename(table_fullname=table_fullname).__name__


def get_class_by_tablename(table_fullname: str) -> Any:
    """Return class reference mapped to table."""

    def _find_class(name):
        for c in Base._decl_class_registry.values():
            if hasattr(c, "__table__"):
                if c.__table__.fullname.lower() == name.lower():
                    return c

    mapped_name = resolve_table_name(table_fullname)
    mapped_class = _find_class(mapped_name)

    # try looking in the 'dispatch_core' schema
    if not mapped_class:
        mapped_class = _find_class(f"dispatch_core.{mapped_name}")

    if not mapped_class:
        raise ValidationError(
            [
                ErrorWrapper(
                    NotFoundError(msg="Model not found. Check the name of your model."),
                    loc="filter",
                )
            ],
            model=BaseModel,
        )

    return mapped_class


def get_table_name_by_class_instance(class_instance: Base) -> str:
    """Returns the name of the table for a given class instance."""
    return class_instance._sa_instance_state.mapper.mapped_table.name


def ensure_unique_default_per_project(target, value, oldvalue, initiator):
    """Ensures that only one row in table is specified as the default."""
    session = object_session(target)
    if session is None:
        return

    mapped_cls = get_mapper(target)

    if value:
        previous_default = (
            session.query(mapped_cls)
            .filter(mapped_cls.columns.default == true())
            .filter(mapped_cls.columns.project_id == target.project_id)
            .one_or_none()
        )
        if previous_default:
            # we want exclude updating the current default
            if previous_default.id != target.id:
                previous_default.default = False
                session.commit()
