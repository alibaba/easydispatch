import json
# import pdb
# from dispatch.database import SessionLocal
import redis
from dispatch.config import REDIS_HOST, REDIS_PORT, REDIS_PASSWORD
from typing import List, Optional

from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.sql.functions import func
from dispatch.planner_service import service as service_service
from .models import Team, TeamCreate, TeamUpdate

from sqlalchemy.orm.session import sessionmaker
from dispatch.database import engine
import logging
log = logging.getLogger(__name__)


#


def get(*, db_session, team_id: int) -> Optional[Team]:
    return db_session.query(Team).filter(Team.id == team_id).first()


def get_by_code(*, db_session, code: str) -> Optional[Team]:
    return db_session.query(Team).filter(Team.code == code).first()


def get_by_id(*, db_session, id: str) -> Optional[Team]:
    return db_session.query(Team).filter(Team.id == id).first()


def get_by_org_id(*, db_session, org_id: int) -> List[Optional[Team]]:
    return db_session.query(Team).filter(Team.org_id == org_id).all()


def get_by_org_id_count(*, db_session, org_id: int) -> Optional[int]:
    """Returns an job based on the given code."""
    return db_session.query(func.count(Team.id)).filter(Team.org_id == org_id).scalar()


def get_all(*, db_session) -> List[Optional[Team]]:
    return db_session.query(Team)


def get_by_org_id_list(*, db_session, org_id: int) -> Optional[Team]:
    return db_session.query(Team).filter(Team.org_id == org_id).all()


# def get_or_create(*, db_session, email: str, **kwargs) -> Team:
#     contact = get_by_code(db_session=db_session, code=email)

#     if not contact:
#         team_contact = TeamCreate(code=email, **kwargs)
#         contact = create(db_session=db_session, team_contact_in=team_contact)

#     return contact


def create(*, db_session, team_contact_in: TeamCreate) -> Team:
    planner_service = None
    if team_contact_in.planner_service:
        planner_service = service_service.get_by_code_and_org_code(
            db_session=db_session,
            code=team_contact_in.planner_service.code,
            # org_id=team_contact_in.org_id,
        )
    else:
        planner_service = None
    team = Team(
        **team_contact_in.dict(exclude={"planner_service"}),
        # service_id=planner_service.id
        planner_service=planner_service,
    )
    db_session.add(team)
    db_session.commit()
    # add_redis_team_flex_data(team)
    return team


def create_all(*, db_session, team_contacts_in: List[TeamCreate]) -> List[Team]:
    contacts = [Team(**t.dict()) for t in team_contacts_in]
    db_session.bulk_save_objects(contacts)
    db_session.commit()
    return contacts


def update(*, db_session, team_contact: Team, team_contact_in: TeamUpdate) -> Team:
    team_contact_data = jsonable_encoder(team_contact)
    if int(team_contact_in.id) != int(team_contact.id):
        log.warning(f"Updating team id is not allowed. {team_contact=} \n {team_contact_in=}")
        return None


    planner_service = None
    if team_contact_in.planner_service:
        planner_service = service_service.get_by_code_and_org_code(
            db_session=db_session,
            code=team_contact_in.planner_service.code,
            # org_id=team_contact_in.planner_service.org_id,
        )

    update_data = team_contact_in.dict(
        exclude_unset=True, exclude={"planner_service", "flex_form_data"}
    )

    for field in team_contact_data:
        if field in update_data:
            setattr(team_contact, field, update_data[field])

    # TODO, clean up. 2021-06-14 07:31:54
    # Replaced by nbr_planning_days
    # team_contact.flex_form_data['nbr_of_days_planning_window'] = int(
    #     team_contact.flex_form_data['nbr_of_days_planning_window'])

    team_contact.planner_service = planner_service
    if team_contact_in.flex_form_data is not None:
        for field in team_contact_in.flex_form_data:
            team_contact.flex_form_data[field] = team_contact_in.flex_form_data[field]
        flag_modified(team_contact, "flex_form_data")

    db_session.add(team_contact)
    db_session.commit()
    # add_redis_team_flex_data(team_contact)
    return team_contact


def update_planning_window_db(
    *,
    db_session,
    team_id: int,
    env_start_datetime: str,
    nbr_minutes_planning_windows_duration=None,
    begin_skip_minutes=None,
) -> Team:
    try:
        team = db_session.query(Team).filter(Team.id == team_id).first()

        team.flex_form_data["env_start_datetime"] = env_start_datetime
        if nbr_minutes_planning_windows_duration:
            team.flex_form_data["nbr_minutes_planning_windows_duration"] = str(int(nbr_minutes_planning_windows_duration))
        if begin_skip_minutes:
            team.flex_form_data["begin_skip_minutes"] = int(begin_skip_minutes)
        flag_modified(team, "flex_form_data")
        db_session.add(team)
        db_session.commit()
        return team
    except Exception as e:
        print(f"update_planning_window_db error :team_id {team_id},{e}")
    


def team_update_offset(*, db_session, id: int, offset: int) -> Team:
    try:
        team = db_session.query(Team).filter(Team.id == id).first()
        team.callback_offset = offset
        db_session.add(team)
        db_session.commit()
    except Exception as e:
        print(f"team_update_offset error :{e}")
    return team


def delete(*, db_session, team_id: int):
    db_session.query(Team).filter(Team.id == team_id).delete()
    # team = db_session.query(Team).filter(Team.id == team_id).first()
    # team.terms = []
    # db_session.delete(team)
    db_session.commit()


def add_redis_team_flex_data(team):
    assert False, "Why this?"
    if REDIS_PASSWORD == "":
        redis_conn = redis.Redis(
            host=REDIS_HOST, port=REDIS_PORT, password=None, decode_responses=True
        )
    else:
        redis_conn = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            password=REDIS_PASSWORD,
            decode_responses=True,
        )

    key_flex_form_data = f"{team.id}_flex_form_data"
    redis_conn.set(key_flex_form_data, json.dumps(team.flex_form_data))


def _get_schema_session(org_code):
    schema_engine = engine.execution_options(
        schema_translate_map={None: f"dispatch_organization_{org_code}"}
    )
    schema_session = sessionmaker(bind=schema_engine)()
    return schema_session


# def get_or_add_redis_team_flex_data(redis_conn, team_id, org_code):
#     flex_form_data = {}
#     try:
#         db_session = None
#         key = f"{team_id}_flex_form_data"
#         if redis_conn.exists(key) <= 0:
#             db_session = _get_schema_session(org_code)
#             team_data = get(db_session=db_session, team_id=team_id)
#             redis_conn.set(key, json.dumps(team_data.flex_form_data))
#             flex_form_data = team_data.flex_form_data
#         else:
#             value = redis_conn.get(key)
#             if isinstance(value, bytes):
#                 value = value.decode("utf-8")
#             flex_form_data = json.loads(value)
#     except:
#         pass
#     finally:
#         if db_session:
#             db_session.close()

#     return flex_form_data
