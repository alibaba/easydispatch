from typing import Any, List, Optional
from fastapi.encoders import jsonable_encoder
from dispatch.auth.models import DispatchUser
from dispatch.plugins.kandbox_planner.util.kandbox_util import check_geo_range
from dispatch.team.service import get_by_code
from .models import Location, LocationCreate, LocationUpdate
from dispatch.auth import service as auth_service
import logging
log = logging.getLogger(__name__)

from dispatch.plugins.kandbox_planner.location_adapter.geocoding_cainiao import addr_geocoder


# def _check_location(location, flex_form_data):
#     flag = True
#     try:
#         if (
#             flex_form_data.get("longitude_diff_max")
#             and flex_form_data.get("longitude_diff_min")
#             and (
#                 location["longitude"] > flex_form_data.get("longitude_diff_max")
#                 or location["longitude"] < flex_form_data.get("longitude_diff_min")
#                 or location["latitude"] > flex_form_data.get("latitude_diff_max")
#                 or location["latitude"] < flex_form_data.get("latitude_diff_min")
#             )
#         ):
#             flag = False
#     except:
#         pass

#     return flag


def get(*, db_session, code: str) -> Optional[Location]:
    return db_session.query(Location).filter(
        Location.code == code).one_or_none()

# def get_by_location_code(*,
#                          db_session,
#                          location_code: str) -> Optional[Location]:
#     return db_session.query(Location).filter(
#         Location.code == location_code
#     ).one_or_none()


# Auth email refers to a Customer
def get_by_auth_email(*,
                      db_session,
                      email: str) -> List[Optional[Location]]:
    return db_session.query(Location).join(DispatchUser).filter(
        DispatchUser.email == email
    ).all()

# TODO, why _by_code in name? 2022-09-05 07:44:02
def get_or_create_by_code(*, db_session, location_in) -> Location:
    if location_in.code:  # location_in["code"]:
        q = db_session.query(Location).filter(
            Location.code == location_in.code)
    else:
        # return None
        raise Exception("The location.code can not be None.")

    instance = q.first()

    if instance:
        return instance

    return create(db_session=db_session, location_in=location_in)


def get_all(*, db_session) -> List[Optional[Location]]:
    return db_session.query(Location)


def create(*, db_session, location_in: LocationCreate) -> Location:
    location = location_in
    if type(location_in) != Location:
        loc_to_create = location_in

        if location_in.team is not None:
            team = get_by_code(db_session=db_session, code=location_in.team.code)
            loc_to_create.org_id = team.org_id
        else:
            team = None

        if location_in.dispatch_user is not None:
            user = auth_service.get_by_email(
                db_session=db_session, email=location_in.dispatch_user.email)
        else:
            user = None
        # loc_to_create = LocationCreate(**location)
        if loc_to_create.geo_address_text and not loc_to_create.geo_latitude:
            log.info(f"loc_to_create = {loc_to_create}, without loc_to_create.geo_latitude, starting parse_address")
            try:
                # nid = SHORTUUID.random(length=9)
                # location_config = {
                #     "url": config.LOCATION_SERVICE_URL,
                #     "token": config.LOCATION_SERVICE_TOKEN,
                #     "request_method": config.LOCATION_SERVICE_REQUEST_METHOD,
                # }
                payload = {
                    "address": loc_to_create.geo_address_text,
                    "regionCode": loc_to_create.region_code,
                    "language": loc_to_create.language,
                }
                # get location service
                # location_plugin = service_plugin_service.get_by_service_id_and_type(
                #     db_session=db_session,
                #     service_id=team_obj.service_id,
                #     service_plugin_type=KandboxPlannerPluginType.kandbox_location_service,
                # ).all()
                # location_plugin = plugins.get(location_plugin[0].plugin.slug)
                # location_adapter_service = location_plugin(config=location_config)
                _location_ret  = addr_geocoder.parse_address(payload)

                if _location_ret is not None:
                    checked = True
                    if team is not None:
                        checked = check_geo_range(
                            _location_ret["longitude"], _location_ret["latitude"],
                            team)
                        # checked = _check_location(_location_ret, team.flex_form_data)

                    if checked:
                        loc_to_create.geo_longitude = float(_location_ret['longitude'])
                        loc_to_create.geo_latitude = float(_location_ret['latitude'])
                        if loc_to_create.code is None:
                            loc_to_create.code = f"{round(loc_to_create.geo_longitude,5)}_{round(loc_to_create.geo_latitude,5)}"

                    else:
                        # logService.create(db_session=db_session, log_in=LogCreate(
                        #     title='Location Response Data OutSide', category='Location', content=f"location outside,job code:{code},input_address:{payload['input_address']}, msg:{str(_location_ret)}", org_id=int(org_id), team_id=team_obj.id))
                        log.error(
                            f"Location Response Data OutSide :{payload['address']}, {_location_ret=}")
                else:
                    # logService.create(db_session=db_session, log_in=LogCreate(
                    #     title=msg['type'], category='Location', content=f"job code:{code},input_address:{payload['input_address']},msg:{str(msg['msg'])}", org_id=int(org_id), team_id=team_obj.id))
                    log.error(
                        f"Location Response failed:{payload['address']}")
                    return None

            except Exception as e:
                log.error(f"address request error:{loc_to_create.geo_address_text},{ str(e)} ")
                return None


        location = Location(**location_in.dict(exclude={
            "team", "dispatch_user","overwrite", "region_code", "language"
            }), team=team, dispatch_user=user)
    db_session.add(location)
    db_session.commit()
    return location


def create_all(*, db_session,
               locations_in: List[LocationCreate]) -> List[Location]:
    locations = [Location(code=d.code) for d in locations_in]
    db_session.bulk_save_insert(locations)
    db_session.commit()
    db_session.refresh()
    return locations


def update(*, db_session, location: Location,
           location_in: LocationUpdate) -> Location:
    location_data = jsonable_encoder(location)

    update_data = location_in.dict(skip_defaults=True, exclude={"overwrite"})

    for field in location_data:
        if field in update_data:
            setattr(location, field, update_data[field])
    if location_in.team is not None:
        team = get_by_code(db_session=db_session, code=location_in.team.code)
    else:
        team = None
    location.team = team
    db_session.add(location)
    db_session.commit()
    return location


def delete(*, db_session, code: str):
    location = db_session.query(Location).filter(
        Location.code == code).first()

    db_session.delete(location)
    db_session.commit()


def upsert(*, db_session, location_in: LocationCreate) -> Location:
    # we only care about unique columns
    q = db_session.query(Location).filter(
        Location.code == location_in.code)
    instance = q.first()

    # there are no updatable fields
    if instance:
        return instance

    return create(db_session=db_session, location_in=location_in)

def search_by_location_group_code(*, db_session, location_group_code: str) ->List[Optional[Any]]:

    data_list =  db_session.query(
        Location.location_group_code
        ).filter(Location.location_group_code.like(f"%{location_group_code}%")
        ).distinct().limit(10).all()
    return [ i[0] for i in data_list]


