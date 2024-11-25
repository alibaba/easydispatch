from typing import List, Optional
from fastapi.encoders import jsonable_encoder
from dispatch import config
from dispatch.auth.models import DispatchUser
from dispatch.team import service as team_service # import get_by_code
from .models import LocationGroup, LocationGroupCreate, LocationGroupUpdate
from dispatch.auth import service as auth_service
from dispatch.worker import service as   worker_service
from dispatch.worker.models import Worker
from datetime import datetime

from sqlalchemy.orm import aliased

def get(*, db_session, code: str) -> Optional[LocationGroup]:
    return db_session.query(LocationGroup).filter(
        LocationGroup.code == code).first()



# Auth email refers to a Customer
def get_by_auth_email(*,
                      db_session,
                      email: str) -> List[Optional[LocationGroup]]:
    return db_session.query(LocationGroup).join(DispatchUser).filter(
        DispatchUser.email == email
    ).all()

# TODO, why _by_code in name? 2022-09-05 07:44:02
def get_or_create_by_code(*, db_session, location_group_in) -> LocationGroup:
    if location_group_in.code:  # location_group_in["code"]:
        q = db_session.query(LocationGroup).filter(
            LocationGroup.code == location_group_in.code)
    else:
        # return None
        raise Exception("The code can not be None.")

    instance = q.first()

    if instance:
        return instance

    return create(db_session=db_session, location_group_in=location_group_in)


def get_all(*, db_session) -> List[Optional[LocationGroup]]:
    return db_session.query(LocationGroup)            


def get_query_all_with_worker_code(*, db_session) -> List[Optional[LocationGroup]]:

    _PrimaryWorker = aliased(Worker)
    _ReplacementWorker = aliased(Worker) 
    curr_day_str = datetime.strftime(datetime.now(), "%Y-%m-%d")

    orig_query = db_session.query(
        LocationGroup.code, 
        _PrimaryWorker.code.label("worker_code"), 
        ).filter( 
            _PrimaryWorker.code == LocationGroup.requested_primary_worker_code,
        ).all()

    replace_query = db_session.query(
        LocationGroup.code, 
        _ReplacementWorker.code.label("worker_code"), 
        ).filter( 
            _ReplacementWorker.code == LocationGroup.replacement_worker_code,
        ).filter( 
            curr_day_str >= LocationGroup.replacement_start_day,
        ).filter( 
            curr_day_str < LocationGroup.replacement_end_day,
        ).all()


    location_group2worker_mapping = {}
    for queried in [orig_query, replace_query]:
        for _, x in enumerate(queried):
            location_group2worker_mapping[x.code] = x.worker_code
    return location_group2worker_mapping 



def get_worker_code_by_location_group_code(*, db_session, location_group_code) -> str:
    curr_day_str = datetime.strftime(datetime.now(), config.KANDBOX_DAY_FORMAT_ISO) 
    replace_query = db_session.query(
        LocationGroup
        ).filter( 
            LocationGroup.code == location_group_code, 
        ).one_or_none()
    if not replace_query:
        return None

    if replace_query.replacement_start_day is None or replace_query.replacement_end_day is None:
         return replace_query.requested_primary_worker_code
    
    if  (curr_day_str >= replace_query.replacement_start_day and  curr_day_str < replace_query.replacement_end_day):
        return replace_query.replacement_worker_code
    else:
        return replace_query.requested_primary_worker_code

def create(*, db_session, location_group_in: LocationGroupCreate) -> LocationGroup:
    location_group = location_group_in
    if type(location_group_in) != LocationGroup:
        if location_group_in.team is not None:
            team = team_service.get_by_code(db_session=db_session, code=location_group_in.team.code)
        else:
            team = None

        if location_group_in.requested_primary_worker is not None:
            requested_primary_worker = worker_service.get_by_code(
                db_session=db_session, 
                code=location_group_in.requested_primary_worker.code)
        else:
            requested_primary_worker = None

        if location_group_in.replacement_worker is not None:
            if requested_primary_worker is None:
                raise ValueError(f"requested_primary_worker must be valid if replacement_worker is present")
            if requested_primary_worker.code  == location_group_in.replacement_worker.code:
                raise ValueError(f"requested_primary_worker can not be same as replacement_worker!")

            replacement_worker = worker_service.get_by_code(
                db_session=db_session, 
                code=location_group_in.replacement_worker.code)
        else:
            replacement_worker = None

        location_group = LocationGroup(
            **location_group_in.dict(exclude={"team","requested_primary_worker", "replacement_worker"}),
            team=team,
            requested_primary_worker = requested_primary_worker,
            replacement_worker = replacement_worker
        )
    db_session.add(location_group)
    db_session.commit()
    return location_group


def create_all(*, db_session,
               location_groups_in: List[LocationGroupCreate]) -> List[LocationGroup]:
    locations = [LocationGroup(code=d.code) for d in location_groups_in]
    db_session.bulk_save_insert(locations)
    db_session.commit()
    db_session.refresh()
    return locations


def update(*, db_session, location_group: LocationGroup,
           location_group_in: LocationGroupUpdate) -> LocationGroup:
    location_data = jsonable_encoder(location_group)

    update_data = location_group_in.dict(skip_defaults=True, exclude={"team","requested_primary_worker", "replacement_worker"})

    for field in location_data:
        if field in update_data:
            setattr(location_group, field, update_data[field])

    if location_group_in.requested_primary_worker is not None:
        requested_primary_worker = worker_service.get_by_code(
            db_session=db_session, 
            code=location_group_in.requested_primary_worker.code)
    else:
        requested_primary_worker = None

    if location_group_in.replacement_worker is not None:
        replacement_worker = worker_service.get_by_code(
            db_session=db_session, 
            code=location_group_in.replacement_worker.code)
    else:
        replacement_worker = None

    if location_group_in.team is not None:
        team = team_service.get_by_code(db_session=db_session, code=location_group_in.team.code)
        location_group.team = team
    # else:
    #     team = None
    location_group.requested_primary_worker = requested_primary_worker
    location_group.replacement_worker = replacement_worker
    db_session.add(location_group)
    db_session.commit()
    return location_group


def delete(*, db_session, code: str):
    location_group = db_session.query(LocationGroup).filter(
        LocationGroup.code == code).first()

    db_session.delete(location_group)
    db_session.commit()


def delete_by_requested_primary_worker_code(*, db_session, requested_primary_worker_code: str) -> Optional[LocationGroup]:
    db_session.query(LocationGroup).filter(
        LocationGroup.requested_primary_worker_code == requested_primary_worker_code).delete()
    db_session.commit()


def upsert(*, db_session, location_group_in: LocationGroupCreate) -> LocationGroup:
    # we only care about unique columns
    q = db_session.query(LocationGroup).filter(
        LocationGroup.code == location_group_in.code)
    instance = q.first()

    # there are no updatable fields
    if instance:
        return instance

    return create(db_session=db_session, location_group_in=location_group_in)
