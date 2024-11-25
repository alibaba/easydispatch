import copy
import datetime
import json
import os
import tempfile
import random
import time
import threading
from fastapi import APIRouter, Body, Depends, HTTPException, Query, UploadFile, File
from pandas import json_normalize
from psycopg2 import IntegrityError
from sqlalchemy.orm import Session
from dispatch.auth.models import DispatchUser, UserRoles
from dispatch.auth.service import get_current_role, get_current_user, get_by_email
from dispatch.common.utils.string_checker import check_order_code_str, check_job_code_str
from dispatch.config import KANDBOX_DATETIME_FORMAT_ISO_SPACE, MAX_NBR_ORDERS_PER_CALL
from typing import List
from dispatch.delivery_info.models import DeliveryInfo
from dispatch.exceptions import InvalidConfiguration
from dispatch.database import get_db
from dispatch.database_util.service import common_parameters, search_filter_sort_paginate
from dispatch.plugins.kandbox_planner.env.env_enums import ActionScoringResultType, ActionType, JobPlanningStatus, OrderCreateResultStatusType
from dispatch.plugins.kandbox_planner.env.env_models import NoAvailableSlots, OrderCreationResult
from dispatch.team.models import Team
from dispatch.delivery_package import service as delivery_package_service
from dispatch.delivery_package_dimweight import service as delivery_package_dimweight_service
from dispatch.job import service as job_service
from dispatch.cloudmarket.job_event import  service as job_event_service
from dispatch.order_event import service as order_event_service


from .models import (
    BatchSearchOrder,
    DownloadOrder,
    OrderCreate,
    OrderPagination,
    OrderRead,
    OrderRelatedBase,
    OrderRelatedUpdate,
    OrderSelect,
    OrderUpdate,
    ImagesOss,
    RedliverRequest,
    RedliverResponse,
    UploadOssFile,
)
from dispatch.planner_env.planner_service import get_active_planner, replan_order
from fastapi.responses import JSONResponse

from .service import (
    do_redliver,
    find_external_order_code,
    get,
    get_by_external_order_code,
    get_by_time,
    get_order_info,
    get_order_related_data,
    get_status_and_time,
    search_by_external_order_code,
    search_filter_sort_paginate_order,
    set_order_related,
    update,
    delete,
    create,
    get_by_code,
    get_oss_signature,
    oss_file_upload,
    is_pick_up_stage,
)  # ,get_delivery_tpl_region
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from datetime import  timedelta

from dispatch.config import OSS_ENDPOINT

import logging
log = logging.getLogger(__name__)

router = APIRouter()


@router.get("/", response_model=OrderPagination)
def get_orders(*, common: dict = Depends(common_parameters)):
    """
    """
    if common["items_per_page"] < 0 or common["items_per_page"] > MAX_NBR_ORDERS_PER_CALL:
        raise HTTPException(status_code=400, detail=f"items per page value is too large, values must be (1 - {MAX_NBR_ORDERS_PER_CALL}) ...")

    orders_data = search_filter_sort_paginate(model="Order", **common)
    # for item in orders_data['items']:
    #     # item.scheduled_primary_worker = get_scheduled_primary_worker_code(db_session=common['db_session'], code=item.code)
    #     item.tpl_region = get_delivery_tpl_region(db_session=common['db_session'], order_code=item.code)
    return orders_data

    # return search_filter_sort_paginate(model="Order", **common)


@router.get("/search/external_order_code/{q}", response_model=OrderSelect)
def search_external_order_code(*, db_session: Session = Depends(get_db), q: str):

    data = search_by_external_order_code(db_session=db_session, code=q)
    return OrderSelect(items=[i.external_order_code for i in data])


@router.get("/{order_code}", response_model=OrderRead)
def get_order(*, db_session: Session = Depends(get_db), order_code: str):
    """
    Get an order.
    """
    order = get_order_info(db_session=db_session, code=order_code)
    if not order:
        raise HTTPException(status_code=404, detail="The order with this code does not exist.")
    return order

