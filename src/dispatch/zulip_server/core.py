# for worker   订阅 自己的job , 按照一天作为一个stream, job 作为topic ,
# 每个topic[job] 都发的message : location ,job_code, 开始时间， 状态，等其他有用信息
# 每个job 更新事件都会向此topic 发送message,

# 所有worker 订阅自己的 orgnazation/team

# 发送消息，
# 创建stream ,订阅stream ,获取流中的主体，获取订阅的流，订阅流状态，等
# 获取所有用户， 自己，创建，停用，更新状态，重新激活，


# cli init all worker to  subcribe orgnization/team
# update/create worker to update topic[team] user ,and send privete message to worker

# job stream title like '2021/20/10'
# update job planner status to zulip message
# number of five day,to unsubcribe stream
# planned job change , and send message to this topic,etc. add to other worker ,delete my topic[job],send change message

# utils ,link google maps to show address
# new edit job page for zulip change detail


from dispatch.plugins.kandbox_planner.env.env_enums import JobPlanningStatus
from dispatch.plugins.kandbox_planner.util.cache_dict import CacheDict
from dispatch.org.service import get_all as get_all_org, get as org_get
import asyncio
from collections import defaultdict
import json
from os import name
from fastapi.exceptions import HTTPException
import redis
from datetime import datetime, timedelta

import requests
from dispatch.common.utils.encryption import decrypt, encrypt, token
from dispatch.config import REDIS_HOST, REDIS_PORT, REDIS_PASSWORD, WEBZ_SITE
import argparse
import logging
import sys
from typing import Any, Dict

import zulip

from dispatch.worker.service import get_by_team as get_worker_by_team
from dispatch.team.service import get_by_org_id_list as get_team_by_org_id_list
from dispatch.auth import service as auth_service
from dispatch.database import SessionLocal
session_local_module = SessionLocal()
log = logging.getLogger("zulip")


def log_result(response: Dict[str, Any]) -> None:
    result = response["result"]
    if result == "success":
        log.info(response)
    else:
        log.error(response['msg'])
    return result


def get_api(username, password, site, refresh=False):
    # curl - sSX POST https: // little.zulipchat.com / api / v1 / fetch_api_key \
    #     - -data - urlencode username = 1 @ q.com \
    #     - -data - urlencode password = =
    try:
        site_user_api_key = f"{username}:{site}"
        if REDIS_PASSWORD == "":
            pool = redis.ConnectionPool(host=REDIS_HOST, port=REDIS_PORT, password=None)
        else:
            pool = redis.ConnectionPool(host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD)
        redis_conn = redis.Redis(connection_pool=pool)
        data = redis_conn.get(site_user_api_key)
        api_data = {}

        if data:
            api_data = eval(data.decode('utf-8')) if isinstance(data, bytes) else eval(data)

        if refresh or not data:
            # param = {
            #     "username": username,
            #     "password": decrypt(str(password, 'utf-8'))
            # }
            # url = f"{site}/api/v1/fetch_api_key"
            # res = requests.post(url=url,
            #                     headers={
            #                         'content-type': "application/x-www-form-urlencoded",
            #                     },
            #                     data=param)
            # res.content.decode('utf-8')
            # if res.status_code != 200:
            #     log.error(json.loads(res.text))
            #     raise HTTPException(status_code=400, detail=json.loads(res.text))
            # api_data = res.json()
            api_data = {"api_key": decrypt(str(password, 'utf-8')), "email": username}
            redis_conn.set(site_user_api_key, str(json.dumps(api_data)))
        return api_data
    except Exception as e:
        log.error(e)
        return {}


