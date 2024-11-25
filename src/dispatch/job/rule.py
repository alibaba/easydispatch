
from functools import wraps
from datetime import datetime, timedelta
import logging

from fastapi import HTTPException

from dispatch.job.service import get
from dispatch.config import e6yun_config_dict
log = logging.getLogger("job_rule")


def e6yun_job_create(option='create'):
    def e6yun_job_create_decorator(func):
        '''
        '''
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                db_session = kwargs['db_session']
                if option in ['update', 'create']:
                    org_code = kwargs['current_user'].org_code
                    job_in = kwargs['job_in']
                    job_code = kwargs.get('job_code')
                    team = job_in.team
                    requested_start_datetime = job_in.requested_start_datetime
                    scheduled_primary_worker = job_in.scheduled_primary_worker
                else:
                    org_code = kwargs['current_user'].org_code
                    job_code = kwargs['job_code']
                    if org_code == e6yun_config_dict['org_code']:
                        job = get(db_session=db_session, code=job_code)
                        if not job:
                            raise HTTPException(status_code=404, detail="The requested job does not exist.")

                    team = job.team
                    requested_start_datetime = job.requested_start_datetime
                    scheduled_primary_worker = job.scheduled_primary_worker

                if org_code != e6yun_config_dict['org_code'] or str(team.id) != str(e6yun_config_dict['team_id']):

                    return func(*args, **kwargs)

                # 每个订单改 [requested min tolerance  , resuested max tolerance] 为任务的当天
                # 'tolerance_start_minutes': 0
                # 'tolerance_end_minutes': 270

                if option in ['create', 'update']:
                    requested_start_datetime = job_in.requested_start_datetime
                    requested_start_datetime_min = requested_start_datetime.hour * 60 + requested_start_datetime.minute
                    end_min = 24 * 60
                    tolerance_start_minutes = 0 - requested_start_datetime_min
                    tolerance_end_minutes = end_min - requested_start_datetime_min
                    job_in.flex_form_data['tolerance_start_minutes'] = tolerance_start_minutes
                    job_in.flex_form_data['tolerance_end_minutes'] = tolerance_end_minutes
                    kwargs['job_in'] = job_in

                return func(*args, **kwargs)
            except:
                import traceback
                log.error(traceback.format_exc())

        return wrapper

    return e6yun_job_create_decorator
