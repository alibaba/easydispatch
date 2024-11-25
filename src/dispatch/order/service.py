import uuid
import datetime
import dataclasses
import tempfile
from typing import Any, List, Optional
from uuid import uuid4

# import oss2
import requests
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
import sqlalchemy
# from py import code

from sqlalchemy.sql.functions import func

from dispatch.config import ENV, KANDBOX_DATETIME_FORMAT_ISO
from dispatch.auth.models import DispatchUser, UserRoles
from dispatch.config import ED_JAVA_URL, ED_JAVA_URL_TIMEOUT, ENV, OSS_ACCESS_KEY_ID, OSS_ACCESS_KEY_SECRET, OSS_ENDPOINT
from dispatch.database_util.service import apply_model_specific_filters
from dispatch.delivery_info import service as delivery_info_service
from dispatch.delivery_info.models import DeliveryInfo
from dispatch.delivery_info import service as delivery_info_service
from dispatch.delivery_package import service as delivery_package_service

from dispatch.delivery_package.models import DeliveryPackage
from dispatch.delivery_package_dimweight import service as delivery_package_dimweight_service
from dispatch.order_event.models import OrderEventCreate, OrderEventRead
from dispatch.plugins.kandbox_planner.util.kandbox_util import check_geo_range
from dispatch.worker import service as worker_service
from .models import (
    Order,
    OrderCreate,
    OrderRead,
    OrderRelatedBase,
    OrderRelatedUpdate,
    OrderUpdate,
    UploadOssFile,
    OrderBase,
    default_job_status,
)
from dispatch.worker.models import WorkerCreate
from dispatch.location import service as location_service
from dispatch.team import service as team_service
from dispatch.job import service as job_service
from dispatch.order_event import service as order_event_service
from uuid import uuid4

from dispatch.auth.models import UserRoles, DispatchUser

# 2022-11-19 00:56:26 Duan: Removed order_job, replaced it by job.order_code
# from dispatch.order import order_job_service_TODEL
# from dispatch.order.order_job_models_TODEL import OrderJobBase

from dispatch.problem import service as problem_service
from dispatch.problem.models import ProblemCreate
from dispatch.team import service as team_service
from dispatch.utils.time_util import TimeUtil
from dispatch.worker import service as worker_service
from dispatch.worker.models import Worker, WorkerCreate, WorkerRead
from dispatch.auth import service as auth_service
from dispatch.config import KANDBOX_DATETIME_FORMAT_ISO_SPACE
from pandas import json_normalize


from dispatch.order.external_api import (
    get_oss_signature,
    update_order_status,
    update_order_location,
    trigger_pc_logout,
    oss_file_upload,
    query_file_url,
    do_redliver,
)
from .models import (
    Order,
    OrderCreate,
    OrderDownloadHistory,
    OrderDownloadHistoryCreate,
    OrderRead,
    OrderRelatedBase,
    OrderRelatedUpdate,
    OrderUpdate,
    UploadOssFile,
)
from sqlalchemy_filters import apply_pagination
from dispatch.plugins.kandbox_planner.env.env_enums import (
    JobPlanningStatus,
)

import logging
log = logging.getLogger(__name__)


def get(*, db_session, code: str) -> Optional[Order]:
    """Returns a plugin based on the given plugin code."""
    return db_session.query(Order).filter(Order.code == code).one_or_none()


def get_by_code(*, db_session, code: str) -> List[Optional[Order]]:
    """Fetches all Order for a given type."""
    return db_session.query(Order).filter(Order.code == code).one_or_none()


def search_by_external_order_code(*, db_session, code: str) -> List[Optional[Any]]:
    """Fetches all Order for a given type."""
    return (
        db_session.query(Order.external_order_code)
        .filter(Order.external_order_code.like(f"%{code}%"))
        .limit(10)
        .all()
    )


def get_all(*, db_session) -> List[Optional[Order]]:
    """Returns all Order."""
    return db_session.query(Order)


def get_by_time(*, db_session, start_time=any, end_time=any) -> List[Optional[Any]]:
    """Returns all jobs."""
    return (
        db_session.query(
            Order,
            DeliveryInfo.check_in_time,
            DeliveryInfo.tpl_region,
            DeliveryInfo.platform_order_number,
            DeliveryInfo.customer_address,
            DeliveryInfo.customer_zipcode,
        )
        .join(DeliveryInfo, Order.code == DeliveryInfo.fk_order_code, isouter=True)
        .filter(DeliveryInfo.check_in_time >= start_time, DeliveryInfo.check_in_time <= end_time)
        .all()
    )


def get_by_org_id_count(*, db_session, org_id: int) -> Optional[int]:
    """Returns an job based on the given code."""
    return db_session.query(func.count(Order.code)).filter(Order.org_id == org_id).scalar()


def get_status_and_time(
    *, db_session, status_list: list, start_time=any, end_time=any
) -> List[Optional[Any]]:
    """Returns all jobs."""
    return (
        db_session.query(
            Order,
            DeliveryInfo.check_in_time,
            DeliveryInfo.tpl_region,
            DeliveryInfo.platform_order_number,
            DeliveryInfo.customer_address,
            DeliveryInfo.customer_zipcode,
        )
        .join(DeliveryInfo, Order.code == DeliveryInfo.fk_order_code, isouter=True)
        .filter(
            DeliveryInfo.check_in_time >= start_time,
            DeliveryInfo.check_in_time <= end_time,
            Order.business_order_status.in_(status_list),
        )
        .all()
    )


def get_by_external_order_code(*, db_session, external_order_code: list) -> List[Optional[Any]]:
    """Returns all jobs."""
    return (
        db_session.query(
            Order,
            DeliveryInfo.check_in_time,
            DeliveryInfo.tpl_region,
            DeliveryInfo.platform_order_number,
            DeliveryInfo.customer_address,
            DeliveryInfo.customer_zipcode,
        )
        .join(DeliveryInfo, Order.code == DeliveryInfo.fk_order_code, isouter=True)
        .filter(Order.external_order_code.in_(external_order_code))
        .all()
    )