@router.post("/", response_model=OrderCreationResult)
def create_order(
    *,
    db_session: Session = Depends(get_db),
    order_in: OrderCreate = Body(
        ...,
        example={"code": "myOrder"},
    ),
    current_user: DispatchUser = Depends(get_current_user),
):
    """
    Create a new order.
    """
    log.info(f"create_order:received: {order_in.json()}")
    if not check_order_code_str(order_in.code):
        raise HTTPException(status_code=400, detail=f"Order code {order_in.code} is invalid")
    for job_in in order_in.job_list:
        if job_in.job_type == "pick":
            if job_in.code.split('-')[-1] != 'p':
                log.info(f"Job code {job_in.code} has a wrong name, pick job must end with -p.")
                raise HTTPException(status_code=400, detail=f"Job code {job_in.code} has a wrong name, pick drop must end with -p")
        elif job_in.job_type == "drop":
            if job_in.code.split('-')[-1] != 'd':
                log.info(f"Job code {job_in.code} has a wrong name, drop job must end with -d.")
                raise HTTPException(status_code=400, detail=f"Job code {job_in.code} has a wrong name, drop job must end with -d")
        elif job_in.job_type == "pickup" and not job_in.code.endswith("-p"):
            raise HTTPException(
                status_code=400,
                detail=f"Job code {job_in.code} has a wrong name, the job_code must end with -p ",
            )
        if job_in.requested_start_datetime is None:
             raise HTTPException(status_code=400, detail=f"Job requested_start_datetime for {job_in.code} is None, forbiddened.")


        if not check_job_code_str(job_in.code):
            log.info(f"Job code {job_in.code} is invalid")
            raise HTTPException(status_code=400, detail=f"Job code {job_in.code} is invalid")

    order = get_by_code(db_session=db_session, code=order_in.code)
    if order:
        raise HTTPException(
            status_code=400,
            detail=f"The order with this code ({order_in.code}) already exists.",
        )

    order, db_job_list = create(db_session=db_session, current_user=current_user, order_in=order_in)

    if not order.auto_planning:
        log.info(f"order is not auto_planning {order}")
        return OrderCreationResult(status=OrderCreateResultStatusType.CREATED_BUT_NOT_DISPATCHED,                 
                                order = order,
                                scheduled_slots = None
                            )

    env = get_active_planner(
        org_id=current_user.org_id, team_id=order.team_id
    )
    
    if not order_in.target_worker :
        worker_whitelist = [] 
    else:
        worker_whitelist = [order_in.target_worker]

    
    res = replan_order(db_session = db_session,
                       env = env, 
                       order = order, 
                       db_job_list = db_job_list,
                       worker_whitelist=worker_whitelist,
                       overwrite_max_orders_limit = order_in.overwrite_max_orders_limit
    )
    # log.info(f"create_order:sending: {res.json()}") # TODO, this reports 500 :(
    log.info(f"create_order:sending:{order.code=}: {res.status=}, {res.worker_code=}, {res.scheduled_slots=} {res.reason_info=}")
    return res

    


@router.put("/{order_code}", response_model=OrderCreate)
def update_order(
    *, db_session: Session = Depends(get_db), order_code: str, order_in: OrderUpdate,
    current_user: DispatchUser = Depends(get_current_user),
):
    """
    Update a order.
    """
    order = get(db_session=db_session, code=order_code)
    if order.business_order_status != order_in.business_order_status:
        if order.business_order_status!="change_address":
            raise HTTPException(status_code=404, detail=f"The order status is already changed to {order.business_order_status}.")
    if not order:
        raise HTTPException(status_code=404, detail="The order with this code does not exist.")
    try:
        order = update(db_session=db_session, order=order, order_in=order_in, current_user = current_user)
    except InvalidConfiguration as e:
        raise HTTPException(status_code=400, detail=str(e))

    return order


