import json
import logging
from typing import Tuple

import redis
from intervaltree import Interval, IntervalTree
from dispatch.config import PLANNER_SERVER_ROLE
from dispatch import config
from dispatch.plugins.kandbox_planner.env.env_enums import *

# RTree and Intervaltree, similar?
from dispatch.plugins.kandbox_planner.env.env_enums import (
    JobPlanningStatus,
    JobType,
    TimeSlotType,
    TimeSlotOperationType,
    ActionType,
    KafkaMessageType,
)
from dispatch.plugins.kandbox_planner.env.env_models import (
    ActionDict,
    BaseJob,
    LocationTuple,
    TimeSlotJSONEncoder,
    WorkingTimeSlot,
    JobLocationBase,
)

from rtree import index


log = logging.getLogger("rl_env.working_time_slot.cache_only")
log.setLevel(logging.ERROR)

MAX_MINUTES_PER_TECH = 10_000_000  # 10,000,000 minutes =  20 years.
MAX_JOBS_IN_ONE_SLOT = 10
MAX_TRANSACTION_RETRY = 2

# Done (2020-10-16 10:05:06), replaced  array of "working_time_slots"?
# https://stackoverflow.com/questions/2646157/what-is-the-fastest-to-access-struct-like-object-in-python
# https://medium.com/@jacktator/dataclass-vs-namedtuple-vs-object-for-performance-optimization-in-python-691e234253b9
# namedtuples are optimised for access as tuples. If you change your accessor to be a[2] instead of a.c, you'll see similar performance to the tuples. The reason is that the name accessors are effectively translating into calls to self[idx], so pay both the indexing and the name lookup price.


SLOT_CODE_SET_FOR_DEBUG = []  # "env_MY_2/CT02_01950_02520_F"


class MissingSlotException(Exception):
    def __init__(self, slot_code, message):
        self.slot_code = slot_code
        self.message = message


# https://code.activestate.com/recipes/389916-example-setattr-getattr-overloading/
class TestingSlotDict(dict):
    """Example of overloading __getatr__ and __setattr__
    This example creates a dictionary where members can be accessed as attributes
    """

    def __setitem__(self, key, value):
        """Maps attributes to values.
        Only if we are initialised
        """
        if key in SLOT_CODE_SET_FOR_DEBUG:
            log.debug(f"pause SLOT_CODE_SET_FOR_DEBUG={SLOT_CODE_SET_FOR_DEBUG}")

        super(TestingSlotDict, self).__setitem__(key, value)