async def unsubcribe_stream_by_days(days=5, refresh_count=999999999999, interval_seconds=3600):
    # timing to do for every day 5 am
    # data to redis user_eamil:[stream_name1,stream_name2]
    for r_i in range(refresh_count):
        await asyncio.sleep(interval_seconds)
        try:
            for org_id, org_dict in all_zulip_client_dict.items():
                zulip_core = org_dict['client']

                today = datetime.now()
                flag = zulip_core.redis_conn.get(str(today.date()))
                if today.hour < 5 or flag:
                    continue
                zulip_core.redis_conn.set(str(today.date()), 1)
                worker_dict = zulip_core._get_workers()
                if not worker_dict:
                    log.warning("timing unsubcribe_stream_by_five_day ,worker is null")
                    return False

                history_two_date_list = [str((today + timedelta(days=-i)).date()) for i in range(2)]
                history_five_date_list = [str((today + timedelta(days=-i)).date())
                                          for i in range(5)]
                for org_team_str, worker_list in worker_dict.items():
                    org_code = org_team_str.split('/')[0]
                    team_code = org_team_str.split('/')[1]
                    for worker in worker_list:

                        zulip_email = worker.flex_form_data.get('zulip_email', '')
                        zulip_user_info = zulip_core.get_user_or_add_in_redis(zulip_email)
                        user_id = zulip_user_info['user_id'] if zulip_user_info else None

                        if not user_id:
                            log.info(f"{worker.code} no zulip user_id info")
                            continue
                        redis_key = zulip_core.redis_worker_key.format(
                            worker.code, org_code, team_code)
                        worker_stream_list = zulip_core.get_redis_subcribe_by_worker_code(redis_key)
                        if not worker_stream_list:
                            log.info(f"{worker.code} no subscribe info")
                            continue
                        user_result = zulip_core.users_core.get_user_by_id(user_id=user_id)
                        if user_result['result'] == 'success':
                            filter_stream_list = []
                            for stream_name in worker_stream_list:
                                if 'Team_' in stream_name:
                                    continue
                                job_code = stream_name.split('|')[1]
                                job_key = zulip_core.redis_worker_key.format(
                                    job_code, org_code, team_code)

                                redis_job_dict = zulip_core.redis_conn.get(job_key)
                                redis_job_dict = eval(redis_job_dict.decode('utf-8'))
                                day = redis_job_dict['day']
                                planning_status = redis_job_dict['planning_status']
                                if planning_status == JobPlanningStatus.PLANNED:
                                    if all([day in j for j in history_two_date_list]):
                                        continue
                                else:
                                    if all([day in j for j in history_five_date_list]):
                                        continue
                                filter_stream_list.append(stream_name)

                            # filter user group
                            if filter_stream_list:
                                result = zulip_core.streams_core.remove_subscriptions(
                                    stream_list=filter_stream_list, principals=[user_result['user']['email']])
                                if result['result'] == 'success':
                                    zulip_core.update_redis_worker_stream(
                                        worker, filter_stream_list, False)
                                    log.info(
                                        f"{worker.code} unsubscribe {filter_stream_list} success!")
                                else:
                                    log.error(
                                        f"{worker.code} unsubscribe {filter_stream_list} failure !")

        except Exception as e:
            log.error(f'unsubcribe_stream_by_days error {e}')


def get_zulip_client():
    try:
        all_zulip_client = {}
        session_local = SessionLocal()
        org_list = get_all_org(db_session=session_local)
        for org_obj in org_list:
            if not org_obj.zulip_is_active:
                continue
            config = get_api(org_obj.zulip_user_name, org_obj.zulip_password, org_obj.zulip_site)
            client = zulip.Client(email=config.get(
                'email'), api_key=config.get('api_key'), site=org_obj.zulip_site)
            all_zulip_client[org_obj.id] = {
                "org_obj": org_obj,
                "client": ZulipCore(org_obj, client),
            }
            all_zulip_client[org_obj.id]['client'].init_subcribe_team()

    except Exception as e:
        log.error(f"_get_workers failure,msg={e}")
    finally:
        try:
            session_local.close()
        except:
            pass
    return all_zulip_client