def search_filter_order(
        db_session,
        external_order_code: List[str] = None,
        worker: WorkerRead = None,
        business_order_status: List[str] = None,
        tpl_region: List[str] = None) -> List[Optional[Any]]:
    """Returns all order."""
    param = []
    if external_order_code:
        param.append(Order.external_order_code.in_(external_order_code))
    if worker:
        param.append(Order.scheduled_primary_worker_id == worker.id)
    if business_order_status:
        param.append(Order.business_order_status.in_(business_order_status))
    if tpl_region:
        param.append(DeliveryInfo.tpl_region.in_(tpl_region))
    query = db_session.query(Order,
                             DeliveryInfo.check_in_time,
                             DeliveryInfo.tpl_region,
                             DeliveryInfo.platform_order_number,
                             DeliveryInfo.customer_address,
                             DeliveryInfo.customer_zipcode,).outerjoin(
        DeliveryInfo, DeliveryInfo.fk_order_id == Order.id).filter(*param)
    query = query.filter((Order.is_deleted == None) | (Order.is_deleted == 0))
    return query.all()


def range_checker(value, max_value, min_value):

    result = True if value <= max_value or value >= min_value else False
    return result


    
def create(*, db_session, current_user, order_in: OrderCreate) -> OrderRead:
    """Creates a new order."""

    new_order = Order(**order_in.dict(exclude={"job_list", "team","scheduled_primary_worker","target_worker", "overwrite_max_orders_limit"}))
    team_obj = team_service.get_by_code(db_session=db_session, code=order_in.team.code)

    org_id = current_user.org_id
    org_code = current_user.org_code
    new_order.team = team_obj
    db_session.add(new_order)
    db_session.commit()
    
    # log.info(f"create order {new_order} ")

    order_code = new_order.code
    job_list = []
    for job in order_in.job_list:
        job_obj = job_service.get_by_code(db_session=db_session, code=job.code)
        if not job_obj:
            check_geo_flag = check_geo_range(
                geo_longitude = job.geo_longitude,
                geo_latitude = job.geo_latitude,
                team = team_obj
                )
            if not check_geo_flag:
                msg = f"Job(code={job.code}) at {(job.geo_longitude, job.geo_latitude)} is outside_of_allowed_range_of_center {(team_obj.geo_longitude, team_obj.geo_latitude)}"
                log.warning(msg)
                raise HTTPException(status_code=400, detail=msg)
            job.flex_form_data.update(default_job_status)  # 使用 job_status 和 job_track_status 代表的配送配送状态 

            job_dict = {
                "code": job.code,
                "job_type": job.job_type,
                "org_id": org_id,
                "org_code": org_code,
                "name": job.name,
                "planning_status": job.planning_status,
                "description": job.description,
                "team": order_in.team.dict(),
                "location": job.location.dict() if job.location else None,
                "geo_longitude": job.geo_longitude,
                "geo_latitude": job.geo_latitude,
                "flex_form_data": job.flex_form_data,
                "requested_primary_worker": None,
                "requested_start_datetime": job.requested_start_datetime,
                "requested_duration_minutes": job.requested_duration_minutes,
                "scheduled_primary_worker": {"code": job.scheduled_primary_worker.code}
                if job.scheduled_primary_worker
                else None,
                "scheduled_start_datetime": job.scheduled_start_datetime,
                "scheduled_duration_minutes": job.scheduled_duration_minutes,
                "auto_planning": job.auto_planning,
                "requested_skills": job.requested_skills,
                "requested_items": job.requested_items,
                "life_cycle_status": None,
                "current_user": current_user,
                "order_code": new_order.code,
                "tolerance_start_minutes": job.tolerance_start_minutes,
                "tolerance_end_minutes": job.tolerance_end_minutes, 
            }
            job_obj = job_service.create(db_session=db_session, **job_dict)
            
            log.info(f"CREATE JOB job_dict={job_dict}  \t\t\t###, result = {job_obj.__dict__}")
            if job_obj is None:
                log.error(f"Failed to create job {job.code} for order {order_in.code}")
            else:
                job_list.append(job_obj)
        else:
            log.error(
                f"Failed to create job {job.code} for order {order_in.code}. It is already existing."
            )
            # TODO, maybe add order job releation?

    order_event = OrderEventCreate(
        uuid=uuid4(),
        started_at=datetime.datetime.utcnow(),  # datetime.strftime(datetime.datetime.utcnow(), KANDBOX_DATETIME_FORMAT_ISO),
        ended_at=datetime.datetime.utcnow(),
        event_type="creation",
        order_code=order_code,
        linked_job_id=None,
        source=current_user.email,
        description="Initial Creation",
        flex_data={"order_in": str(order_in)},  # .dict()
    )
    order_event_service.add(db_session=db_session, order_event=order_event)
    db_session.commit()
    return new_order, job_list

    order_read = {}
    for column in new_order.__table__.columns:
        order_read[column.name] = getattr(order_read, column.name)  # str()
    order_read["job_list"] = job_list

    return OrderRead(**order_read)

