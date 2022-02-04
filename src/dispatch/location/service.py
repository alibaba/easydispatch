from typing import List, Optional
from fastapi.encoders import jsonable_encoder
from dispatch.auth.models import DispatchUser
from dispatch.team.service import get_by_code
from .models import Location, LocationCreate, LocationUpdate
from dispatch.auth import service as auth_service

def get(*, db_session, location_id: int) -> Optional[Location]:
    return db_session.query(Location).filter(
        Location.id == location_id).first()


def get_by_location_code(*,
                         db_session,
                         location_code: str) -> Optional[Location]:
    return db_session.query(Location).filter(
        Location.location_code == location_code
    ).one_or_none()
 

# Auth email refers to a Customer
def get_by_auth_email(*,
                db_session,
                email: str) -> List[Optional[Location]]:
    return db_session.query(Location).join(DispatchUser).filter(
         DispatchUser.email == email
    ).all()

def get_or_create_by_code(*, db_session, location_in) -> Location:
    if location_in.location_code:  # location_in["location_code"]:
        q = db_session.query(Location).filter(
            Location.location_code == location_in.location_code)
    else:
        # return None
        raise Exception("The location_code can not be None.")

    instance = q.first()

    if instance:
        return instance

    return create(db_session=db_session, location_in=location_in)


def get_all(*, db_session) -> List[Optional[Location]]:
    return db_session.query(Location)


def create(*, db_session, location_in: LocationCreate) -> Location:
    location = location_in
    if type(location_in) != Location:
        if location_in.team is not None:
            team = get_by_code(db_session=db_session, code=location_in.team.code)
        else:
            team = None

        if location_in.dispatch_user is not None:
            user = auth_service.get_by_email(db_session=db_session, email=location_in.dispatch_user.email)
        else:
            user = None

        location = Location(**location_in.dict(exclude={"team","dispatch_user"}),
                            team=team, dispatch_user=user)
    db_session.add(location)
    db_session.commit()
    return location


def create_all(*, db_session,
               locations_in: List[LocationCreate]) -> List[Location]:
    locations = [Location(location_code=d.location_code) for d in locations_in]
    db_session.bulk_save_insert(locations)
    db_session.commit()
    db_session.refresh()
    return locations


def update(*, db_session, location: Location,
           location_in: LocationUpdate) -> Location:
    location_data = jsonable_encoder(location)

    update_data = location_in.dict(skip_defaults=True)

    for field in location_data:
        if field in update_data:
            setattr(location, field, update_data[field])

    db_session.add(location)
    db_session.commit()
    return location


def delete(*, db_session, location_id: int):
    location = db_session.query(Location).filter(
        Location.id == location_id).first()

    db_session.delete(location)
    db_session.commit()


def upsert(*, db_session, location_in: LocationCreate) -> Location:
    # we only care about unique columns
    q = db_session.query(Location).filter(
        Location.location_code == location_in.location_code)
    instance = q.first()

    # there are no updatable fields
    if instance:
        return instance

    return create(db_session=db_session, location_in=location_in)