def get_zulip_client_by_org_id(org_id):
    try:
        session_local = SessionLocal()
        return_data = {}
        org_obj = org_get(db_session=session_local, org_id=org_id)
        if org_obj and org_obj.zulip_is_active:

            if org_id in all_zulip_client_dict:
                return_data = all_zulip_client_dict[org_id]
            else:
                all_zulip_client = {}
                config = get_api(org_obj.zulip_user_name,
                                 org_obj.zulip_password, org_obj.zulip_site)
                if config:
                    client = zulip.Client(email=config.get(
                        'email'), api_key=config.get('api_key'), site=org_obj.zulip_site)
                    all_zulip_client[org_obj.id] = {
                        "org_obj": org_obj,
                        "client": ZulipCore(org_obj, client),
                    }
                    return_data = all_zulip_client[org_obj.id]
    except Exception as e:
        log.error(f"get_zulip_client_by_org_id failure,msg={e}")
    finally:
        session_local.close()
    return return_data


class ZulipCore(object):

    def __init__(self, org_obj, client):
        self.org_code = org_obj.code
        self.org_obj = org_obj
        self.client = client
        self.message_core = ZulipMessageCore(client=self.client, log_result=log_result)
        self.streams_core = ZulipStreamCore(client=self.client, log_result=log_result)
        self.users_core = ZulipUserCore(client=self.client, log_result=log_result)
        self.team_stream_name = 'Team_{}'  # Team_teamcode
        self.job_stream_name = '{}|{}'  # 20210201_jobcode
        self.job_topic_name = 'job_events'  # '0985_jobname'
        self.redis_worker_key = '{}_{}_{}_stream_list'  # 'jane_orgcode_teamcode_stream_list':[]
        self.user_info_key = '{}_{}'  # email_orgcode
        # job1_orgcode_teamcode' :  {
        #     "worker_code_list": [worker1,worker2],
        #     "zulip_user_id": [userid1,userid2],
        #     "stream": job_stream_name,
        #     "topic": job_topic_name,
        # }
        self.redis_job_key = '{}_{}_{}_job_stream_dict'
        if REDIS_PASSWORD == "":
            pool = redis.ConnectionPool(host=REDIS_HOST, port=REDIS_PORT, password=None)
        else:
            pool = redis.ConnectionPool(host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD)
        self.redis_conn = redis.Redis(connection_pool=pool)
        self.admin_user_id = self.users_core.get_user_by_email(org_obj.zulip_user_name)[
            'user']['user_id']
        self.google_links = "[Show Address {}](http://www.google.com/maps/place/{},{}/@{},{},17z)"
        # self.edit_job_links = "[Edit Job]({}/edit_job?jobId={}&token={})"
        self.edit_job_links = "[Edit Job]({}/job_edit_4_worker?jobId={}&token={})"
        self.edit_job_token = 'job_edit_token|{}'  # job_edit_token|123 ,vlaue :token

    def get_user_or_add_in_redis(self, email):
        key = self.user_info_key.format(email, self.org_code)
        userinfo = self.redis_conn.get(key)
        if not userinfo:
            result = self.users_core.get_user_by_email(email=email)
            if result['result'] == 'success':
                userinfo = result['user']
                self.redis_conn.set(key, str(json.dumps(userinfo)))
            else:
                userinfo = None
        else:
            userinfo = json.loads(userinfo.decode('utf-8')) if isinstance(userinfo,
                                                                          bytes) else json.loads(userinfo)
        return userinfo

    def _get_workers(self):

        try:
            worker_list = []
            session_local = SessionLocal()
            all_team = get_team_by_org_id_list(db_session=session_local, org_id=self.org_obj.id)
            use_zulip_team_list = [
                team.id for team in all_team if team.flex_form_data.get('use_zulip', False)]

            for team_id in use_zulip_team_list:
                inner_worker_list = get_worker_by_team(db_session=session_local, team_id=team_id)
                if inner_worker_list:
                    worker_list.extend(inner_worker_list)

            worker_dict = defaultdict(list)
            for worker in worker_list:
                team_code = worker.team.code
                worker_dict[f"{self.org_obj.code}/{team_code}"].append(worker)

        except Exception as e:
            log.error(f"_get_workers failure,msg={e}")
        finally:
            session_local.close()

        return worker_dict

    def init_subcribe_team(self):
        try:
            worker_dict = self._get_workers()
            for org_team_str, worker_list in worker_dict.items():
                org_code = org_team_str.split('/')[0]
                team_code = org_team_str.split('/')[1]
                self.workers_subcribe_team(worker_list=worker_list,
                                           org_code=org_code, team_code=team_code)
        except Exception as e:
            log.error(f"init worker failure,msg={e}")

    def workers_subcribe_team(self, worker_list, org_code, team_code):
        # start server do this
        all_user_list = [i.flex_form_data['zulip_email']
                         for i in worker_list if i.flex_form_data.get('zulip_email', '')]
        all_userid_list = []
        for email in all_user_list:
            userinfo = self.get_user_or_add_in_redis(email)
            if userinfo:
                all_userid_list.append(userinfo['user_id'])

        if not all_userid_list:
            log.info(f'{org_code},{team_code},database worker no zulip_user info')
            return 0
        if self.admin_user_id not in all_userid_list:
            all_userid_list.append(self.admin_user_id)
        stream_name = self.team_stream_name.format(team_code)
        all_users = self.streams_core.get_subscribers(stream_name)
        unsubcribe_user_list = [
            i for i in all_userid_list if i not in all_users.get('subscribers', [])]
        if not unsubcribe_user_list:
            log.info(f"{org_code},{team_code},all worker have subcribe")
            return 0
        result = self.streams_core.add_subscriptions(
            stream_name=stream_name, user_id_list=unsubcribe_user_list)
        if result['result'] == 'success':
            for worker in worker_list:
                zulip_email = worker.flex_form_data.get('zulip_email', '')
                zulip_user_info = self.get_user_or_add_in_redis(zulip_email)
                if zulip_user_info:
                    zulip_user_id = zulip_user_info['user_id']
                else:
                    continue
                if not zulip_email or zulip_user_id not in unsubcribe_user_list:
                    continue
                redis_worker_key = self.redis_worker_key.format(worker.code, org_code, team_code)
                self.update_redis_worker_stream(redis_worker_key, [stream_name], True)
            return len(unsubcribe_user_list)
        else:
            return 0

    def update_add_subscribe_user_group(self, worker, org_code, team_code, flag):
        use_zulip = worker.team.flex_form_data.get('use_zulip', False)
        if not use_zulip:
            return None
        if not org_code:
            org_code = self.org_code
        zulip_email = worker.flex_form_data.get('zulip_email', '')
        zulip_user_info = self.get_user_or_add_in_redis(zulip_email)
        user_id = zulip_user_info['user_id'] if zulip_user_info else None

        if not user_id:
            log.info(f"{worker.code} no zulip user_id info")
            return None
        stream_name = self.team_stream_name.format(team_code)
        result = self.update_add_subscribe_by_user_id(
            worker, org_code, team_code, stream_name, flag)
        return result

    def update_add_subscribe_by_user_id(self, worker, org_code, team_code, stream_name, flag, is_private=False, user_id=None):
        if not user_id:
            zulip_email = worker.flex_form_data.get('zulip_email', '')
            zulip_user_info = self.get_user_or_add_in_redis(zulip_email)
            user_id = zulip_user_info['user_id'] if zulip_user_info else None
        if not user_id:
            log.info(f"{worker.code} no zulip user_id info")
            return 0
        all_users = self.streams_core.get_subscribers(stream_name)
        is_subscribed = False
        if user_id in all_users.get('subscribers', []):
            is_subscribed = True
        result = None
        if flag and not is_subscribed:
            # do subcribe
            user_id_list = [user_id] if user_id == self.admin_user_id else [
                user_id, self.admin_user_id]
            result = self.streams_core.add_subscriptions(
                stream_name=stream_name, user_id_list=user_id_list)
            # change private
            if is_private:
                stream_id = self.streams_core.get_stream_id(stream_name=stream_name)["stream_id"]
                param = {
                    "is_private": is_private,
                }
                self.streams_core.update_stream(stream_id=stream_id, param=param)
        if not flag and is_subscribed:
            # do unsubcribe
            user_result = self.users_core.get_user_by_id(user_id=user_id)
            if user_result['result'] == 'success':
                result = self.streams_core.remove_subscriptions(
                    stream_list=[stream_name], principals=[user_result['user']['email']])
        if result and result['result'] == 'success':
            redis_worker_key = self.redis_worker_key.format(worker.code, org_code, team_code)
            return self.update_redis_worker_stream(redis_worker_key, [stream_name], flag)
        else:
            return result

    def update_redis_worker_stream(self, redis_worker_key, stream_list, flag):

        if flag:
            # add
            self.redis_conn.rpush(redis_worker_key, *stream_list)
            return 1
        else:
            # delete
            if self.redis_conn.exists(redis_worker_key) > 0 and self.redis_conn.llen(redis_worker_key) > 0:
                param_list = self.get_redis_subcribe_by_worker_code(redis_worker_key)
                filter_list = [i for i in param_list if i not in stream_list]
                self.redis_conn.delete(redis_worker_key)
                if filter_list:
                    self.redis_conn.rpush(redis_worker_key, *filter_list)
                return 1
            else:
                return 0

    def get_redis_subcribe_by_worker_code(self, redis_key):

        param_list = self.redis_conn.lrange(redis_key, 0, -1)
        param_list = [i.decode('utf-8') if isinstance(i, bytes) else i for i in param_list]
        return param_list

    def send_job_infomation(self, job, job_stream_name, job_topic_name,user_id):

        google_address_link = self.google_links.format(job.location.location_code, job.location.geo_latitude,
                                                       job.location.geo_longitude, job.location.geo_latitude, job.location.geo_longitude)
        # token_value = token(job.id)

        user = auth_service.get(
            db_session=session_local_module,
            user_id = user_id) # _user_by_id
        token_value = user.generate_token(duration_seconds=60*60*24*7)

        send_new_page_link_info = self.edit_job_links.format(WEBZ_SITE, job.id, token_value)
        requested_skills = ""
        requested_skills_list = job.requested_skills if job.requested_skills else []
        for i, skill in enumerate(requested_skills_list, start=1):
            requested_skills += f" {i}. {skill}"
        requested_skills = requested_skills if requested_skills else "None"
        requested_items = ""
        requested_items_list = job.requested_items if job.requested_items else []
        for i, item in enumerate(requested_items_list, start=1):
            requested_items += f" {i}. {item}"
        requested_items = requested_items if requested_items else "None"
        content = f"**{job.code}**, [{send_new_page_link_info}],Start **{str(job.scheduled_start_datetime)}**, Duration **{job.scheduled_duration_minutes} Minute**,  \
               Requested Skills **{requested_skills}**, Requested Items **{requested_items}**,[{google_address_link}]"
        request = {
            "type": "stream",
            "to": job_stream_name,
            "topic": job_topic_name,
            "content": content,
        }
        msg_result = self.message_core.send_message(message_data=request)


        request["widget_content"] = """{"widget_type": "zform", "extra_data": {"type": "choices", "heading": "You can also click the following options to manage """ + job.code + """: ", "choices": [{"type": "multiple_choice", "short_name": "Start", "long_name": "Start the job", "reply": "start """ + job.code + """ "}, {"type": "multiple_choice", "short_name": "Finish", "long_name": "Finish job", "reply":  "finish """ + job.code + """ "} ]}}"""
        response = self.message_core.send_message(request)

        return msg_result

    def first_job_planned_send_message(self, job, worker_dict, team_code):
        if not worker_dict:
            return False
        time_str = job.scheduled_start_datetime.strftime('%H:%M')
        datatime_str = job.scheduled_start_datetime.strftime('%Y-%m-%d')
        job_stream_name = self.job_stream_name.format(time_str, job.code)
        for userid, worker in worker_dict.items():
            self.update_add_subscribe_by_user_id(
                worker, self.org_code, team_code, job_stream_name, True, True, userid)

        msg_result = self.send_job_infomation(
            job=job, job_stream_name=job_stream_name, job_topic_name=self.job_topic_name, user_id=worker.dispatch_user.id)
        # redis add jobkey and worker info mapping
        redis_job_key = self.redis_job_key.format(job.code, self.org_code, team_code)
        mapping_data = {
            "worker_code_list": [worker.code for worker in worker_dict.values()],
            "zulip_user_id": list(worker_dict.keys()),
            "stream": job_stream_name,
            "topic": self.job_topic_name,
            "day": datatime_str,
            "planning_status": job.planning_status,
        }
        self.redis_conn.set(redis_job_key, str(json.dumps(mapping_data)))

        return msg_result

    def update_job_send_message(self, job, worker_list):
        worker_dict = {}
        worker_dict_by_worker_id = {}
        for worker in worker_list:
            use_zulip = worker.team.flex_form_data.get('use_zulip', False)
            if not use_zulip:
                continue
            zulip_email = worker.flex_form_data.get('zulip_email', '')
            zulip_user_info = self.get_user_or_add_in_redis(zulip_email)
            user_id = zulip_user_info['user_id'] if zulip_user_info else None
            if not user_id:
                log.info(f"{worker.code} no zulip user_id info")
                continue
            worker_dict[user_id] = worker
            worker_dict_by_worker_id[worker.id] = worker

        if not worker_dict:
            return False

        team_code = job.team.code
        redis_job_key = self.redis_job_key.format(job.code, self.org_code, team_code)
        redis_job_dict = None

        datatime_str = job.scheduled_start_datetime.strftime('%H:%M')
        job_stream_name = self.job_stream_name.format(datatime_str, job.code)
        worker_code_list = [worker.code for worker in worker_dict.values()]
        job_key_change_flag = False
        subcribed_flag = False
        if self.redis_conn.exists(redis_job_key) > 0:
            subcribed_flag = True
            redis_job_dict = self.redis_conn.get(redis_job_key)
            redis_job_dict = eval(redis_job_dict.decode('utf-8'))
            if job_stream_name != redis_job_dict['stream'] or set(worker_code_list) != set(redis_job_dict['worker_code_list']):
                job_key_change_flag = True

        # worker and start time not change
        # send change infomation on this topic

        # worker and start time change
        # do first _job_planned_send_message for other worker
        # send private message to this user :this job go to other worker ,or ther time ,and send close topic
        return_data = False
        if not subcribed_flag:
            return_data = self.first_job_planned_send_message(
                job=job, worker_dict=worker_dict, team_code=team_code)
        else:
            if not job_key_change_flag:
                return_data = self.send_job_infomation(
                    job=job, job_stream_name=job_stream_name, 
                    job_topic_name=self.job_topic_name,
                    user_id = worker_dict_by_worker_id[job.scheduled_primary_worker_id].dispatch_user.id
                    )
            else:
                # 换worker
                return_data = self.first_job_planned_send_message(
                    job=job, worker_dict=worker_dict, team_code=team_code)
                content = f"{job.code}  changed, \
                            {redis_job_dict['stream']}, {redis_job_dict['worker_code_list']}==>\
                            {job_stream_name}, ,{worker_code_list}"
                request = {
                    "type": "private",
                    "to": list(worker_dict.keys()),
                    "content": content,
                }
                self.message_core.send_message(message_data=request)
                # close old topic
                if job_stream_name != redis_job_dict['stream']:
                    self.streams_core.delete_stream(redis_job_dict['stream'])

        return return_data