from dispatch.plugins.kandbox_planner.env.env_enums import JobPlanningStatus
def update(*, db_session, order: Order, order_in: OrderUpdate, current_user=None) -> Order:
    """Updates a plugin."""
    _data = jsonable_encoder(order)
    update_data = order_in.dict(
        skip_defaults=True, exclude={"team", "job_list", "reason_code", "business_order_status", "scheduled_primary_worker","target_worker", "overwrite_max_orders_limit"}
    )
    team_obj = team_service.get_by_code(db_session=db_session, code=order_in.team.code)
    
    order.team = team_obj

    new_scheduled_primary_worker = None
    scheduled_primary_worker_changed = False
    if order_in.scheduled_primary_worker:
        log.info(f"Updated order:{order.code} to worker: {order_in.scheduled_primary_worker.code}")
        new_scheduled_primary_worker = worker_service.get_by_code(db_session=db_session, code=order_in.scheduled_primary_worker.code)
        if order.scheduled_primary_worker and order.scheduled_primary_worker.code != order_in.scheduled_primary_worker.code:
            scheduled_primary_worker_changed = True
        if order.scheduled_primary_worker is None:
            scheduled_primary_worker_changed = True
        # set the new worker for the order
        order.scheduled_primary_worker = new_scheduled_primary_worker
    else:
        log.info(f"Updated order:{order.code} to empty")
        order.scheduled_primary_worker = None
        if order.scheduled_primary_worker:
            scheduled_primary_worker_changed = True

    # TODO change reason_code
    # origin_job_list = order_job_service.get_by_order_code(db_session=db_session, code=order.code)
    # origin_job_id_list = [i.fk_job_id for i in origin_job_list]
    # in_job_code_list = [i.code for i in order_in.job_list]
    channged_job_id_list = []
    for job in order_in.job_list:
        job_obj = job_service.get_by_code(db_session=db_session, code=job.code)
        if not job_obj:
            log.error(f"not find job:{job.code} for order: {order_in.code}, skipped and continued.")
            continue
        check_geo_flag = check_geo_range(
            geo_longitude = job.geo_longitude,
            geo_latitude = job.geo_latitude,
            team = team_obj
        )
        if not check_geo_flag:
            msg = f"Job(code={job_obj.code})  geo_longitude, geo_latitude: {(job.geo_longitude, job.geo_latitude)} outside of min_max_range"
            log.error(msg)
            raise HTTPException(status_code=400, detail=msg)

        if scheduled_primary_worker_changed and (job_obj.planning_status not in (JobPlanningStatus.CANCELLED, JobPlanningStatus.FINISHED)):
            job_obj.scheduled_primary_worker = new_scheduled_primary_worker
            if new_scheduled_primary_worker is not None:
                job_obj.planning_status == JobPlanningStatus.IN_PLANNING
                channged_job_id_list.append(job_obj.code)
            else:
                job_obj.planning_status = JobPlanningStatus.UNPLANNED
                # ignore job biz change if unplanned. channged_job_id_list
                
        if job.geo_latitude:
            job_obj.geo_latitude = float(job.geo_latitude)
        if job.geo_longitude:
            job_obj.geo_longitude = float(job.geo_longitude)

        db_session.add(job_obj)

        # add order job releation
        # if job_obj.code not in origin_job_id_list:
        if job_obj.code:

            # order_job_obj = OrderJobBase(
            #     fk_order_code=order.code,
            #     order_code=order.code,
            #     fk_job_id=job_obj.code,
            #     job_code=job_obj.code,
            #     env=ENV,
            #     is_deleted=0,
            # )

            # order_job_service.create(db_session=db_session, order_in=order_job_obj)

            # add order event
            order_event = OrderEventCreate(
                uuid=uuid4(),
                started_at=datetime.datetime.utcnow(),
                ended_at=datetime.datetime.utcnow(),
                event_type="",
                order_code=order.code,
                linked_job_id=job_obj.code,
                source="",
                description="Update",
                flex_data={},
            )
            order_event_service.add(db_session=db_session, order_event=order_event)

    if len(channged_job_id_list) > 0:
        if not current_user:
            raise HTTPException(status_code=400, detail="Not authenticated for updating")
        user = auth_service.get_by_email(db_session=db_session, email=current_user.email)
        # commit & release locks before calling java api.
        db_session.commit()
        worker_data = new_scheduled_primary_worker  # worker_service.get(db_session=db_session,worker_id=new_scheduled_primary_worker.code)
        try:
            data = job_service.job_batch_change_worker(
                worker_id=str(worker_data.code),
                dispatch_user_id=worker_data.dispatch_user.code,
                worker_code=worker_data.code,
                job_id_list=channged_job_id_list,
                user_id=user.code,
                token=user.token)
            log.info(f"finished job_batch_change_worker {data}")
        except Exception as e:
            log.error(f"error during job_batch_change_worker for updating {channged_job_id_list}")
            # raise HTTPException(status_code=400, detail=str(e))

    # origin_job_list = job_service.get_all_by_order_code(db_session=db_session,order_code = order.code)
    # origin_job_code_list = [i.code for i in origin_job_list]
    # in_job_code_list = [i.code for i in order_in.job_list]
    # for job in order_in.job_list:
    #     job_obj = job_service.get_by_code(db_session=db_session,code = job.code)
    #     if not job_obj:
    #         log.error(f"not find job:{job.code} continue")
    #         continue
    #     if job_obj.order_code == order.code:
    #         continue
    #     log.warning(f"You should not modify job {job_obj.code}  to another order {order.code}: skipped")

    for field in _data:
        if field in update_data:
            setattr(order, field, update_data[field])

    db_session.add(order)
    db_session.commit()
    return order


def set_order_scheduled_primary_worker(*, db_session, order_code: str, worker_id: int, linked_job_id: int = None, source=None):

    order = get(db_session=db_session, code=order_code)
    if not order:
        log.error(f"The order with this code {order_code} does not exist.")
        return
    order.scheduled_primary_worker_code = worker_id
    db_session.add(order)

    # add order event
    order_event = OrderEventCreate(
        uuid=uuid4(),
        started_at=datetime.datetime.utcnow(),
        ended_at=datetime.datetime.utcnow(),
        event_type="",
        order_code=order.code,
        linked_job_id=linked_job_id,
        source=source,
        description="Updated worker code (linked job change )",
        flex_data={},
    )
    order_event_service.add(db_session=db_session, order_event=order_event)

    if linked_job_id is not None:
        linked_job = job_service.get(db_session=db_session, job_id=linked_job_id)
        if linked_job.planning_status == 'F':
            log.error(f"job code {linked_job_id} code {linked_job.code} is in F status and can not be changed.")
        else:
            linked_job.scheduled_primary_worker_code = worker_id
            if linked_job.planning_status == 'U':
                linked_job.planning_status = "I"
            db_session.add(linked_job)
    db_session.commit()