@router.delete("/{order_code}")
def delete_order(*, db_session: Session = Depends(get_db), order_code: str,current_user: DispatchUser = Depends(get_current_user)):
    """
    Delete a single order.
    """
    log.info(f"start delete order : order code ={order_code}")
    data = get(db_session=db_session, code=order_code)
    if not data:
        log.info(f"delete order:  NOT EXIST ORDER , code = {order_code}")
        raise HTTPException(status_code=404, detail="The order with this code does not exist.")
    # delete all status order code
    # for job in data.job_order_rel:
    #     if job.planning_status not in (JobPlanningStatus.UNPLANNED, JobPlanningStatus.FINISHED):
    #         msg = f"The job {job.code} in this order is in status {job.planning_status}. Only U, F can be deleted."
    #         log.error(msg)
    #         raise HTTPException(status_code=400, detail=msg)
    team_id = data.team_id
    try:
        # delete_order_cascade(db_session=db_session, code=order_code,current_user=current_user,team_id=team_id)

        all_job_events = job_event_service.get_all_by_order_code(db_session=db_session, order_code=order_code )
        [db_session.delete(job_events) for job_events in all_job_events ]
        db_session.commit()
        log.info(f'all_job_events is deleted , {order_code} , all_job_events={all_job_events} ')
        # 删除JOB

        all_job = job_service.get_all_by_order_code(db_session=db_session, order_code=order_code )
        env = get_active_planner(org_id=current_user.org_id, team_id=team_id)
        for job in all_job:
            if  job.planning_status not in [JobPlanningStatus.IN_PLANNING] :
                continue

            log.info(f"orderCode: {order_code}, job.code:{job.code} current Job code status == I , delete from redis ")

            scheduled_start_datetime = env.env_encode_from_datetime_to_minutes(job.scheduled_start_datetime)
            slot_list = env.get_working_slot_list(
                worker_code=job.scheduled_primary_worker_code,
                start_minutes=scheduled_start_datetime-1,
                end_minutes=scheduled_start_datetime + 1,
                active_only=False,
            )

            # TODO
            for slot in slot_list:
                for ji,job_ in enumerate(slot.assigned_jobs):
                    if job_.code == job.code :
                        del slot.assigned_jobs[ji]
                        # slot.start_longitude = job.geo_longitude
                        # slot.start_latitude = job.geo_latitude
                        env.add_single_working_time_slot(
                            slot=slot,
                            update_ops = ["jobs"]
                        )
                        log.info(f"job {job.code } is deleted from worker {job.scheduled_primary_worker_code}, slot {slot.slot_code}")


        [db_session.delete(job) for job in all_job ]
        db_session.commit()
        log.info(f'all_job is deleted , {order_code} , all_job={all_job} ')

        # 删除 order_event
        all_order_events = order_event_service.get_by_order_code(db_session=db_session, order_code=order_code)
        [db_session.delete(order_events) for order_events in all_order_events ]
        db_session.commit()
        log.info(f'all_order_events is deleted , {order_code} , all_order_events={all_order_events} ')

        # delete order
        order = get(db_session=db_session, code=order_code)
        db_session.delete(order)
        db_session.commit()
        log.info(f'order is deleted , {order_code} , order={order} ')



    except IntegrityError:
        raise HTTPException(
            status_code=400, detail="The order is used by a team and can not be deleted."
        )
    return JSONResponse({"status":200, "detail":f"{order_code} delete success"})


@router.post("/batch_search/", response_model=OrderPagination, summary="batch earch order data.")
def batch_search(
    *,
    db_session: Session = Depends(get_db),
    current_user: DispatchUser = Depends(get_current_user),
    bartch_search_param: BatchSearchOrder,
    role: UserRoles = Depends(get_current_role),
):
    """ """

    common = common_parameters(
        db_session=db_session,
        query_str=bartch_search_param.q,
        role=role,
        current_user=current_user,
        page=bartch_search_param.page,
        items_per_page=bartch_search_param.itemsPerPage,
        sort_by=bartch_search_param.sortBy,
        descending=bartch_search_param.descending,
        fields=[],
        ops=[],
        values=[],
    )

    query_str = bartch_search_param.q.strip() if bartch_search_param.q else ""
    if "\n" in query_str or "\t" in query_str:
        order_code_list = [i for i in query_str.split() if i]
    else:
        order_code_list = [i for i in query_str.split(' ') if i]
    all_order = search_filter_sort_paginate_order(
        db_session,
        external_order_code=order_code_list,
        worker=bartch_search_param.scheduled_primary_worker,
        business_order_status=bartch_search_param.business_order_status, 
        tpl_region=bartch_search_param.tpl_region, 
        page=bartch_search_param.page,
        items_per_page=bartch_search_param.itemsPerPage,
        sort_by=bartch_search_param.sortBy,
        descending=bartch_search_param.descending,
        current_user=current_user,
        role = role
        )
    # new_items = []
    # for item in all_order["items"]:
    #     order = item.Order
    #     order.tpl_region = item.tpl_region
    #     new_items.append(order)

    result_order_code_list = find_external_order_code(db_session = db_session,external_order_code=order_code_list)
    not_find_code = [code for code in order_code_list if code not in result_order_code_list]

    return  {
        "items": all_order["items"],
        "itemsPerPage": all_order["itemsPerPage"],
        "page": all_order["page"],
        "total": all_order["total"],
        "not_find_code": not_find_code,
    }