class ZulipStreamCore(object):

    def __init__(self, client, log_result):
        self.client = client
        self.log_result = log_result

    def add_subscriptions(self, stream_name, user_id_list):
        result = self.client.add_subscriptions(
            streams=[
                {"name": stream_name},
            ],
            principals=user_id_list,
        )
        self.log_result(result)
        return result

    def get_subscriptions(self):
        result = self.client.get_subscriptions()
        self.log_result(result)
        return result

    def remove_subscriptions(self, stream_list, principals):
        result = self.client.remove_subscriptions(
            stream_list,
            principals,
        )
        self.log_result(result)
        return result

    def call_endpoint_subscriptions(self, user_id, stream_id):
        result = self.client.call_endpoint(
            url=f"/users/{user_id}/subscriptions/{stream_id}",
            method="GET",
        )
        self.log_result(result)
        return result

    def get_subscribers(self, stream_name):
        result = self.client.get_subscribers(stream=stream_name)
        self.log_result(result)
        return result

    def get_streams(self):
        result = self.client.get_streams()
        self.log_result(result)
        return result

    def get_stream_id(self, stream_name):
        result = self.client.get_stream_id(stream_name)
        self.log_result(result)
        return result

    def delete_stream(self, stream_name):
        stream = self.client.get_stream_id(stream_name)
        if stream:
            stream_id = stream["stream_id"]
            result = self.client.delete_stream(stream_id)
            self.log_result(result)
            return result
        else:
            return None

    def get_stream_topics(self, stream_id):
        result = self.client.get_stream_topics(stream_id)
        self.log_result(result)
        return result

    def call_endpoint_delete_topic(self, stream_name, topic_name):
        stream = self.client.get_stream_id(stream_name)
        if stream:
            stream_id = stream["stream_id"]
            request = {
                "topic_name": topic_name,
            }
            result = self.client.call_endpoint(
                url=f"/streams/{stream_id}/delete_topic", method="POST", request=request
            )
            self.log_result(result)
            return result
        else:
            return None

    def update_stream(self, stream_id, param):
        request = {
            "stream_id": stream_id
        }
        request.update(param)
        result = self.client.update_stream(request)
        self.log_result(result)
        return result