def delete(*, db_session, code: str ):
    """Deletes a plugin."""
    # db_session.query(Order).filter(Order.code == code).delete()
    # db_session.commit()
    order = get(db_session=db_session, code=code)
    order.is_deleted = 1
    db_session.add(order)
    db_session.commit()
    return order



def get_order(*, db_session, order_code: str) -> OrderRead:

    order = get_by_code(db_session=db_session, code=order_code)
    job_list = job_service.get_all_by_order_code(db_session=db_session, order_code=order_code)

    events = []
    order_read = OrderRead(
        job_list=job_list,
        team={"code": order.team_id},
        events=events,
        **order.__dict__)

    return order_read


def get_order_info(*, db_session, code: str) -> OrderRead:

    order = get(db_session=db_session, code=code)
    if order is None:
        return None
    team = team_service.get(db_session=db_session, team_id=order.team_id)

    job_list = job_service.get_all_by_order_code(db_session=db_session, order_code=code)

    events = []
    all_events = order_event_service.get_by_order_code(db_session=db_session, order_code=code)
    for event in all_events:
        _event = OrderEventRead(**event.__dict__)
        events.append(_event)
    order_read = OrderRead(job_list=job_list, team=team, events=events, **order.__dict__)

    return order_read


# def get_scheduled_primary_worker_code(*, db_session, code: int):
#     order_job_list = job_service.get_all_by_order_code(db_session=db_session, order_code=code)
#     data = ""
#     if order_job_list:
#         for job_obj in order_job_list:
#             if job_obj and job_obj.scheduled_primary_worker:
#                 data = job_obj.scheduled_primary_worker.code
#                 break

#     return data


def get_order_related_data(
    *, db_session, order_data: Order, code: int, user_id: int, token: str
) -> OrderRelatedBase:

    relation_data = {
        "order_code": code,
        "package_type": None,
        "customer_address": None,
        "customer_zipcode": None,
        "customer_name:": None,
        "customer_phone_pumber": None,
        "scheduled_start_datetime": None,
        "scheduled_primary_worker": None,
        "package_code": None,
        "length": None,
        "width": None,
        "height": None,
        "volume": None,
        "weight": None,
        "location": None,
        "job_reschedule_times": None,
        "image_url_list": [],
        "file_code_list": [],
        "problem_notes": None,
        "tpl_region": None,
        "delivery_price": []
    }

    delivery_package_data = delivery_package_service.get_by_order_code(db_session=db_session, code=code)
    delivery_info_data = delivery_info_service.get_by_order_code(db_session=db_session, code=code)
    delivery_package_dimweight_data = delivery_package_dimweight_service.get_by_order_code(
        db_session=db_session, code=code
    )
    relation_data["scheduled_primary_worker"] = order_data.scheduled_primary_worker

    relation_data["package_type"] = (
        delivery_package_data.package_type if delivery_package_data else None
    )
    relation_data["customer_address"] = (
        delivery_info_data.customer_address if delivery_info_data else None
    )
    relation_data["customer_zipcode"] = (
        delivery_info_data.customer_zipcode if delivery_info_data else None
    )
    relation_data["customer_name"] = (
        delivery_info_data.customer_name if delivery_info_data else None
    )
    relation_data["customer_phone_pumber"] = (
        delivery_info_data.customer_telno if delivery_info_data else None
    )
    relation_data["tpl_region"] = delivery_info_data.tpl_region if delivery_info_data else None
    relation_data["package_code"] = (
        delivery_package_data.package_code if delivery_package_data else None
    )
    if delivery_package_dimweight_data.length_tpl:
        relation_data["length"] = (
            delivery_package_dimweight_data.length_tpl if delivery_package_dimweight_data else None
        )
        relation_data["width"] = (
            delivery_package_dimweight_data.width_tpl if delivery_package_dimweight_data else None
        )
        relation_data["height"] = (
            delivery_package_dimweight_data.height_tpl if delivery_package_dimweight_data else None
        )
        relation_data["volume"] = (
            delivery_package_dimweight_data.volume_tpl if delivery_package_dimweight_data else None
        )
        relation_data["weight"] = (
            delivery_package_dimweight_data.weight_tpl if delivery_package_dimweight_data else None
        )
    else:
        relation_data["length"] = (
            delivery_package_dimweight_data.length_platform
            if delivery_package_dimweight_data
            else None
        )
        relation_data["width"] = (
            delivery_package_dimweight_data.width_platform
            if delivery_package_dimweight_data
            else None
        )
        relation_data["height"] = (
            delivery_package_dimweight_data.height_platform
            if delivery_package_dimweight_data
            else None
        )
        relation_data["volume"] = (
            delivery_package_dimweight_data.volume_platform
            if delivery_package_dimweight_data
            else None
        )
        relation_data["weight"] = (
            delivery_package_dimweight_data.weight_platform
            if delivery_package_dimweight_data
            else None
        )

    if delivery_info_data.customer_zipcode:
        location = location_service.get(
            db_session=db_session, code=delivery_info_data.customer_zipcode
        )
        relation_data["location"] = location
    problem = problem_service.get_order_exception_problem(
        db_session=db_session, code=code, source_code="Order"
    )
    if problem:
        relation_data["problem_notes"] = problem.notes
        file_code_list = problem.images.split(";") if problem.images else []
        file_code_list = [i for i in file_code_list if i]
        relation_data["images_dict"] = query_file_url(file_code_list, user_id=user_id, token=token)
    # todo 将all()转化为python类型 dict(zip())
    delivery_data = get_by_order_code(db_session=db_session, code=code)
    relation_json = []
    for item in delivery_data:
        data = {}
        data['delivery_name'] = item.name
        data['item_quantity'] = item.item_quantity
        data['unit_price'] = item.unit_price
        data['paid_price'] = item.paid_price
        data['sku'] = item.sku
        relation_json.append(data)
    relation_data['delivery_price'] = relation_json
    return OrderRelatedBase(**relation_data)