@router.post(
    "/download/", summary="download order csv file."
)
async def download(*, db_session: Session = Depends(get_db),  bartch_search_param: DownloadOrder):

    """
    """
    result_order_code_list = []
    df = json_normalize([])
    query_str = bartch_search_param.q.strip() if bartch_search_param.q else ''
    if '\n' in query_str or '\t' in query_str:        
        order_code_list = [i for i in query_str.split() if i]
    else:
        order_code_list = [i for i in query_str.split(' ') if i]
    
    if order_code_list or bartch_search_param.scheduled_primary_worker or bartch_search_param.business_order_status or bartch_search_param.tpl_region:
        all_order = search_filter_order(
            db_session,
            external_order_code=order_code_list,
            worker=bartch_search_param.scheduled_primary_worker,
            business_order_status=bartch_search_param.business_order_status, 
            tpl_region=bartch_search_param.tpl_region
        )

        result_order_code_list = [order[0].external_order_code for order in all_order]
        not_find_code = [code for code in order_code_list if code not in result_order_code_list]
        df = order_to_df(db_session,all_order,not_find_code)
    random_str = list("abcdefgh")
    random.shuffle(random_str)
    filename = f"order_{time.time_ns()}_{''.join(random_str)}.csv"
    fd, file_path = tempfile.mkstemp(suffix='.csv')
    df.to_csv(file_path, encoding='utf-8', index=False)


    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="text/csv",
        background=BackgroundTask(lambda: os.remove(file_path)),
    )


def num_out(data):
    data = str(data) + "\t"
    return data

    sorted_date =  sorted(date_range, key=lambda k : k, reverse=False)
    start_date = f"{sorted_date[0]} 00:00:00"
    end_date = f"{sorted_date[1]} 23:59:59"
    order_in = OrderDownloadHistoryCreate(
        dispatch_user_id=current_user.id,
        start_time=start_date,
        end_time=end_date,
        status="creating",
        file_location=OSS_ENDPOINT,
        created_date=None,
        expiry_date=None
        )
    download_history_id = order_download_history_create(db_session, order_in)
    thread_put = threading.Thread(target=put_download_data, args=(db_session, status, order_in, download_history_id))
    thread_put.start()
    result = order_download_history_query(db_session)
    return result
    
@router.get(
    "/download_history/", summary="get all download history.")
def get_history(*, db_session: Session = Depends(get_db)):
    return order_download_history_query(db_session)

# def get_history(*, common: dict = Depends(common_parameters)):
#     """
#     """
#     if common["items_per_page"] < 0 or common["items_per_page"] > 100:
#         raise HTTPException(status_code=400, detail="items per page value is too large ...")
    # history_data = search_filter_sort_paginate(model="OrderDownloadHistory", **common)
    # return {
    #     "items": new_items,
    #     "itemsPerPage": history_data['itemsPerPage'] ,
    #     "page": history_data['page'] ,
    #     "total": history_data['total']
    # }


@router.get("/download_by_status/", summary="download order csv file.")
async def download_by_status(
    *,
    db_session: Session = Depends(get_db),
    date_range: List[str] = Query([], alias="date_range[]"),
    status: List[str] = Query([], alias="status[]"),
):
    sorted_date = sorted(date_range, key=lambda k: k, reverse=False)
    start_date = f"{sorted_date[0]} 00:00:00"
    end_date = f"{sorted_date[1]} 23:59:59"
    if "all" in status:
        all_data = get_by_time(db_session=db_session, start_time=start_date, end_time=end_date)
    else:
        all_data = get_status_and_time(
            db_session=db_session, status_list=status, start_time=start_date, end_time=end_date
        )

    df = order_to_df(db_session, all_data, [])

    random_str = list("abcdefgh")
    random.shuffle(random_str)
    filename = f"order_{time.time_ns()}_{''.join(random_str)}.csv"

    fd, file_path = tempfile.mkstemp(suffix=".csv")

    df.to_csv(file_path, encoding="utf-8", index=False)

    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="text/csv",
        background=BackgroundTask(lambda: os.remove(file_path)),
    )