class ZulipUserCore(object):

    def __init__(self, client, log_result):
        self.client = client
        self.log_result = log_result

    def get_me(self):
        return self.client.get_profile()

    def get_members(self):
        result = self.client.get_members()
        return result

    def get_user_by_id(self, user_id):
        result = self.client.get_user_by_id(user_id)
        return result

    def get_user_by_email(self, email):
        result = self.client.call_endpoint(
            url=f"/users/{email}",
            method="GET",
        )
        return result

    def create_user(self, request):
        '''
        request = {
            "email": "newbie@zulip.com",
            "password": "temp",
            "full_name": "New User",
        }
        '''
        result = self.client.create_user(request)
        self.log_result(result)
        return result

    def deactivate_user_by_id(self, user_id):
        result = self.client.deactivate_user_by_id(user_id)
        self.log_result(result)
        return result

    def reactivate_user_by_id(self, user_id):
        result = self.client.reactivate_user_by_id(user_id)
        self.log_result(result)
        return result


class ZulipMessageCore(object):

    def __init__(self, client, log_result):
        self.client = client
        self.log_result = log_result

    def send_message(self, message_data: Dict[str, Any]) -> bool:
        """Sends a message and optionally prints status about the same."""

        if message_data["type"] == "stream":
            log.info(
                'Sending message to stream "%s", topic "%s"... '
                % (message_data["to"], message_data["topic"])
            )
        else:
            log.info("Sending message to {}... ".format(message_data["to"]))
        response = self.client.send_message(message_data)
        if response["result"] == "success":
            log.info("Message sent.")
            return True
        else:
            log.error(response["msg"])
            return False

    def delete_message(self, message_id):

        result = self.client.delete_message(message_id)
        self.log_result(result)
        return result


all_zulip_client_dict = CacheDict(cache_len=9999)
all_zulip_client_dict = get_zulip_client()
all_zulip_client_dict_by_org_code ={}
for v in all_zulip_client_dict.values():
    all_zulip_client_dict_by_org_code[v["org_obj"].code] = v["client"]


if __name__ == "__main__":
    core = ZulipCore()
    me = core.users_core.get_user_by_email('@1.com')
    user_id = me['user']['user_id'] 
    print(user_id)