def set_order_related(
    *, db_session, order: Order, order_related_in: OrderRelatedUpdate, user_id: int, token: str
):
    """
    update order detail
    """
    flag = True
    msg = ""
    try:
        if not order:
            return {
                "msg": f"Error set_order_related,order_code {order_related_in.order_code} ",
                "flag": False,
            }

        # 修改 体积重量等
        try:
            package_dim = delivery_package_dimweight_service.get_by_order_code(
                db_session=db_session, code=order.code
            )
            if package_dim and order_related_in.length:
                if package_dim.length_tpl:
                    package_dim.length_tpl = order_related_in.length
                    package_dim.width_tpl = order_related_in.width
                    package_dim.height_tpl = order_related_in.height
                    package_dim.volume_tpl = order_related_in.volume
                    package_dim.weight_tpl = order_related_in.weight
                else:
                    package_dim.length_platform = order_related_in.length
                    package_dim.width_platform = order_related_in.width
                    package_dim.height_platform = order_related_in.height
                    package_dim.volume_platform = order_related_in.volume
                    package_dim.weight_platform = order_related_in.weight

                db_session.add(package_dim)
                db_session.commit()
        except Exception as e:
            flag = False
            msg = msg + f"error update package_dim  ,order_code{order_related_in.order_code} "

        try:
            problem = problem_service.get_order_exception_problem(
                db_session=db_session, code=order.code, source_code="Order"
            )
            new_images = []
            if problem:
                origin_img = problem.images.split(";")
                all_images = list(set(order_related_in.file_code_in + origin_img))
                new_images = [
                    i for i in all_images if i not in order_related_in.delete_file_code_list and i
                ]

                problem.problem_type = "Order Exception"
                problem.notes = order_related_in.problem_notes
                problem.images = ";".join(new_images) if new_images else ""
                db_session.add(problem)
                db_session.commit()
            else:
                all_images = list(set(order_related_in.file_code_in))
                new_images = [
                    i for i in all_images if i not in order_related_in.delete_file_code_list and i
                ]

                if all_images or order_related_in.problem_notes:
                    problem_in = ProblemCreate(
                        problem_type="Order Exception",
                        operator_type=None,
                        reason_code=None,
                        notes=order_related_in.problem_notes,
                        fk_order_code=order.code,
                        job_code=-1,
                        fk_job_biz_id=-1,
                        geocoding_latitude=None,
                        geocoding_longitude=None,
                        images=";".join(new_images) if new_images else "",
                        source_code="Order",
                        env=ENV,
                        is_deleted=0,
                    )
                    problem = problem_service.create(db_session=db_session, problem_in=problem_in)

        except Exception as e:
            flag = False
            msg = (
                msg
                + f"error update order_exception_problem  ,order_code{order_related_in.order_code} "
            )

        try:
            add_image = list(set(order_related_in.file_code_in))
            images = ";".join(add_image) if add_image else ""
            order_updated_changed_flag, api_notify_flag = check_order_status_change(
                order, order_related_in
            )
            if api_notify_flag:
                update_order_data = update_order_status(
                    orderCode=order_related_in.order_code,
                    targetStatus=order_related_in.business_order_status,
                    reasonCode=order_related_in.reason_code,
                    fileCode=images,
                    token=token,
                    user_id=user_id,
                )
                if not update_order_data['flag']:
                    flag = False
                    # msg = (
                    #     msg
                    #     + f"error update_order_status  ,order_code{order_related_in.order_code} ,business_order_status:{order_related_in.business_order_status}, reasonCode: {order_related_in.reason_code} "
                    # )
                    msg = update_order_data['msg']
                else:
                    log.info(
                        f"update_order_status successful for order {order_related_in.order_code} "
                    )
            else:
                log.info(
                    f"order related is updated successfully, but not called update_order_status api for order {order_related_in.order_code} "
                )

        except Exception as e:
            msg = (
                msg
                + f"error update_order_status with exception,order_code{order_related_in.order_code} ,business_order_status:{order_related_in.business_order_status}, reasonCode: {order_related_in.reason_code} "
            )
            flag = False
            log.error(f"update_order_status error: {str(e)}")
            log.error(f"{msg}")

        # 修改电话

        try:
            delivery_info_changed_flag = False
            delivery_info_data = delivery_info_service.get_by_order_code(
                db_session=db_session, code=order.code
            )

            # delivery_info_data = delivery_info_service.get_by_order_code(db_session=db_session,code=order.code)
            if delivery_info_data and order_related_in.customer_phone_pumber:
                delivery_info_data.customer_telno = order_related_in.customer_phone_pumber
                delivery_info_changed_flag = True

            """
            检查location 是否有更改    
            """
            location = location_service.get(
                db_session=db_session, code=delivery_info_data.customer_zipcode
            )
            if not location:
                flag = False
                msg = msg + f"Unknow Location ,order_code{order_related_in.order_code}"

            location_change_flag = False
            if order_related_in.customerAddress != delivery_info_data.customer_address:
                location_change_flag = True
            else:
                if location.code != order_related_in.locationId:
                    location_change_flag = True

            if delivery_info_changed_flag or location_change_flag:
                try:
                    delivery_info_data.tpl_region = order_related_in.tpl_region
                    # delivery_info_changed_flag = True
                    db_session.add(delivery_info_data)
                    db_session.commit()
                except Exception as e:
                    flag = False
                    msg = (
                        msg
                        + f"error update customer_phone_pumber  ,order_code{order_related_in.order_code}, {str(e)} "
                    )

            # location_update_flag = check_(db_session,delivery_info_data,order_related_in)
            if location_change_flag:

                if not order_related_in.locationId or not order_related_in.customerAddress:
                    flag = False
                    msg = (
                        msg
                        + f"error update_order_location_data  ,order_code{order_related_in.order_code}  location code or  location address is required "
                    )

                update_order_location_data = update_order_location(
                    orderCode=order_related_in.order_code,
                    locationId=order_related_in.locationId,
                    customerAddress=order_related_in.customerAddress,
                    token=token,
                    user_id=user_id,
                )
                if not update_order_location_data:
                    flag = False
                    msg = (
                        msg
                        + f"error update_order_location_data  ,order_code{order_related_in.order_code} ,locationId:{order_related_in.locationId}, customerAddress: {order_related_in.customerAddress} "
                    )

        except Exception as e:
            flag = False
            msg = (
                msg
                + f"error in update_order_location API ,order_code{order_related_in.order_code} ,locationId:{order_related_in.locationId}, customerAddress: {order_related_in.customerAddress} "
            )
            log.error(f"update_order_location error:")
            log.error(f"{msg}")

    except Exception as e:
        flag = False
        log.error(
            f"EdJavaError: Failed to  set_order_related: set_order_related ,order_code {order_related_in.order_code}, {e}"
        )

    return {
        "msg": "succeed" if flag else msg,
        "flag": flag,
    }


