from datetime import datetime
from typing import List, Optional

from anyio import Any

from dispatch.location.models import LocationCreate
from dispatch.models import DispatchBase
from pydantic import validator, Field

from dispatch.team.models import TeamCreate



class SimpleLocation(DispatchBase):
    """ A location is where a worker or a job is positioned on a map. The longitude and latitude are mandatory and textual addresses are optional.
    \n A location is treated as first class citizen in parallel to job because we see that there are repeated jobs for same customer and location. The historical assignment patterns can be learned on location level.
    """
    code: str = None
    geo_longitude: float = None
    geo_latitude: float = None
    geo_address_text: str = None
    geo_json: dict = None


class SimpleJob(DispatchBase):
    code: str = Field(
        title="Job Code", description='Job code is the unique identify for this job. It must be unique across all teams',)
    description: Optional[str] = None  
    requested_duration_minutes :Optional[int] = None  
    flex_form_data: Any = Field(
        default={}, title="Flexible Form Data", description='You can save all customized job attributes into a flex_form_data. Those data will be used by dispatching rule plugins to validate the worker-job assignment. \n Examples of field candidates are: requested_skills, job_schedule_type, ...',)
    location: SimpleLocation



class OptimizerRequest(DispatchBase):
    ak:  Optional[str] 
    token: Optional[str] 
    jobs:  Optional[List[SimpleJob]] 
    start_datetime:  Optional[datetime] 
    end_datetime:  Optional[datetime] 
    depot:Optional[SimpleLocation] 

class OptimizerJobBase(DispatchBase):

    id :int = None
    code: str = Field(
        title="Job Code", description='Job code is the unique identify for this job. It must be unique across all teams',)    
    scheduled_start_datetime: Optional[datetime] = None
   

class OptimizerResponese(DispatchBase):
    state: Optional[str]
    msg: Optional[str]
    planned_data: Optional[List[OptimizerJobBase]] = []
    not_planned_data: Optional[List[OptimizerJobBase]] = []