@router.get("/related/{order_code}", response_model=OrderRelatedBase)
def get_order(
    *,
    db_session: Session = Depends(get_db),
    order_code: str,
    current_user: DispatchUser = Depends(get_current_user),
):
    """
    Get a order.
    """
    order = get(db_session=db_session, code=order_code)
    if not order:
        raise HTTPException(status_code=404, detail="The order with this code does not exist.")
    user = get_by_email(db_session=db_session, email=current_user.email)
    order_related = get_order_related_data(db_session=db_session, order_data=order, code=order_code, user_id=user.id, token=user.token    )
    return order_related


@router.put("/related/{order_code}")
def update_order_related(
    *,
    db_session: Session = Depends(get_db),
    order_code: str,
    order_related_in: OrderRelatedUpdate,
    current_user: DispatchUser = Depends(get_current_user),
):
    """
    Update a order.
    """
    order = get(db_session=db_session, code=order_code)
    if not order:
        raise HTTPException(status_code=404, detail="The order with this code does not exist.")

    user = get_by_email(db_session=db_session, email=current_user.email)
    try:
        flag = set_order_related(
            db_session=db_session,
            order=order,
            order_related_in=order_related_in,
            user_id=user.id,
            token=user.token,
        )
    except InvalidConfiguration as e:
        # raise HTTPException(status_code=400, detail=str(e))
        return {
            "msg": str(e),
            "flag": flag,
        }

    return flag


@router.post("/oss_signature/")
def oss_signature(
    *,
    db_session: Session = Depends(get_db),
    images_oss: ImagesOss = Body(
        ...,
        example={},
    ),
    current_user: DispatchUser = Depends(get_current_user),
):
    """
    Create a new order.
    """
    user = get_by_email(db_session=db_session, email=current_user.email)
    data = get_oss_signature(
        scenarioCode=images_oss.scenarioCode,
        fileSize=images_oss.fileSize,
        fileName=images_oss.fileName,
        user_id=user.code,
        token=user.token,
    )
    if not data:
        raise HTTPException(
            status_code=400,
            detail=f"get_oss_signature error.",
        )
    return data


# @router.post("/redliver/", response_model=RedliverResponse)
# def redliver(
#     *,
#     db_session: Session = Depends(get_db),
#     order_in: RedliverRequest = Body(
#         ...,
#         example={"order_code": "myOrder"},
#     ),
#     current_user: DispatchUser = Depends(get_current_user),
# ):
#     """
#     Create a new order.
#     """
#     order = get(db_session=db_session, code=order_in.order_code)
#     if not order:
#         return RedliverResponse(
#             status=0, message=f"The order with this code ({order_in.order_code}) already exists."
#         )
#     user = get_by_email(db_session=db_session, email=current_user.email)
#     result = do_redliver(order_code=order_in.order_code,user_id=user.code,token=user.token)
#     return RedliverResponse(status =result['status'],message = result['message'])