def check_order_status_change(order, order_related_in):
    """
    校验是否状态更改
    """
    # 2022-11-28 23:45:24, to fix status update at:
    # allowed_status_calling = {
    #     "package_on_hold",
    #     "package_lost",
    #     "package_damaged",
    #     "package_scrapped",
    #     "on_the_way_to_shipper",
    #     "package_returned",
    # }

    final_status_list = {
        "delivered",
        # "package_on_hold",
        "package_lost",
        "package_damaged",
        "package_scrapped",
        # "on_the_way_to_shipper",
        "package_returned",
    }

    changed_flag = False
    api_notify_flag = False

    if (order.business_order_status in final_status_list) and (
        order.business_order_status != order_related_in.business_order_status
    ):
        raise HTTPException(
            status_code=400, detail="The order status at {order.business_order_status} can not be changed, since it is a final status...")

    if (
        order.business_order_status
        != order_related_in.business_order_status
        # or order.reason_code != order_related_in.reason_code
    ):
        if order_related_in.business_order_status == "package_returned":
            if not order_related_in.file_code_in:
                raise HTTPException(status_code=400, detail="Images must be provided if status is changed to 'package_returned'.")

        changed_flag = True
        api_notify_flag = True

    return changed_flag, api_notify_flag


def get_delivery_tpl_region(db_session, order_code: str):
    delivery_info_data = delivery_info_service.get_by_order_code(db_session=db_session, code=order_code)
    tpl_region = delivery_info_data.tpl_region if delivery_info_data else None
    return tpl_region


def search_filter_sort_paginate_order(
    db_session,
    external_order_code: List[str] = None,
    worker: WorkerRead = None,
    business_order_status: List[str] = None,
    tpl_region: List[str] = None,
    page: int = 1,
    items_per_page: int = 5,
    sort_by: List[str] = None,
    descending: List[bool] = None,
    current_user: DispatchUser = None,
    role: UserRoles = UserRoles.CUSTOMER,
):
    if items_per_page < 0 or items_per_page > 100:
        raise HTTPException(status_code=400, detail=f"items per page value ({items_per_page}) is too large ...")

    try:
        param = []
        if external_order_code:
            param.append(Order.external_order_code.in_(external_order_code))
        if worker:
            param.append(Order.scheduled_primary_worker_code == worker.code)
        if business_order_status:
            param.append(Order.business_order_status.in_(business_order_status))
        # if tpl_region:
        #     param.append(DeliveryInfo.tpl_region.in_(tpl_region))

        query = db_session.query(Order).filter(*param)
        # wemart 没有  用过这个DeliveryInfo表 
        # query = db_session.query(Order, DeliveryInfo.tpl_region).outerjoin(
        #     DeliveryInfo, DeliveryInfo.fk_order_code == Order.code
        # ).filter(*param)
        # if sort_by:
        #     query = query.order_by(Order.code.desc() if descending[0] else Order.code)
        query = query.filter((Order.is_deleted == None) | (Order.is_deleted == 0))
        query = apply_model_specific_filters(Order, query, current_user, role)
        total = query.with_entities(sqlalchemy.func.count(Order.code)).scalar()
        query = query.limit(items_per_page).offset((page - 1) * items_per_page)
    except sqlalchemy.exc.ProgrammingError as e:
        log.debug(e)
        return {
            "items": [],
            "itemsPerPage": items_per_page,
            "page": page,
            "total": 0,
        }
        
    result_sql  = str(query.statement)
    # log.info(f"search_filter_sort_paginate_order {result_sql}")
    return {
        "items": query.all(),
        "itemsPerPage": items_per_page,
        "page": page,
        "total": total,
    }


def find_external_order_code(*, db_session, external_order_code: list) -> List[Optional[Any]]:
    """Returns all jobs."""
    data = (
        db_session.query(Order.external_order_code)
        .filter(Order.external_order_code.in_(external_order_code))
        .all()
    )
    return [i[0] for i in data]


def order_download_history_create(db_session, order_in: OrderDownloadHistoryCreate):
    """Creates a new order download history."""
    history_data = OrderDownloadHistory(**order_in.dict())
    db_session.add(history_data)
    db_session.flush()
    db_session.refresh(history_data)
    db_session.commit()
    return history_data.id