class CacheOnlySlotServer:
    def __init__(self, env, redis_conn):  # team_id is included in worker_code
        self.env = env
        self.r = redis_conn
        self.rtree_properties = index.Property()
        # longitude, latitude, time/minutes, worker id (int)
        self.rtree_properties.dimension = 4
        self.time_slot_dict = TestingSlotDict()
        self.time_slot_tree = IntervalTree()
        self.rtree_index = index.Index(properties=self.rtree_properties, interleaved=False)

        # self.reset()

    def get_time_slot_key(self, slot: WorkingTimeSlot) -> str:
        #  worker_id, start_minutes, end_minutes, slot_type,  worker_id,start_minutes, end_minutes, slot_type

        start_minutes_str = str(int(slot.start_minutes)).zfill(5)
        end_minutes_str = str(int(slot.end_minutes)).zfill(5)

        return f"{self.env.team_env_key}/s/{slot.worker_id}_{start_minutes_str }_{ end_minutes_str}_{ slot.slot_type}"

    def reload_from_redis_server(self):

        for slot_code in self.r.scan_iter(f"{self.env.team_env_key}/s/*"):
            slot_code_str = slot_code.decode("utf-8")
            self.get_from_redis_to_internal_cache(slot_code_str)

    def reset(self):
        self.time_slot_dict = TestingSlotDict()
        self.time_slot_tree = IntervalTree()
        self.rtree_index = index.Index(properties=self.rtree_properties, interleaved=False)
        self.reload_from_redis_server()
        return

        # for key in self.r.scan_iter(f"{self.env.team_env_key}/s/*"):
        #     self.r.delete(key)

    def get_from_redis_to_internal_cache(self, slot_code) -> WorkingTimeSlot:
        try:
            slot_on_redis = self.r.get(slot_code)
            if slot_on_redis is None:
                log.error(f"Failed to read slot_code={slot_code} from redis.  ? remove process")

            current_slot_as_list = json.loads(slot_on_redis)
            slot = WorkingTimeSlot(*current_slot_as_list)
            self._set_into_internal_cache(slot_code, slot)
        except MissingSlotException as mse:
            log.error(
                f"Failed to read slot_code={mse.slot_code}. During get_from_redis_to_internal_cache"
            )
            return None

    def get_slot(self, redis_handler, slot_code, raise_exception=True) -> WorkingTimeSlot:
        return self.time_slot_dict[slot_code]

    def set_slot(self, slot):
        slot_code = self.get_time_slot_key(slot)
        if slot_code in SLOT_CODE_SET_FOR_DEBUG:
            log.debug(f"pause SLOT_CODE_SET_FOR_DEBUG={SLOT_CODE_SET_FOR_DEBUG}")

        self._set_into_internal_cache(slot_code, slot)
        return True

    def add_single_working_time_slot(
        self, worker_code: str, start_minutes: int, end_minutes: int, start_location, end_location
    ) -> WorkingTimeSlot:
        # assert False

        if end_minutes - start_minutes < 1:
            return None
        # It is such a luxury to have fake start / end for every day. So I used None to denote start/end of time slots in one original slot.
        # 2020-10-14 08:53:33
        start_location_base = JobLocationBase(*start_location[0:4])
        end_location_base = JobLocationBase(*end_location[0:4])
        slot = WorkingTimeSlot(
            slot_type=TimeSlotType.FLOATING,
            start_minutes=start_minutes,
            end_minutes=end_minutes,
            prev_slot_code=None,
            next_slot_code=None,
            start_location=start_location_base,
            end_location=end_location_base,
            worker_id=worker_code,
            available_free_minutes=end_minutes - start_minutes,
            assigned_job_codes=[],
        )
        a = self.set_slot(slot)

        return slot

    def delete_slot__TODEL(
        self, slot_code: str
    ):  # worker_id, start_minutes, end_minutes, slot_type,
        assert False

        if slot_code in self.time_slot_dict.keys():
            slot = self.time_slot_dict[slot_code]

            log.debug(f"pause SLOT_CODE_SET_FOR_DEBUG={SLOT_CODE_SET_FOR_DEBUG}")
        self.time_slot_dict[slot_code] = slot

        if slot_code in SLOT_CODE_SET_FOR_DEBUG:
            log.debug(f"pause SLOT_CODE_SET_FOR_DEBUG={SLOT_CODE_SET_FOR_DEBUG}")

        if (
            (slot.worker_id == 1145)
            & (int(slot.start_minutes) == 10910)
            & (int(slot.end_minutes) == 11880)
        ):
            print("pause 1145/10910/11880/F ")

        self._set_into_internal_cache(slot_code, slot)
        return self.r.set(slot_code, json.dumps(slot, cls=TimeSlotJSONEncoder))

    def delete_slots_from_worker(self, worker_code: str, start_minutes: int, end_minutes: int):
        assert False

        (interval_begin, interval_end) = self.get_interval_begin_end_by_worker_code(
            worker_code, start_minutes, end_minutes
        )
        existing_slots = self.time_slot_tree[interval_begin:interval_end]
        # slots_to_delete = []
        all_slot_codes_to_delete = {
            self.get_time_slot_key(an_existing_slot[2]) for an_existing_slot in existing_slots
        }
        for an_existing_slot in existing_slots:
            slot_code = self.get_time_slot_key(an_existing_slot[2])
            # if slot_code in self.time_slot_dict.keys():
            if self.time_slot_dict[slot_code].next_slot_code is not None:
                if self.time_slot_dict[slot_code].next_slot_code not in all_slot_codes_to_delete:
                    log.error(
                        f"The slot {slot_code} is deleted with dangling next slot: {self.time_slot_dict[slot_code].next_slot_code}. It shouldnot happend? I am fixing it anyway."
                    )
                    next_slot_as_list_str = self.r.get(
                        self.time_slot_dict[slot_code].next_slot_code
                    )
                    if next_slot_as_list_str is not None:
                        next_slot = WorkingTimeSlot(*json.loads(next_slot_as_list_str))
                        next_slot.prev_slot_code = None
                        with self.r.pipeline() as pipe:
                            self.atomic_slot_delete_and_add_back(
                                redis_handler=pipe,
                                slots_to_delete=[],
                                slots_to_add_back={
                                    self.time_slot_dict[slot_code].next_slot_code: next_slot
                                },
                            )
                    else:
                        log.error(
                            f"The next slot: {self.time_slot_dict[slot_code].next_slot_code} is lost."
                        )

        for an_existing_slot in existing_slots:
            slot_code = self.get_time_slot_key(an_existing_slot[2])
            if slot_code in self.time_slot_dict.keys():
                del self.time_slot_dict[slot_code]
            else:
                log.error(f"Slot mismatch from time_slot_tree to time_slot_dict {slot_code} ")
            # TODO, @duan, really works?
            self.time_slot_tree.remove(an_existing_slot)

            if slot_code in config.DEBUGGING_SLOT_CODE_SET:
                log.debug("config ")

            self.r.delete(slot_code)
            # slots_to_delete.append(slot_code)

        self.env.kafka_server.post_changed_slot_codes(
            message_type=KafkaMessageType.DELETE_WORKING_TIME_SLOTS,
            changed_slot_codes_list=all_slot_codes_to_delete,
        )

    def get_integer_id_for_slot(
        self, worker_code, start_minutes, job_seq
    ) -> int:
        worker_index = self.env.workers_dict[worker_code].worker_index
        slot_index = (worker_index * MAX_MINUTES_PER_TECH + int(start_minutes)) * \
            MAX_JOBS_IN_ONE_SLOT + int(job_seq)
        return slot_index

    def get_interval_begin_end_by_worker_code(
        self, worker_code, start_minutes, end_minutes
    ) -> (int, int):
        worker_index = self.env.workers_dict[worker_code].worker_index
        interval_begin = worker_index * MAX_MINUTES_PER_TECH + int(start_minutes)
        interval_end = worker_index * MAX_MINUTES_PER_TECH + int(end_minutes)
        return (interval_begin, interval_end)

    def _decode_slot_code_info(self, slot_code):
        s = slot_code.split("/")[2].split("_")
        return s[0], int(s[1]), int(s[2])

    def _remove_slot_code_from_internal_cache(self, slot_code):

        if slot_code in self.time_slot_dict.keys():
            del self.time_slot_dict[slot_code]

        worker_code, start_minutes, end_minutes = self._decode_slot_code_info(slot_code)

        (interval_begin, interval_end) = self.get_interval_begin_end_by_worker_code(
            worker_code, start_minutes, end_minutes
        )

        intervals = self.time_slot_tree[interval_begin:interval_end]
        for iv in intervals:
            if (iv.begin == interval_begin) and (iv.end == interval_end):
                log.info(
                    f"slot removed from interval_tree: {worker_code}_{start_minutes}_{end_minutes}"
                )
                # Delete only by exact match. Not the overlapped ones
                self.time_slot_tree.remove(iv)

    def _set_into_internal_cache(self, slot_code, slot):
        if slot_code in SLOT_CODE_SET_FOR_DEBUG:
            log.debug(f"pause SLOT_CODE_SET_FOR_DEBUG={SLOT_CODE_SET_FOR_DEBUG}")
        self.time_slot_dict[slot_code] = slot
        (interval_begin, interval_end) = self.get_interval_begin_end_by_worker_code(
            slot.worker_id,
            slot.start_minutes - slot.start_overtime_minutes,
            slot.end_minutes + slot.end_overtime_minutes,
        )

        existing_slots = self.time_slot_tree[interval_begin:interval_end]
        for an_existing_slot in existing_slots:
            if self.get_time_slot_key(an_existing_slot[2]) == slot_code:
                # If not removed, time_slot_tree will have two entries.
                self.time_slot_tree.remove(an_existing_slot)
        self.time_slot_tree.add(Interval(interval_begin, interval_end, slot))

        worker_code, start_minutes, _ = self._decode_slot_code_info(slot_code)

        worker_index = self.env.workers_dict[worker_code].worker_index
        log.info(f"worker_code = {worker_code}, worker_index = {worker_index}")

        slot_index_id = self.get_integer_id_for_slot(
            worker_code=worker_code, start_minutes=start_minutes, job_seq=0)

        self.rtree_index.insert(
            id=slot_index_id,
            coordinates=(
                slot.start_location.geo_longitude,
                slot.start_location.geo_longitude,
                slot.start_location.geo_latitude,
                slot.start_location.geo_latitude,
                start_minutes,
                start_minutes,
                worker_index,
                worker_index
            ),
            obj=slot_code
        )

        current_start_minutes = start_minutes
        for j_i, jc in enumerate(slot.assigned_job_codes):
            job = self.env.jobs_dict[jc]
            job_start = job.scheduled_start_minutes + job.scheduled_duration_minutes
            if job_start < current_start_minutes:
                log.warn(f"Wrong job seq")
                job_start = current_start_minutes
            self.rtree_index.insert(
                id=slot_index_id + j_i + 1,
                coordinates=(
                    job.location.geo_longitude,
                    job.location.geo_longitude,
                    job.location.geo_latitude,
                    job.location.geo_latitude,
                    current_start_minutes,
                    job_start,
                    worker_index,
                    worker_index
                ),
                obj=slot_code
            )
            current_start_minutes = job.scheduled_start_minutes + job.scheduled_duration_minutes

    def release_job_time_slots(self, job: BaseJob) -> Tuple[bool, dict]:
        """
        action_dict -> action_type: 'JOB_FS' , 'JOB_N', JobType.ABSENCE
        """
        # action_type = action_dict["action_type"]
        job_code = job.job_code
        start_minutes = job.scheduled_start_minutes
        duration_minutes = job.scheduled_duration_minutes
        end_minutes = start_minutes + duration_minutes

        action_worker_ids = job.scheduled_worker_codes
        if len(action_worker_ids) < 1:
            return False, {}
        pipe = None

        if True:
            if True:
                error_occurred = False
                error_messages = []
                for worker_id in action_worker_ids:
                    the_slots = self.get_overlapped_slots(
                        worker_id=worker_id,
                        start_minutes=start_minutes,
                        end_minutes=end_minutes,
                    )
                    if len(the_slots) < 1:
                        log.info(
                            f"release_job_time_slots: no slots to release, worker={worker_id}, start={start_minutes}, job_code={job_code}"
                        )
                        return (
                            False,
                            {
                                "messages": [
                                    {"message": f"no slots to release, worker_id={worker_id}"}
                                ]
                            },
                        )
                    elif len(the_slots) > 1:
                        # there are multiple slots matching this job duration. It means confliction among several jobs or absence_events.
                        # For long jobs, small urgent request may interrupt it and two jobs are in parallel for a single worker.
                        # The logic is:
                        # - Loop through all slots and find which one is the one to be released
                        # - realse the selected one
                        # -  - and then link this one to prev + next
                        # - Loop through rest of slots, with conflicted jobs, cut off from this new free/movable again.
                        log.error(
                            f"spanning across slots, not possible to release, worker_id={worker_id}, start={start_minutes}, job_code={job_code}, slots = {[self.get_time_slot_key(s) for s in the_slots ]}"
                        )
                        return (
                            False,
                            {
                                "messages": [
                                    {
                                        "message": f"spanning across slots, not possible to release, worker_id={worker_id}, start={start_minutes}"
                                    }
                                ]
                            },
                        )
                    local_slot = the_slots.pop()
                    slot_code = self.get_time_slot_key(local_slot)
                    slot = self.get_slot(redis_handler=pipe, slot_code=slot_code)
                    if slot.slot_type == TimeSlotType.FLOATING:
                        try:
                            slot.assigned_job_codes.remove(job_code)
                        except ValueError:
                            log.info(
                                f"JOB:{job_code}:release_job_time_slots: {job_code} is not in slot. slot_code={slot_code} "
                            )
                            return (
                                True,
                                {
                                    "messages": [
                                        {
                                            "message": f"error, {job_code} is not in slot. slot_code={slot_code} ",
                                            "deleted": 0,
                                            "added": 0,
                                        }
                                    ]
                                },
                            )

                        new_slot = slot
                        # now we can put the pipeline back into buffered mode with MULTI
                        self.atomic_slot_delete_and_add_back(
                            redis_handler=pipe,
                            slots_to_delete=[],
                            slots_to_add_back={slot_code: new_slot},
                        )
                        # if a WatchError wasn't raised during execution, everything
                        # we just did happened atomically.
                        return (
                            True,
                            {
                                "messages": [
                                    {
                                        "message": "success",
                                        "deleted": 0,
                                        "added": 1,
                                    }
                                ]
                            },
                        )
                        # This is updating existing floating slot, but to remove one slot does not change recommedation.
                        # I skip updating recommendation slot.
                    else:
                        if job.job_code not in slot.assigned_job_codes:
                            return (
                                True,
                                {
                                    "messages": [
                                        {
                                            "message": "The ",
                                            "deleted": -1,
                                            "added": -1,
                                        }
                                    ]
                                },
                            )
                        if len(slot.assigned_job_codes) > 1:
                            slot.assigned_job_codes.remove(job_code)
                            self.atomic_slot_delete_and_add_back(
                                redis_handler=pipe,
                                slots_to_delete=[],
                                slots_to_add_back={slot_code: slot},
                            )
                            log.warn(
                                f"Multiple job in one JOB_FIXED, and only one {job_code} is removed. slot={str(slot)}"
                            )
                            return (
                                True,
                                {
                                    "messages": [
                                        {
                                            "message": "The ",
                                            "deleted": -1,
                                            "added": -1,
                                        }
                                    ]
                                },
                            )

                        # Now only one job is in this job_fixed slot, I remove this slot completely.
                        result, result_dict = self._release_slot_job_fixed(pipe, slot)
                        if not result:
                            return result, result_dict

                return (
                    True,
                    {
                        "messages": [
                            {
                                "message": "success",
                                "deleted": -1,
                                "added": -1,
                            }
                        ]
                    },
                )

    def _release_slot_job_fixed(self, pipe, slot) -> Tuple[bool, dict]:
        slots_to_delete = []
        slots_to_add_back = {}
        slot_code = self.get_time_slot_key(slot)

        # TODO,  How to release one planned job from multiple conflicted job slot. @duan
        slots_to_delete.append(slot_code)
        new_job_list = []
        new_start_minutes = slot.start_minutes
        new_end_minutes = slot.end_minutes
        new_slot_prev_slot_code = slot.prev_slot_code
        new_slot_next_slot_code = slot.next_slot_code

        new_slot_start_location = slot.start_location
        new_slot_end_location = slot.end_location

        if slot.prev_slot_code is not None:
            prev_slot = self.get_slot(
                redis_handler=pipe, slot_code=slot.prev_slot_code, raise_exception=False
            )
            if prev_slot is None:
                slot.prev_slot_code = None
            else:
                # if prev_slot is None:
                #     log.error(f"Failed to read prev_slot_code={slot.prev_slot_code}. During release_job_time_slots for {job.job_code}")
                #     return ( False, { "messages": [  {"message":  f"Internal Error, release_job_time_slots for {job.job_code}, failed to read slot_code={slot.prev_slot_code}"  }]}, )
                # prev_2nd_slot_code = prev_slot.prev_slot_code
                if prev_slot.slot_type == TimeSlotType.FLOATING:
                    # maximum i merge only one free on left, same as right
                    slots_to_delete.append(slot.prev_slot_code)
                    new_job_list += prev_slot.assigned_job_codes
                    new_start_minutes = prev_slot.start_minutes
                    new_slot_prev_slot_code = prev_slot.prev_slot_code
                    new_slot_start_location = prev_slot.start_location

        if slot.next_slot_code is not None:
            next_slot = self.get_slot(
                redis_handler=pipe, slot_code=slot.next_slot_code, raise_exception=False
            )
            # if next_slot is None:
            #     log.error(f"Failed to read next_slot_code={slot.next_slot_code}. During release_job_time_slots for {job.job_code}")
            #     return ( False, { "messages": [  {"message":  f"Internal Error, release_job_time_slots for {job.job_code}, failed to read slot_code={slot.next_slot_code}"  }]}, )
            if next_slot is None:
                slot.next_slot_code = None
            else:
                if next_slot.slot_type == TimeSlotType.FLOATING:
                    # maximum i merge only one free on right
                    slots_to_delete.append(slot.next_slot_code)
                    new_job_list += next_slot.assigned_job_codes
                    new_end_minutes = next_slot.end_minutes
                    new_slot_next_slot_code = next_slot.next_slot_code
                    new_slot_end_location = next_slot.end_location

        new_slot = WorkingTimeSlot(
            slot_type=TimeSlotType.FLOATING,
            start_minutes=new_start_minutes,
            end_minutes=new_end_minutes,
            prev_slot_code=new_slot_prev_slot_code,
            next_slot_code=new_slot_next_slot_code,
            start_location=new_slot_start_location,
            end_location=new_slot_end_location,
            worker_id=slot.worker_id,
            available_free_minutes=new_end_minutes - new_start_minutes + 1,
            assigned_job_codes=new_job_list,
        )
        new_slot_code = self.get_time_slot_key(new_slot)

        # Link up the new slot to its previous and next slot
        # This should happen after we have merged its prev and next floating slots.
        # prev_2nd_slot_as_list could be same as prev_slot_code if the previous one is job slot. I still have to update its next_node code.
        if new_slot.prev_slot_code is not None:  # Not none, link further to prev.next_slot_code.
            affect_prev_2nd_slot = self.get_slot(
                redis_handler=pipe, slot_code=new_slot.prev_slot_code, raise_exception=False
            )

            if affect_prev_2nd_slot is None:
                new_slot.prev_slot_code = None
            else:
                affect_prev_2nd_slot.next_slot_code = new_slot_code
                slots_to_add_back[new_slot.prev_slot_code] = affect_prev_2nd_slot

        if new_slot.next_slot_code is not None:
            affect_next_2nd_slot = self.get_slot(
                redis_handler=pipe, slot_code=new_slot.next_slot_code, raise_exception=False
            )
            if affect_next_2nd_slot is None:
                new_slot.next_slot_code = None
            else:
                affect_next_2nd_slot.prev_slot_code = new_slot_code
                slots_to_add_back[new_slot.next_slot_code] = affect_next_2nd_slot
        if new_slot.start_minutes >= new_slot.end_minutes:
            log.error(
                f"invalid slot generated and will be skippped., slot_code = {new_slot_code}, slot = {new_slot}"
            )
        else:
            slots_to_add_back[new_slot_code] = new_slot

        # This is updating existing floating slot, but to remove one slot does not change recommedation.
        # I skip updating recommendation slot.

        # now we can put the pipeline back into buffered mode with MULTI
        self.atomic_slot_delete_and_add_back(
            redis_handler=pipe,
            slots_to_delete=slots_to_delete,
            slots_to_add_back=slots_to_add_back,
        )
        # if a WatchError wasn't raised during execution, everything
        # we just did happened atomically.
        return (
            True,
            {
                "messages": [
                    {
                        "message": "success",
                        "deleted": len(slots_to_delete),
                        "added": len(slots_to_add_back),
                    }
                ]
            },
        )

    def cut_off_time_slots(self, action_dict: ActionDict, probe_only=False) -> Tuple[bool, dict]:
        """
        action_dict -> action_type: 'JOB_FS' , 'JOB_N',
        """
        job_code = action_dict.job_code
        start_minutes = action_dict.scheduled_start_minutes
        duration_minutes = action_dict.scheduled_duration_minutes
        end_minutes = start_minutes + duration_minutes

        action_worker_ids = action_dict.scheduled_worker_codes
        the_job = self.env.jobs_dict[action_dict.job_code]
        # the_job_type = the_job.job_type

        if job_code in config.DEBUGGING_JOB_CODE_SET:
            log.debug(f"Debug: cut off {config.DEBUGGING_JOB_CODE_SET} ")
        # https://redis-py-doc.readthedocs.io/en/2.7.0/README.html#pipelines
        pipe = None
        if True:
            if True:
                if True:
                    slots_to_delete = []
                    slots_to_add_back = {}
                    # put a WATCH on each job_code
                    error_occurred = False
                    error_messages = []
                    for worker_id in action_worker_ids:

                        the_slots = self.get_overlapped_slots(
                            worker_id=worker_id,
                            start_minutes=start_minutes,
                            end_minutes=end_minutes,
                        )
                        if len(the_slots) < 1:

                            if action_dict.is_forced_action:
                                # Very likely it is an weekend/night overtime, I will create a J- slot out of nowwhere...  like  "MY|D|03004640|1|PESTS|1|113"
                                self.create_JOB_FIXED_time_slot_for_forced_action(
                                    worker_code=worker_id, action_dict=action_dict
                                )
                                continue
                            else:
                                log.warn(
                                    f"JOB:{job_code}:cut_off_time_slots: no slots to cut from, worker={worker_id}, start={start_minutes}"
                                )
                                return (
                                    False,
                                    {
                                        "messages": [
                                            {
                                                "message": f"JOB:{job_code}:WORKER:{worker_id}: No working slot matched this request. Rejected as not forced action."
                                            }
                                        ]
                                    },
                                )

                        elif len(the_slots) > 1:
                            # very likely, multiple jobs are conflicted in certain timeslots. I should report to the business
                            # Maybe report it by one kafka message? KafkaEnvMessage.

                            if action_dict.is_forced_action:
                                # At least Two visits are overlapping, Here i try to merge them into one visit.
                                if (
                                    the_job.job_type
                                    in (
                                        JobType.APPOINTMENT,
                                        JobType.ABSENCE,
                                    )
                                ) | (the_job.planning_status == JobPlanningStatus.PLANNED):
                                    # - Find the overlapping Working visit and merge into it.
                                    # - I assume there should be only 1 job_fixed.
                                    # self.create_JOB_FIXED_time_slot_for_forced_action(
                                    #     worker_code=worker_id, action_dict=action_dict
                                    # )
                                    error_occurred = error_occurred or (
                                        self._cut_off_fixed_job_from_multiple_slots(
                                            the_slots=the_slots,
                                            the_job=the_job,
                                            action_dict=action_dict,
                                            slots_to_delete=slots_to_delete,
                                            slots_to_add_back=slots_to_add_back,
                                            pipe=pipe,
                                            error_messages=error_messages,
                                        )
                                    )
                                    log.warn(
                                        f"ACTION:{str(action_dict)}:One job request is spanning across slots. It is enforced for now since is_forced_action == True."
                                    )
                                    continue  # To next worker

                            # Even if in forced action, in-planning jobs are also rejected for now. # TODO, @duan 2020-11-23 15:49:23
                            log.error(
                                f"One job request is spanning across slots. Most likely this is due to conflictions. action = {str(action_dict)}, slots={str([(s.slot_type, s.start_minutes, s.assigned_job_codes, s.end_minutes) for s in the_slots])}"
                            )
                            # matched slot jobs:{s.assigned_job_codes}:

                            return (
                                False,
                                {
                                    "messages": [
                                        {
                                            "message": f"One job request is spanning across slots. action = {str(action_dict)}, slots={str([(s.slot_type, s.start_minutes, s.assigned_job_codes, s.end_minutes) for s in the_slots])}"
                                        }
                                    ]
                                },
                            )

                        else:  # len(the_slots) == 1:
                            local_slot = the_slots.pop()
                            slot_code = self.get_time_slot_key(local_slot)
                            slot = local_slot
                            if job_code in slot.assigned_job_codes:
                                log.warn(
                                    f"cut_off_time_slots: while trying to add floating job, the slot={slot_code} already contains this job code={job_code}"
                                )
                                return (
                                    True,  # I consider this as OK, then the_job.schedule_start_minutes will indicate true start value
                                    {
                                        "messages": [
                                            {
                                                "message": f"cut_off_time_slots: the slot={slot_code} already contains this job code={job_code}"
                                            }
                                        ]
                                    },
                                )

                            if slot.slot_type == TimeSlotType.FLOATING:
                                error_occurred = error_occurred or (
                                    self._cut_off_fixed_job_from_single_floating_slot(
                                        slot=slot,
                                        the_job=the_job,
                                        action_dict=action_dict,
                                        slots_to_delete=slots_to_delete,
                                        slots_to_add_back=slots_to_add_back,
                                        pipe=pipe,
                                        error_messages=error_messages,
                                    )
                                )
                            else:
                                # Because I matched only 1 job_fixed slot, the new job is a subset of the matched timeslot. I simply attach the job code to current period.
                                # The start time is also later than the existing job_code.
                                if action_dict.is_forced_action:
                                    log.warn(
                                        f"The only matched slot is not free/movable, but is_forced_action == True. Current job_code={job_code}, matched slot has {slot.assigned_job_codes}, matched slot_code={slot_code},  worker={worker_id}, start={start_minutes}. "
                                    )
                                    slot.assigned_job_codes.append(the_job.job_code)
                                    slots_to_add_back[slot_code] = slot
                                    continue
                                else:
                                    log.error(
                                        f"The only matched slot is not free/movable. This normally means another conflicted visit. Current job_code={job_code}, matched slot has {slot.assigned_job_codes}, matched slot_code={slot_code},  worker={worker_id}, start={start_minutes}, "
                                    )
                                    return (
                                        False,
                                        {
                                            "messages": [
                                                {"message": f"no slots, worker_id={worker_id}"}
                                            ]
                                        },
                                    )

                        if error_occurred:
                            if action_dict.is_forced_action:
                                log.warn(f"REPLAY_ERROR: {str(error_messages)}")
                            else:
                                return False, {"messages": error_messages}
                    # now we can put the pipeline back into buffered mode with MULTI
                    if probe_only:
                        return (not error_occurred, error_messages)
                    self.atomic_slot_delete_and_add_back(
                        redis_handler=pipe,
                        slots_to_delete=slots_to_delete,
                        slots_to_add_back=slots_to_add_back,
                    )

                    return (
                        True,
                        {
                            "messages": [
                                {
                                    "message": "success",
                                    "deleted": len(slots_to_delete),
                                    "added": len(slots_to_add_back),
                                }
                            ]
                        },
                    )

    def get_overlapped_job_codes(self, worker_id, start_minutes, end_minutes):
        # (interval_begin, interval_end) = self.get_interval_begin_end_by_worker_code(
        #     worker_id, start_minutes, end_minutes
        # )
        # slots = self.time_slot_tree[interval_begin:interval_end]
        over_slots = self.get_overlapped_slots(worker_id, start_minutes, end_minutes)

        overlapped_jobs = []
        for slot in over_slots:
            if slot.slot_type != TimeSlotType.ABSENCE:  # F or J

                # TODO, this is duplicated with job_code_sanity_ check 2020-12-18 15:57:55
                for job_code in slot.assigned_job_codes:
                    if job_code not in self.env.jobs_dict.keys():
                        # TODO @duan
                        log.error(
                            f"Non existing job = {job_code} identified. Please consider deleting it"
                        )
                        # raise ValueError("TEMP")
                        continue
                    overlapped_jobs.append(job_code)
            else:
                pass
                # overlapped_jobs.append(slot.referred_object_code)
        return overlapped_jobs

    def get_overlapped_slots_4d_duocylinder(self, geo_center, geo_radius, time_worker_box):
        query_box = (
            geo_center.geo_longitude - geo_radius,
            geo_center.geo_longitude + geo_radius,
            geo_center.geo_latitude - geo_radius,
            geo_center.geo_latitude + geo_radius,
        ) + time_worker_box
        hits = self.rtree_index.intersection(query_box, objects=True)

        # Remove duplicated.
        slots = sorted(list(set([s.object for s in hits])))

        return slots

    def get_overlapped_slots(self, worker_id, start_minutes, end_minutes):
        (interval_begin, interval_end) = self.get_interval_begin_end_by_worker_code(
            worker_id, start_minutes, end_minutes
        )
        slots = self.time_slot_tree[interval_begin:interval_end]

        # this is temp fix
        # Do a sanity check over all slots and their job codes and make sure that they are not dangling codes.
        all_slots = []
        for slot in slots:
            a_slot = self.job_code_sanity_check(slot.data)
            if a_slot is not None:
                all_slots.append(a_slot)

        return all_slots

    def job_code_sanity_check(self, slot):
        return slot

        new_jobs_codes = []
        found_dangling_job = False
        for job_code in slot.assigned_job_codes:
            if job_code not in self.env.jobs_dict.keys():
                log.error(
                    f"job_code_sanity_check: Found dangling job_code = {job_code}, trying to remove. key={self.get_time_slot_key(slot)}, slot={str(slot)} "
                )
                found_dangling_job = True
            else:
                new_jobs_codes.append(job_code)

        if (slot.slot_type == TimeSlotType.JOB_FIXED) & (len(new_jobs_codes) < 1):
            log.error(
                f"slot_code = {self.get_time_slot_key(slot)}, len(a_slot.assigned_job_codes) < 1. I will release this slot"
            )
            with self.r.pipeline() as p:
                self._release_slot_job_fixed(pipe=p, slot=slot)
            return None

        if found_dangling_job:
            slot.assigned_job_codes = new_jobs_codes
            self.atomic_slot_delete_and_add_back(
                redis_handler=self.r.pipeline(),
                slots_to_delete=[],
                slots_to_add_back={self.get_time_slot_key(slot): slot},
            )
            log.info(
                f"job_code_sanity_check: Removed dangling job_code = {job_code}. key={self.get_time_slot_key(slot)}."
            )

        return slot

    def remove_overlapped_slots(self, original_slots: set, rejected_slots: set) -> set:
        if len(rejected_slots) < 1:
            return original_slots
        new_slot_tree = IntervalTree([Interval(sl[0], sl[1], sl) for sl in original_slots])
        for r_slot in rejected_slots:
            for r_interval in new_slot_tree[r_slot[0]: r_slot[1]]:
                new_slot_tree.remove(r_interval)  # Interval(r_slot[0], r_slot[1], r_slot)

        return set(new_slot_tree)

    def atomic_slot_delete_and_add_back(self, redis_handler, slots_to_delete, slots_to_add_back):

        for slot_code in slots_to_delete:
            if slot_code in self.time_slot_dict.keys():
                slot = self.time_slot_dict[slot_code]

                (interval_begin, interval_end) = self.get_interval_begin_end_by_worker_code(
                    slot.worker_id, slot.start_minutes, slot.end_minutes
                )
                try:
                    self.time_slot_tree.remove(Interval(interval_begin, interval_end, slot))
                except ValueError as ve:
                    print(ve)
                    log.error(
                        f"failed to remove from local time_slot_tree. missing slot_code={slot_code}"
                    )

                del self.time_slot_dict[slot_code]
            else:
                # TODO, duan. temp fix.
                log.warn(
                    f"Failed to delete from local dict cache, slot_code = {slot_code}. Instead, i remove overlapped with "
                )
                for s_code, s in slots_to_add_back.items():
                    (interval_begin, interval_end) = self.get_interval_begin_end_by_worker_code(
                        s.worker_id, s.start_minutes, s.end_minutes
                    )
                    for inter_s in self.time_slot_tree[interval_begin:interval_end]:
                        self.time_slot_tree.remove(inter_s)

        for slot_code in slots_to_add_back:
            if slot_code in SLOT_CODE_SET_FOR_DEBUG:
                log.debug(f"pause SLOT_CODE_SET_FOR_DEBUG={SLOT_CODE_SET_FOR_DEBUG}")
            slot_to_add = slots_to_add_back[slot_code]
            # slot_to_add.assigned_job_codes = sorted(
            #     slot_to_add.assigned_job_codes, key=lambda x: self.env.jobs_dict[x].scheduled_start_minutes)

            self._set_into_internal_cache(slot_code, slot_to_add)

    def _cut_off_fixed_job_from_single_floating_slot(
        self,
        slot,
        the_job,
        action_dict: ActionDict,
        slots_to_delete,
        slots_to_add_back,
        pipe,
        error_messages,
    ) -> bool:

        start_minutes = action_dict.scheduled_start_minutes
        duration_minutes = action_dict.scheduled_duration_minutes
        end_minutes = start_minutes + duration_minutes

        slot_code = self.get_time_slot_key(slot)
        if slot_code in config.DEBUGGING_SLOT_CODE_SET:
            log.debug("debug _cut_off_fixed_job_from_single_floating_slot_")

        if the_job.job_code in config.DEBUGGING_JOB_CODE_SET:
            log.debug("debug _cut_off_fixed_job_from_single_floating_slot__ DEBUGGING_JOB_CODE_SET")

        current_job_location = JobLocationBase(*the_job.location[0:4])  # the_job.location
        if the_job.job_type == JobType.ABSENCE:
            new_slot_type = TimeSlotType.ABSENCE
        else:
            new_slot_type = TimeSlotType.JOB_FIXED

        new_slot_prev_slot_code = slot.prev_slot_code
        new_slot_next_slot_code = slot.next_slot_code

        new_slot_start_location = slot.start_location
        new_slot_end_location = slot.end_location

        if the_job.job_type == JobType.ABSENCE:
            new_action_location = (
                the_job.location.geo_longitude,
                the_job.location.geo_latitude,
                TimeSlotType.ABSENCE,
            )
        else:
            new_action_location = (
                the_job.location.geo_longitude,
                the_job.location.geo_latitude,
                LocationType.JOB,
            )

        prev_travel_minutes = self.env.travel_router.get_travel_minutes_2locations(
            new_action_location,
            slot.start_location,
        )
        next_travel_minutes = self.env.travel_router.get_travel_minutes_2locations(
            new_action_location,
            slot.end_location,
        )

        error_occurred = False
        # TODO, urgent < mixing jobtype and action type.!!!!
        # 2020-10-28 16:21:46
        if (
            the_job.job_type
            in (
                JobType.APPOINTMENT,
                JobType.ABSENCE,
            )
        ) or (action_dict.action_type == ActionType.JOB_FIXED):
            has_slot_1 = False
            has_slot_3 = False

            slots_to_delete.append(slot_code)
            front_jobs = []
            back_jobs = []
            for job_code in slot.assigned_job_codes:
                if self.env.jobs_dict[job_code].scheduled_start_minutes <= start_minutes:
                    front_jobs.append(job_code)
                else:
                    back_jobs.append(job_code)
            # slot_3_key = slot.next_slot_code

            slot_2 = WorkingTimeSlot(
                start_minutes=start_minutes,
                end_minutes=end_minutes,
                prev_slot_code=slot.prev_slot_code,
                next_slot_code=slot.next_slot_code,
                slot_type=new_slot_type,
                start_location=current_job_location,
                end_location=current_job_location,  # current_slot.start_location,
                assigned_job_codes=[the_job.job_code],
                worker_id=slot.worker_id,
                referred_object_code=None,
            )
            slot_2_key = self.get_time_slot_key(slot_2)
            if slot_2_key == "env_MY_2/s/CT36_07810_07820_J":
                log.debug("Debug releasing 'env_MY_2/s/CT36_07810_07820_J' ")

            if start_minutes + duration_minutes < slot.end_minutes - 1:
                # - next_travel_minutes  # skip 1 minutes leftover.
                # as long as there are minutes, though less than travel time, I still keep the free slot record. Otherwise, it lost track.
                # 3rd, next free slot. Optional
                has_slot_3 = True
                slot_3 = WorkingTimeSlot(
                    start_minutes=end_minutes,
                    end_minutes=slot.end_minutes,
                    prev_slot_code=slot_2_key,
                    next_slot_code=slot.next_slot_code,
                    slot_type=TimeSlotType.FLOATING,
                    start_location=current_job_location,
                    end_location=slot.end_location,
                    assigned_job_codes=list(back_jobs),
                    worker_id=slot.worker_id,
                    referred_object_code=None,
                )
                if len(back_jobs) > 0:
                    (
                        prev_travel,
                        next_travel,
                        inside_travel,
                    ) = self.env.get_travel_time_jobs_in_slot(slot_3, back_jobs)
                    demanded_minutes = int(prev_travel + next_travel + sum(inside_travel)) + sum(
                        [self.env.jobs_dict[jc].scheduled_duration_minutes for jc in back_jobs]
                    )
                    if demanded_minutes > slot_3.end_minutes - slot_3.start_minutes:
                        error_occurred = True
                        error_messages.append(
                            {
                                "message": f"not enough travel in back_jobs={back_jobs}, demanding={demanded_minutes} minutes,  slot {self.get_time_slot_key(slot_3)}"
                            }
                        )
                        # return False,
                # else skipped.
                # slot_3.assigned_job_codes = back_jobs
                # slot_3.worker_id = worker_id
                slot_3_key = self.get_time_slot_key(slot_3)
                slots_to_add_back[slot_3_key] = slot_3

                new_slot_next_slot_code = slot_3_key

            else:
                if len(back_jobs) > 0:
                    error_occurred = True
                    error_messages.append(
                        {
                            "message": f"back_jobs={back_jobs}  are pushed out without slot_3 in slot {slot_code}"
                        }
                    )

            # - prev_travel_minutes, even if no sufficient travel, the free slot is created to track the place.
            if start_minutes > slot.start_minutes + 1:
                has_slot_1 = True
                slot_1 = WorkingTimeSlot(
                    start_minutes=slot.start_minutes,
                    end_minutes=start_minutes,
                    prev_slot_code=slot.prev_slot_code,
                    next_slot_code=slot_2_key,
                    slot_type=TimeSlotType.FLOATING,
                    start_location=slot.start_location,
                    end_location=current_job_location,
                    assigned_job_codes=front_jobs,
                    worker_id=slot.worker_id,
                )
                if len(front_jobs) > 0:
                    (
                        prev_travel,
                        next_travel,
                        inside_travel,
                    ) = self.env.get_travel_time_jobs_in_slot(slot_1, front_jobs)
                    demanded_minutes = int(prev_travel + next_travel + sum(inside_travel)) + sum(
                        [self.env.jobs_dict[jc].scheduled_duration_minutes for jc in front_jobs]
                    )
                    if demanded_minutes > slot_1.end_minutes - slot_1.start_minutes:
                        error_occurred = True
                        error_messages.append(
                            {
                                "message": f"not enough travel time for front_jobs={front_jobs}, demanding={demanded_minutes} minutes, in slot {self.get_time_slot_key(slot_1)}"
                            }
                        )
                    # front_jobs.available_free_minutes =

                slot_1_key = self.get_time_slot_key(slot_1)
                slots_to_add_back[slot_1_key] = slot_1

                new_slot_prev_slot_code = slot_1_key
            else:
                if len(front_jobs) > 0:
                    error_occurred = True
                    error_messages.append(
                        {"message": f"Front jobs={front_jobs}  are pushed out in slot {slot_code}"}
                    )

            # Now we are ready to link them up, with prev & next
            # slot_2_list = list(slot_2)
            new_slot_code_for_prev_slot = slot_2_key
            new_slot_code_for_next_slot = slot_2_key
            if has_slot_1:
                new_slot_code_for_prev_slot = slot_1_key
                slot_2.prev_slot_code = slot_1_key
            if has_slot_3:
                new_slot_code_for_next_slot = slot_3_key
                slot_2.next_slot_code = slot_3_key

            # slot_2 = WorkingTimeSlot(*slot_2_list)
            slots_to_add_back[slot_2_key] = slot_2

            try:
                if slot.prev_slot_code is not None:
                    affect_prev_slot = self.get_slot(
                        redis_handler=pipe, slot_code=slot.prev_slot_code
                    )
                    affect_prev_slot.next_slot_code = new_slot_code_for_prev_slot
                    slots_to_add_back[slot.prev_slot_code] = affect_prev_slot

                if slot.next_slot_code is not None:
                    affect_next_slot = self.get_slot(
                        redis_handler=pipe, slot_code=slot.next_slot_code
                    )
                    affect_next_slot.prev_slot_code = new_slot_code_for_next_slot
                    slots_to_add_back[slot.next_slot_code] = affect_next_slot

            except MissingSlotException as mse:
                log.error(
                    f"Failed to read slot_code={mse.slot_code}. During linking prev next in _cut_off_fixed_job_from_single_floating_slot for {the_job.job_code}"
                )
                pass  # For now

        # NOT [JobType.ABSENCE/APPT] Not[ActionType.JOB_FIXED]: then it is flexible (including in-planning job) arrange into existing Floating slots
        else:

            all_jobs = []
            sorted_slot_assigned_job_codes = sorted(
                slot.assigned_job_codes, key=lambda x: self.env.jobs_dict[x].scheduled_start_minutes)

            j_start_i = 0
            for j_i in range(len(sorted_slot_assigned_job_codes)):
                if (
                    self.env.jobs_dict[sorted_slot_assigned_job_codes[j_i]].scheduled_start_minutes
                    <= action_dict.scheduled_start_minutes
                ):
                    all_jobs.append(sorted_slot_assigned_job_codes[j_i])
                    j_start_i = j_i + 1
                else:
                    j_start_i = j_i
                    break
            all_jobs.append(the_job.job_code)

            for j_new_i in range(j_start_i, len(sorted_slot_assigned_job_codes)):
                if (
                    self.env.jobs_dict[sorted_slot_assigned_job_codes[j_new_i]
                                       ].scheduled_start_minutes
                    > action_dict.scheduled_start_minutes
                ):
                    all_jobs.append(sorted_slot_assigned_job_codes[j_new_i])
                else:
                    log.debug(
                        f"Error, wrong scheduled_start_minutes sequence of {sorted_slot_assigned_job_codes} at index  {j_new_i} ")

            all_durations = [self.env.jobs_dict[jc].scheduled_duration_minutes for jc in all_jobs]

            (
                prev_travel,
                next_travel,
                inside_travel,
            ) = self.env.get_travel_time_jobs_in_slot(slot, all_jobs)
            if (
                prev_travel + next_travel + sum(inside_travel) + sum(all_durations)
                > slot.end_minutes - slot.start_minutes
            ):
                error_occurred = True
                error_messages.append({"message": f"not enough travel in slot {slot_code}"})

            if len(set(sorted_slot_assigned_job_codes) - set(all_jobs)) > 0:
                log.error(f"lost jobs: {set(sorted_slot_assigned_job_codes) - set(all_jobs)  }")
            slot.assigned_job_codes = all_jobs
            # slot.assigned_job_codes = all_jobs
            # new_slot = WorkingTimeSlot(*current_slot_as_list)
            slots_to_add_back[slot_code] = slot

            # This is updating existing floating slot, so I re-evaluate the recommendation
            # recommended_slot_update_list.append(slot_code)
            # self.env.recommendation_server.update_recommendation_for_slot_change_deprecated(
            #     slot_code, TimeSlotOperationType.UPDATE
            # )
        return error_occurred

    def _cut_off_fixed_job_from_multiple_slots(
        self,
        the_slots,
        the_job,
        action_dict: ActionDict,
        slots_to_delete,
        slots_to_add_back,
        pipe,
        error_messages,
    ) -> bool:

        if the_job.job_type == JobType.ABSENCE:
            new_slot_type = TimeSlotType.ABSENCE
        else:
            new_slot_type = TimeSlotType.JOB_FIXED

        all_redis_slots_temp = []
        for local_slot in the_slots:  # .data
            slot_code = self.get_time_slot_key(local_slot)
            slot__ = self.get_slot(redis_handler=pipe, slot_code=slot_code, raise_exception=False)
            if slot__ is not None:
                all_redis_slots_temp.append(slot__)
            else:
                return True
        all_redis_slots = sorted(all_redis_slots_temp, key=lambda x: x.start_minutes)
        # working_slots = [s for s in the_slots if s.slot_type != TimeSlotType.FLOATING]
        # floating_slots = [s for s in the_slots if s.slot_type == TimeSlotType.FLOATING]
        has_slot_1 = False
        has_slot_3 = False

        prev_slot_slot_for_all = all_redis_slots[0].prev_slot_code
        next_slot_slot_for_all = all_redis_slots[-1].next_slot_code

        slot_2 = WorkingTimeSlot(
            start_minutes=action_dict.scheduled_start_minutes,
            end_minutes=action_dict.scheduled_start_minutes
            + action_dict.scheduled_duration_minutes,
            prev_slot_code=prev_slot_slot_for_all,
            next_slot_code=next_slot_slot_for_all,
            slot_type=new_slot_type,
            start_location=the_job.location,
            end_location=the_job.location,  # current_slot.start_location,
            assigned_job_codes=[the_job.job_code],
            worker_id=all_redis_slots[0].worker_id,
            referred_object_code=None,
        )

        if (all_redis_slots[0].slot_type == TimeSlotType.FLOATING) & (
            all_redis_slots[0].start_minutes < action_dict.scheduled_start_minutes
        ):
            has_slot_1 = True
            slot_1 = all_redis_slots[0]
            slot_1_key = self.get_time_slot_key(slot_1)
            # Must be true
            if slot_1.end_minutes < action_dict.scheduled_start_minutes:
                log.error("Not possible: slot_1.end_minutes < action_dict.scheduled_start_minutes")
            slots_to_delete.append(slot_1_key)
            slot_1.end_minutes = action_dict.scheduled_start_minutes
            slot_1_key = self.get_time_slot_key(slot_1)

            slot_2.prev_slot_code = slot_1_key
            all_redis_slots.pop(0)

        if (all_redis_slots[-1].slot_type == TimeSlotType.FLOATING) & (
            all_redis_slots[-1].end_minutes
            > action_dict.scheduled_start_minutes + action_dict.scheduled_duration_minutes
        ):
            has_slot_3 = True
            slot_3 = all_redis_slots[-1]
            slot_3_key = self.get_time_slot_key(slot_3)
            if (
                slot_3.start_minutes
                > action_dict.scheduled_start_minutes + action_dict.scheduled_duration_minutes
            ):
                log.error(
                    "Not possible: slot_3.start_minutes > action_dict.scheduled_start_minutes + action_dict.scheduled_duration_minutes"
                )

            slots_to_delete.append(slot_3_key)
            slot_3.start_minutes = (
                action_dict.scheduled_start_minutes + action_dict.scheduled_duration_minutes
            )
            slot_3_key = self.get_time_slot_key(slot_3)

            slot_2.next_slot_code = slot_3_key
            all_redis_slots.pop(-1)

        for curr_slot in all_redis_slots:
            if curr_slot.start_minutes < action_dict.scheduled_start_minutes:
                slot_2.start_minutes = curr_slot.start_minutes
                slot_2.assigned_job_codes = curr_slot.assigned_job_codes + slot_2.assigned_job_codes
            else:
                slot_2.assigned_job_codes = slot_2.assigned_job_codes + curr_slot.assigned_job_codes

            if (
                curr_slot.end_minutes
                > action_dict.scheduled_start_minutes + action_dict.scheduled_duration_minutes
            ):
                slot_2.end_minutes = curr_slot.end_minutes

            curr_slot_code = self.get_time_slot_key(curr_slot)
            slots_to_delete.append(curr_slot_code)

        # Now the start and end minutes are fixed.
        slot_2_key = self.get_time_slot_key(slot_2)
        slots_to_add_back[slot_2_key] = slot_2
        # if (slot_2.start_minutes < 0):
        #     log.debug("Error slot_21.start_minutes < 0")

        # if slot_2_key == "env_MY_2/s/CT36_07810_07820_J":
        #     log.debug("Debug cut off 'env_MY_2/s/CT36_07810_07820_J' ")

        # Now we are ready to link them up, with prev & next
        # slot_2_list = list(slot_2)
        new_slot_code_for_prev_slot = slot_2_key
        new_slot_code_for_next_slot = slot_2_key
        if has_slot_1:
            new_slot_code_for_prev_slot = slot_1_key
            slot_2.prev_slot_code = slot_1_key
            slot_1.next_slot_code = slot_2_key
            slots_to_add_back[slot_1_key] = slot_1

            # if (slot_1.start_minutes < 0):
            #     log.debug("Error slot_1.start_minutes < 0")

        if has_slot_3:
            new_slot_code_for_next_slot = slot_3_key
            slot_2.next_slot_code = slot_3_key
            slot_3.prev_slot_code = slot_2_key
            slots_to_add_back[slot_3_key] = slot_3

            # if (slot_3.start_minutes < 0):
            #     log.debug("Error slot_1.start_minutes < 0")

        try:
            if prev_slot_slot_for_all:
                # prev_slot_redis = pipe.get(prev_slot_slot_for_all)
                # affect_prev_slot_as_list = json.loads(prev_slot_redis)
                # affect_prev_slot_as_list[3] = new_slot_code_for_prev_slot
                # affect_prev_slot = WorkingTimeSlot(*affect_prev_slot_as_list)

                affect_prev_slot = self.get_slot(
                    redis_handler=pipe, slot_code=prev_slot_slot_for_all
                )
                affect_prev_slot.next_slot_code = new_slot_code_for_prev_slot
                slots_to_add_back[prev_slot_slot_for_all] = affect_prev_slot

            if next_slot_slot_for_all:
                # next_slot_redis = pipe.get(next_slot_slot_for_all)
                # affect_next_slot_as_list = json.loads(next_slot_redis)
                # affect_next_slot_as_list[2] = new_slot_code_for_next_slot
                # affect_next_slot = WorkingTimeSlot(*affect_next_slot_as_list)

                affect_next_slot = self.get_slot(
                    redis_handler=pipe, slot_code=next_slot_slot_for_all
                )
                affect_next_slot.prev_slot_code = new_slot_code_for_next_slot
                slots_to_add_back[next_slot_slot_for_all] = affect_next_slot
        except MissingSlotException as mse:
            log.error(
                f"Failed to read slot_code={mse.slot_code}. During linking prev next  for {the_job.job_code}"
            )
            pass  # For now

        return False  # error_occurred

    def create_JOB_FIXED_time_slot_for_forced_action(
        self, worker_code: str, action_dict: ActionDict
    ) -> Tuple[bool, dict]:
        start_minutes = action_dict.scheduled_start_minutes
        duration_minutes = action_dict.scheduled_duration_minutes
        end_minutes = start_minutes + duration_minutes

        the_job = self.env.jobs_dict[action_dict.job_code]

        current_job_location_full = self.env.jobs_dict[action_dict.job_code].location

        current_job_location = JobLocationBase(*current_job_location_full[0:4])

        if the_job.job_type == JobType.ABSENCE:
            new_slot_type = TimeSlotType.ABSENCE
        else:
            new_slot_type = TimeSlotType.JOB_FIXED

        slot_2 = WorkingTimeSlot(
            start_minutes=start_minutes,
            end_minutes=end_minutes,
            prev_slot_code=None,
            next_slot_code=None,
            slot_type=new_slot_type,
            start_location=current_job_location,
            end_location=current_job_location,  # current_slot.start_location,
            assigned_job_codes=[action_dict.job_code],
            worker_id=worker_code,
            referred_object_code=None,
            is_in_working_hour=False,
        )
        slot_2_key = self.get_time_slot_key(slot_2)
        slots_to_add_back = {slot_2_key: slot_2}

        # .mset(slots_to_add_back)
        with self.r.pipeline() as pipe:
            self.atomic_slot_delete_and_add_back(
                redis_handler=pipe,
                slots_to_delete=[],
                slots_to_add_back=slots_to_add_back,
            )
        return (
            True,
            {
                "messages": [
                    {
                        "message": f"no working slots at worker_id={worker_code}, but added as job_fixed"
                    }
                ]
            },
        )