@router.get("/order_detail/{order_code}")
def redliver(
    *,
    db_session: Session = Depends(get_db),
    order_code : str , 
    current_user: DispatchUser = Depends(get_current_user),
):
    order = get_order_info(db_session=db_session, code=order_code)
    if not order:
        raise HTTPException(status_code=404, detail="The order with this code does not exist.")
    planner = get_active_planner(org_id= current_user.org_id, team_id= current_user.default_team_id)
    jobType = planner.config.get("bussiness_type","pickdrop")
    
    result = {}
    pickup_job = list(filter(lambda x : x.code.endswith("-p"), order.job_list))[0]
    delivery_job = list(filter(lambda x : x.code.endswith("-d"), order.job_list))[0]


    if is_pick_up_stage(order.business_order_status):
        address = pickup_job.flex_form_data.get("shipperAddress","shipperAddress-demo")
        current_job_code = order.code  +'-p'

    else:
        address = delivery_job.flex_form_data.get("customerAddress","customerAddress-demo")
        current_job_code = order.code  +'-d'
    result["jobType"]  = jobType
    result["current_job_code"] = current_job_code
    result["address"] = address
    result["canOperation"]  = True
    result["customerAddress"] = delivery_job.flex_form_data.get("customerAddress","customerAddress-demo")
    result["customerEmail"] = delivery_job.flex_form_data.get("customerEmail","customerEmail-demo")
    result["customerName"] = delivery_job.flex_form_data.get("customerName","customerName-demo")
    result["customerPhoneNumber"] = delivery_job.flex_form_data.get("customerPhoneNumber","customerPhoneNumber-demo")
    result["customerAddress"] = delivery_job.flex_form_data.get("customerAddress","customerAddress-demo")
    result["deliveryInfo"] = delivery_job.flex_form_data.get("deliveryInfo",'{"Volume":"1cm³","W":"1.00cm","H":"1.00cm","L":"1.00cm","Weight":"1kg"}')
    
    
    result["orderCode"] = order.code
    result["orderNo"] = order.external_order_code
    result["orderStatus"]  = order.business_order_status
    
    result["orderType"] = order.order_type
    
    
    result["requestPickUpEndTime"] = pickup_job.requested_start_datetime + timedelta(minutes=pickup_job.requested_duration_minutes) 
    result["requestPickUpStartTime"]= pickup_job.requested_start_datetime 
    
    result["requestedDropoffEndTime"] = delivery_job.requested_start_datetime + timedelta(minutes = pickup_job.requested_duration_minutes)
    result["requestedDropoffStartTime"] = delivery_job.requested_start_datetime
    result["shipperAddress"] = pickup_job.flex_form_data.get("shipperAddress","shipperAddress-demo")
    result["shipperEmail"] = pickup_job.flex_form_data.get("shipperEmail","shipperEmail-demo")
    result["shipperName"] = pickup_job.flex_form_data.get("shipperName","shipperName-demo")
    result["shipperPhoneNumber"] = pickup_job.flex_form_data.get("shipperPhoneNumber","shipperPhoneNumber-demo")
    
#     {
    #  根据实际要去的 地方 展示的 
#     "address": "shipper 551บริษัทสหคิมมอเตอร์  46-52 เฉลิมเขตร์3 วัดเทพศิรินทร์ เขตป้อมปราบศัตรูพ่าย",
#     "canOperation": true,
#     "customerAddress": "customer 551344 วัดสระเกศ (คณะ 6)  แขวงบ้านบาตร เขตป้อมปราบศัตรูพ่าย  กรุงเทพมหานคร 344 วัดสระเกศ (คณะ 6)  แขวงบ้านบาตร เขตป้อมปราบศัตรูพ่าย  กรุงเทพมหานคร",
#     "customerEmail": "customer551@domain.com",
#     "customerName": "customer เบญจวรรณ เยี่ยมพาณิชย์ภักดิ์shipperเบญจวรรณ เยี่ยมพาณิชย์ภักดิ์551",
#     "customerPhoneNumber": "+86-222255102",
#     "deliveryInfo": "{\"Volume\":\"6cm³\",\"W\":\"3.00cm\",\"H\":\"4.00cm\",\"L\":\"2.00cm\",\"Weight\":\"0.500kg\"}",
#     "dropOffJobBizId": 3050,
#     "isInCar": false,
#     "isSubmitProblem": false,
#     "jobBizId": 3049,
#     "jobStatus": "toDo",
#     "jobTrackStatus": "notStarted",
#     "jobType": "pickUp",
#     "locationId": 2,
#     "orderCode": "2023121815090700001",
#     "orderId": 2362,
#     "orderNo": "OTS20231218150906",
#     "orderStatus": "assigned",
#     "orderType": "sales_order",


#     "requestPickUpEndTime": 1702991346326,
#     "requestPickUpStartTime": 1702980546326,

#     "requestedDropoffEndTime": 1703099346326,
#     "requestedDropoffStartTime": 1703056146326,

#     "scheduledPickUpStartTime": 1702858200000,
#     "scheduledStartTime": 1702858200000,


#     "shipperAddress": "shipper 551บริษัทสหคิมมอเตอร์  46-52 เฉลิมเขตร์3 วัดเทพศิรินทร์ เขตป้อมปราบศัตรูพ่าย",
#     "shipperEmail": "shipper551@domain.com",
#     "shipperName": "shipper เบญจวรรณ เยี่ยมพาณิชย์ภักดิ์551",
#     "shipperPhoneNumber": "+86-111155101",
#     "shippingAmount": 10.1,
#     "sitePoint": "shipper"
# }
    
    
    return result