def order_download_history_update(db_session, download_history_id: int, download_status: str, download_url: str):
    """Updata a new order download history status."""
    query = db_session.query(OrderDownloadHistory).filter(OrderDownloadHistory.id == download_history_id)
    now = datetime.datetime.now()
    created_date = datetime.datetime.strftime(now, "%Y-%m-%d %H:%M:%S")
    expiry_date = datetime.datetime.strftime(now + datetime.timedelta(days=1), "%Y-%m-%d %H:%M:%S")
    query.update({
        OrderDownloadHistory.status: download_status,
        OrderDownloadHistory.file_location: download_url,
        OrderDownloadHistory.created_date: created_date,
        OrderDownloadHistory.expiry_date: expiry_date,
    })
    db_session.commit()


def order_download_history_query(db_session):
    """Query all order download history."""
    query = db_session.query(
        (sqlalchemy.func.to_char(OrderDownloadHistory.start_time, 'YYYY-MM-DD HH24:MI:SS')).label("start_time"),
        (sqlalchemy.func.to_char(OrderDownloadHistory.end_time, 'YYYY-MM-DD HH24:MI:SS')).label("end_time"),
        OrderDownloadHistory.status,
        OrderDownloadHistory.file_location,
        (sqlalchemy.func.to_char(OrderDownloadHistory.created_date, 'YYYY-MM-DD HH24:MI:SS')).label("created_date"),
        (sqlalchemy.func.to_char(OrderDownloadHistory.expiry_date, 'YYYY-MM-DD HH24:MI:SS')).label("expiry_date"),
    ).order_by(OrderDownloadHistory.created_at.desc())
    history_data = query.all()
    data_list = []
    now_time = datetime.datetime.now()
    for i in history_data:
        data = dict(zip(i.keys(), i))
        second_time = datetime.datetime.strptime(data['created_date'], "%Y-%m-%d %H:%M:%S")
        data['disabled'] = (now_time - second_time).total_seconds() > 60 * 60 * 24 or data['status'] != 'created'
        data_list.append(data)
    return data_list


def put_download_data(db_session, order_status: List[str], order_in: OrderDownloadHistoryCreate, download_history_id: int):
    """put download file."""
    # if 'all' in order_status:
    #     all_data = get_by_time(db_session=db_session,start_time=order_in.start_time,end_time=order_in.end_time)
    # else:
    #     all_data = get_status_and_time(db_session=db_session,status_list=order_in.status,start_time=order_in.start_time,end_time=order_in.end_time)
    # df = order_to_df(db_session,all_data,[])
    download_data = get_download_data(db_session=db_session, order_status=order_status, start_time=order_in.start_time, end_time=order_in.end_time)
    data_list = []
    for i in download_data:
        data = dict(zip(i.keys(), i))
        data_list.append(data)
    data_frame = json_normalize(data_list)
    with tempfile.TemporaryDirectory() as tmpdirname:
        current_time = datetime.datetime.now().strftime('%Y-%m-%d-%H-%M-%S')
        file_name = f"{current_time}-{uuid.uuid4().hex}.csv"
        file_path = f"{tmpdirname}/{file_name}"
        data_frame.to_csv(file_path, encoding='utf-8', index=False, date_format="%Y-%m-%d %H:%M:%S")
        from dispatch.utils.oss_tools import OssTools
        oss = OssTools()
        oss_result = oss.oss_put_file(file_path, file_name)
        order_in.status = "created" if oss_result else "failed"
    download_url = oss.oss_download_url(file_name)
    order_download_history_update(db_session, download_history_id, order_in.status, download_url)


def get_download_data(*, db_session, order_status: list, start_time=any, end_time=any) -> List[Optional[Any]]:
    """Returns all jobs. """
    param = []
    if 'all' not in order_status and order_status:
        param.append(Order.business_order_status.in_(order_status))
    last_subquery = db_session.query(
        JobBiz.fk_order_id.label("fk_order_id"),
        JobBiz.end_time.label("last_job_end_time"),
        (sqlalchemy.func.substr(JobBiz.job_code, 3)).label("seq"),
        JobBiz.worker.label("w_code"),
        JobBiz.job_track_status.label("last_job_status"),
        JobBiz.job_type.label("last_job_type"),
    ).filter(
        JobBiz.job_type == "dropOff",
        JobBiz.is_deleted == 0
    ).distinct("fk_order_id"
               ).order_by(JobBiz.fk_order_id.desc(), (sqlalchemy.func.substr(JobBiz.job_code, 3)).desc()).subquery()

    first_subquery = db_session.query(
        JobBiz.fk_order_id.label("fk_order_id"),
        JobBiz.end_time.label("first_job_end_time"),
        (sqlalchemy.func.substr(JobBiz.job_code, 3)).label("seq"),
        JobBiz.worker.label("w_code")
    ).filter(
        JobBiz.job_type == "dropOff",
        JobBiz.is_deleted == 0
    ).distinct("fk_order_id"
               ).order_by(JobBiz.fk_order_id, sqlalchemy.func.substr(JobBiz.job_code, 3)).subquery()

    query = db_session.query(
        (sqlalchemy.func.to_char(DeliveryInfo.check_in_time, 'YYYY-MM-DD')).label("in_bound_day"),
        DeliveryInfo.check_in_time.label("in_bound_time"),
        last_subquery.c.last_job_end_time.label("last_job_datetime"),
        last_subquery.c.last_job_status,
        last_subquery.c.last_job_type,
        Order.external_order_code.label("tracking_number"),
        DeliveryPackage.package_code,
        Order.code,
        Order.business_order_status,
        Order.updated_at.label("order_updated_at"),
        first_subquery.c.first_job_end_time.label("first_attempt_end_time"),
        (DeliveryPackageDimweight.volume_platform / 5000).label("lazada_volume_5000_kg"),
        (DeliveryPackageDimweight.weight_platform / 1000).label("lazada_weight_kg"),
        (DeliveryPackageDimweight.volume_tpl / 5000).label("sc_volume_5000"),
        (DeliveryPackageDimweight.weight_tpl / 1000).label("sc_weight"),
        DeliveryInfo.tpl_region.label("Sort_Code"),
        DeliveryInfo.platform_order_number,
        DeliveryInfo.customer_address,
        DeliveryInfo.customer_zipcode,
        last_subquery.c.w_code.label("worker_code"),
        Order.id.label("order_id"),
        Order.created_at.label("order_create_time"),
    ).outerjoin(
        DeliveryInfo, Order.id == DeliveryInfo.fk_order_id
    ).outerjoin(
        DeliveryPackage, Order.id == DeliveryPackage.fk_order_id
    ).outerjoin(
        DeliveryPackageDimweight, Order.id == DeliveryPackageDimweight.fk_order_id
    ).outerjoin(last_subquery, Order.id == last_subquery.c.fk_order_id
                ).outerjoin(first_subquery, Order.id == first_subquery.c.fk_order_id
                            ).filter(
        DeliveryInfo.check_in_time >= start_time,
        DeliveryInfo.check_in_time <= end_time,
        *param
    ).order_by(Order.id)
    return query.all()


