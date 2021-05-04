from typing import List, Optional
from fastapi.encoders import jsonable_encoder

from .models import Location, LocationCreate, LocationUpdate


def get(*, db_session, location_id: int) -> Optional[Location]:
    return db_session.query(Location).filter(Location.id == location_id).first()


def get_by_location_code(*, db_session, location_code: str) -> Optional[Location]:
    return db_session.query(Location).filter(Location.location_code == location_code).first()


def get_or_create_by_code(*, db_session, location_in) -> Location:
    if location_in.location_code:  # location_in["location_code"]:
        q = db_session.query(Location).filter(Location.location_code == location_in.location_code)
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

    location = Location(**location_in.dict())
    db_session.add(location)
    db_session.commit()
    return location


def create_all(*, db_session, locations_in: List[LocationCreate]) -> List[Location]:
    locations = [Location(location_code=d.location_code) for d in locations_in]
    db_session.bulk_save_insert(locations)
    db_session.commit()
    db_session.refresh()
    return locations


def update(*, db_session, location: Location, location_in: LocationUpdate) -> Location:
    location_data = jsonable_encoder(location)

    update_data = location_in.dict(skip_defaults=True)

    for field in location_data:
        if field in update_data:
            setattr(location, field, update_data[field])

    db_session.add(location)
    db_session.commit()
    return location


def delete(*, db_session, location_id: int):
    location = db_session.query(Location).filter(Location.id == location_id).first()

    db_session.delete(location)
    db_session.commit()


def upsert(*, db_session, location_in: LocationCreate) -> Location:
    # we only care about unique columns
    q = db_session.query(Location).filter(Location.location_code == location_in.location_code)
    instance = q.first()

    # there are no updatable fields
    if instance:
        return instance

    return create(db_session=db_session, location_in=location_in)