def num_out(data):
    data = str(data) + '\t'
    return data


def order_to_df(db_session, all_order, not_find_code):
    result_json_data = []
    for order_obj_list in all_order:
        order_obj = order_obj_list[0]
        check_in_time = order_obj_list[1]
        tpl_region = order_obj_list[2]
        platform_order_number = order_obj_list[3]
        customer_address = order_obj_list[4]
        customer_zipcode = order_obj_list[5]
        delivery_package = delivery_package_service.get_by_order_id(db_session=db_session, id=order_obj.id)
        delivery_package_dimweight = delivery_package_dimweight_service.get_by_order_id(db_session=db_session, id=order_obj.id)

        worker_code = order_obj_list.Order.scheduled_primary_worker.code if order_obj_list.Order.scheduled_primary_worker else ''
        worker_name = order_obj_list.Order.scheduled_primary_worker.name if order_obj_list.Order.scheduled_primary_worker else ''
        order_job_list = order_job_service.get_by_order_id(db_session=db_session, id=order_obj.id)
        team_code = ''
        for order_job in order_job_list:
            job_obj = job_service.get(db_session=db_session, job_id=order_job.fk_job_id)
            if job_obj:
                team_code = job_obj.team.code
        delivered_Time = ""
        if order_obj.business_order_status in ['delivered', 'package_returned']:
            delivered_Time = order_obj.updated_at.strftime(KANDBOX_DATETIME_FORMAT_ISO_SPACE) if order_obj.updated_at else None

        result_json_data.append({
            'Package Tracking No': order_obj.external_order_code,
            "Package ID": delivery_package.package_code if delivery_package else None,
            "Order Number": platform_order_number,
            "Order Status": order_obj.business_order_status,
            "Inbound_Time": check_in_time.strftime(KANDBOX_DATETIME_FORMAT_ISO_SPACE) if check_in_time else None,
            "Delivered Time": delivered_Time,
            "LAZADA Volume/5000 (KG)": float(delivery_package_dimweight.volume_platform / 5000) if delivery_package_dimweight.volume_platform else 0,
            "LAZADA Weight (KG)": float(delivery_package_dimweight.weight_platform / 1000) if delivery_package_dimweight.weight_platform else 0,
            "SC Volume/5000": float(delivery_package_dimweight.volume_tpl / 5000) if delivery_package_dimweight.volume_tpl else 0,
            "SC Wieght": float(delivery_package_dimweight.weight_tpl / 1000) if delivery_package_dimweight.weight_tpl else 0,
            "Driver ID": worker_code,
            "Driver Name": worker_name,
            "Deliver Group Name": team_code,
            "Sort_Code": tpl_region,
            "Post code": customer_zipcode,
            "Buyer Address": customer_address
        })

    for code in not_find_code:
        result_json_data.append({
            'Package Tracking No': code,
            "Package ID": None,
            "Order Number": None,
            "Order Status": None,
            "Inbound_Time": None,
            "Delivered_Time": None,
            "LAZADA Volume/5000 (KG)": None,
            "LAZADA Weight (KG)": None,
            "SC Volume/5000": None,
            "SC Wieght": None,
            "Driver ID": None,
            "Driver Name": None,
            "Deliver Group Name": None,
            "Sort_Code": None,
            "Post code": None,
            "Buyer Address": None
        })

    if not result_json_data:
        result_json_data.append({
            'Package Tracking No': None,
            "Package ID": None,
            "Order Number": None,
            "Order Status": None,
            "Inbound_Time": None,
            "Delivered_Time": None,
            "LAZADA Volume/5000 (KG)": None,
            "LAZADA Weight (KG)": None,
            "SC Volume/5000": None,
            "SC Wieght": None,
            "Driver ID": None,
            "Driver Name": None,
            "Deliver Group Name": None,
            "Sort_Code": None,
            "Post code": None,
            "Buyer Address": None
        })
    df = json_normalize(result_json_data)

    df['Package Tracking No'] = df['Package Tracking No'].astype(str)
    df['Package ID'] = df['Package ID'].astype(str)
    df['Order Number'] = df['Order Number'].map(num_out)

    return df

def is_pick_up_stage(stage):
    if stage in ["inbound_success","arrived"]:
        return True
    return False

def app_get_flex_form_data(job, filedname,default_value=None):
    # if "shipperAddress" in job["flex_form_data"] and job["flex_form_data"]["shipperAddress"]:
    #     job["shipperAddress"] = job["flex_form_data"]["shipperAddress"]

    if filedname in job["flex_form_data"] and job["flex_form_data"][filedname]:
        return job["flex_form_data"][filedname]
    else:
        return  default_value 

def get_job_info(*, db_session, code: str):
    job = job_service.get(db_session=db_session, code=code)
    return job
