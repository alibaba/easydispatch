from dispatch.plugins.kandbox_planner.util.kandbox_json_util import generic_json_encoder
from dataclasses import asdict as python_asdict
import socket
from dispatch.config import KAFKA_BOOTSTRAP_SERVERS, PLANNER_SERVER_ROLE, TESTING_MODE  #
from dispatch.plugins.kandbox_planner.env.env_models import (
    KafkaEnvMessage,
    Appointment,
    Job,
    Worker,
    JobLocationBase,
)
from dispatch.plugins.kandbox_planner.env.env_enums import (
    KafkaMessageType,
    KafkaRoleType,
    KandboxMessageSourceType,
    KandboxMessageTopicType,
    JobType,
    AppointmentStatus,
)
from kafka import KafkaProducer, KafkaConsumer, TopicPartition
from datetime import datetime
import json
from typing import List
from redis.exceptions import LockError, LockNotOwnedError
import logging
from dispatch import config
import time

import copy

log = logging.getLogger("kandbox_kafka_adapter")


class KafkaAdapter:
    def __init__(
        self,
        role: KafkaRoleType = KafkaRoleType.ENV_ADAPTER,
        env=None,
        team_env_key=None,
    ):
        self.env = env
        if self.env:
            log.info("The kafka is ued for Env")
            self.team_env_key = self.env.team_env_key
        else:
            assert team_env_key is not None
            self.team_env_key = team_env_key

        consumer_timeout_ms = 20
        self.role = role

        if (self.role == KafkaRoleType.ENV_ADAPTER) and (PLANNER_SERVER_ROLE == "recommendation"):
            consumer_timeout_ms = 20  # float("inf")
            self.role = KafkaRoleType.RECOMMENDER

        self.producer = KafkaProducer(
            # value_serializer=lambda m: json.dumps(m).encode("utf-8"),
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS.split(";"),
            # max_request_size=2147483622,
            max_block_ms=60000,
            request_timeout_ms=30000,
        )
        if self.env is not None:
            self.consumer = KafkaConsumer(
                # self.get_env_window_topic_name(),
                # auto_offset_reset="earliest",
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS.split(";"),
                fetch_max_wait_ms=10,
                consumer_timeout_ms=consumer_timeout_ms,
                # max_request_size=214748362220,
            )  #
            self.env_tp = TopicPartition(self.get_env_window_topic_name(), 0)
            self.consumer.assign([self.env_tp])
            self.consumer.seek(self.env_tp, self.env.kafka_input_window_offset)
            log.info(
                f"Initialized env window consumer, topic: { self.get_env_window_topic_name() }, kafka_input_window_offset: { self.env.kafka_input_window_offset },  role = {self.role} "
            )

    def get_env_window_topic_name(self) -> str:
        return f"{KandboxMessageTopicType.ENV_WINDOW}.{self.team_env_key}"

    def get_env_window_out_topic_name(self) -> str:
        return f"{KandboxMessageTopicType.ENV_WINDOW_OUTPUT}.{self.team_env_key}"

    # def get_env_slot_topic_name(self) -> str:
    #     return f"{KandboxMessageTopicType.ENV_SLOT}.{self.team_env_key}"

    def post_message(self, topic_name, m: KafkaEnvMessage):
        """This is used by ENV to post a message
        returns offset.
        """

        msg_dict = python_asdict(m)
        msg = json.dumps(msg_dict, default=generic_json_encoder).encode("utf-8")
        future = self.producer.send(topic_name, value=msg)

        return future.get().offset

    def post_env_message(self, message_type, payload):
        """This is used by ENV to post a message
        returns offset.
        """
        kem = KafkaEnvMessage(
            message_type=message_type,
            message_source_type=KandboxMessageSourceType.ENV,
            message_source_code=self.env.env_inst_code,
            payload=payload,
        )

        return self.post_message(topic_name=self.get_env_window_topic_name(), m=kem)

    def post_env_out_message(self, message_type, payload):
        """This is used by ENV to post a message"""

        m = KafkaEnvMessage(
            message_type=message_type,
            message_source_type=KandboxMessageSourceType.ENV,
            message_source_code=self.env.env_inst_code,
            payload=payload,
        )

        msg_dict = python_asdict(m)
        msg = json.dumps(msg_dict, default=generic_json_encoder).encode("utf-8")

        log.info(f"post_changed_jobs to kafka_out: {msg}")

        self.producer.send(self.get_env_window_out_topic_name(), value=msg)

    def post_refresh_planning_window(self):
        """This is used by ENV to post a message
        2021-05-01 08:37:50, Replaced by post_env_message"""

        self.post_env_message(
            message_type=KafkaMessageType.REFRESH_PLANNING_WINDOW, payload=[{"refresh": True}]
        )
        return

        # m = KafkaEnvMessage(
        #     message_type=KafkaMessageType.REFRESH_PLANNING_WINDOW,
        #     message_source_type=KandboxMessageSourceType.ENV,
        #     message_source_code=self.env.env_inst_code,
        #     payload=[{"refresh": True}],  # any message
        # )

        # msg_dict = python_asdict(m)
        # msg = json.dumps(msg_dict, default=generic_json_encoder).encode("utf-8")

        # return self.producer.send(self.get_env_window_topic_name(), value=msg)

    def post_changed_slot_codes(
        self, message_type: KafkaMessageType, changed_slot_codes_list: List
    ):
        """This is used by ENV to post a message to incidate time slot changes
        2021-05-01 08:37:50, Replaced by post_env_message"""

        if len(changed_slot_codes_list) < 1:
            return False

        self.post_env_message(message_type=message_type, payload=changed_slot_codes_list)
        return True

        # m = KafkaEnvMessage(
        #     message_type=message_type,
        #     message_source_type=KandboxMessageSourceType.ENV,
        #     message_source_code=self.env.env_inst_code,
        #     payload=changed_slot_codes_list,
        # )
        # # m.payload = jobs

        # msg_dict = python_asdict(m)
        # msg = json.dumps(msg_dict, default=generic_json_encoder).encode("utf-8")

        # self.producer.send(self.get_env_slot_topic_name(), value=msg)

        # return

    # def post_jobs_by_codes(self, planner, message_type, job_codes):
    #     """This is used by External Adapter to post any changed objects including workers, jobs to ENV"""
    #     jobs = [
    #         planner.jobs_db_dict[j] for j in job_codes if planner.jobs_db_dict.get(j) is not None
    #     ]

    #     if len(jobs) > 0:
    #         index = 0
    #         step = 20
    #         lens = len(jobs)
    #         print("post_jobs_by_codes: len(jobs)=", len(jobs))

    #         while index * step < lens:
    #             m = KafkaEnvMessage(
    #                 message_type=message_type,
    #                 message_source_type=KandboxMessageSourceType.BATCH_INPUT,
    #                 message_source_code=self.env.env_inst_code,
    #                 payload=jobs[index * step : (index + 1) * step],
    #             )
    #             # m.payload = works

    #             msg_dict = python_asdict(m)
    #             msg = json.dumps(msg_dict, default=generic_json_encoder).encode("utf-8")

    #             future = self.producer.send(self.get_env_window_topic_name(), value=msg)

    #             # added by qiyang to control traffic. Temp fix 2020-11-25 21:01:33
    #             # removed 20210211 to avoid gap between created in db and appt posted after database lookup.
    #             # time.sleep(1)

    #             existing_team = team_service.get(
    #                 db_session=planner.db_session,
    #                 team_id=planner.team_id,
    #             )

    #             team_to_update = TeamUpdate(
    #                 name=existing_team.name,
    #                 code=existing_team.code,
    #                 flex_form_data=existing_team.flex_form_data,
    #                 latest_env_kafka_offset=future.get().offset,
    #             )

    #             new_worker = team_service.update(
    #                 db_session=planner.db_session,
    #                 team_contact=existing_team,
    #                 team_contact_in=team_to_update,
    #             )

    #             index = index + 1

    def post_job(
        self,
        message_source_type=KandboxMessageSourceType.BATCH_INPUT,
        message_source_code="Uknown",
        job=None,
    ) -> int:
        if job is None:
            return
        m = KafkaEnvMessage(
            message_type=message_type,
            message_source_type=KandboxMessageSourceType.BATCH_INPUT,
            message_source_code=message_source_code,
            payload=[job],
        )

        msg_dict = python_asdict(m)
        msg = json.dumps(msg_dict, default=generic_json_encoder).encode("utf-8")
        log.info(f"To post_job env_window_topic: {msg}")

        future = self.producer.send(self.get_env_window_topic_name(), value=msg)
        return future.get().offset

    def post_workers(self, planner, message_type, worker_codes):
        workers = [
            planner.workers_by_email_dict[w]
            for w in worker_codes
            if planner.workers_by_email_dict.get(w) is not None
        ]

        if len(workers) > 0:
            index = 0
            step = 20
            lens = len(workers)

            while index * step < lens:
                m = KafkaEnvMessage(
                    message_type=message_type,
                    message_source_type=KandboxMessageSourceType.BATCH_INPUT,
                    message_source_code=self.env.env_inst_code,
                    payload=workers[index * step: (index + 1) * step],
                )

                # m.payload = works

                msg_dict = python_asdict(m)
                msg = json.dumps(msg_dict, default=generic_json_encoder).encode("utf-8")

                future = self.producer.send(self.get_env_window_topic_name(), value=msg)

                existing_team = team_service.get(
                    db_session=planner.db_session,
                    team_id=planner.team_id,
                )

                team_to_update = TeamUpdate(
                    name=existing_team.name,
                    code=existing_team.code,
                    flex_form_data=existing_team.flex_form_data,
                    latest_env_kafka_offset=future.get().offset,
                )

                new_worker = team_service.update(
                    db_session=planner.db_session,
                    team_contact=existing_team,
                    team_contact_in=team_to_update,
                )

                index = index + 1

    def post_appointments(self, planner, message_type, appointment_codes):
        appointments = [
            planner.pubsub_appointment_db_dict[w]
            for w in appointment_codes
            if planner.pubsub_appointment_db_dict.get(w) is not None
        ]

        if len(appointments) > 0:
            index = 0
            step = 20
            lens = len(appointments)

            while index * step < lens:
                m = KafkaEnvMessage(
                    message_type=message_type,
                    message_source_type=KandboxMessageSourceType.BATCH_INPUT,
                    message_source_code=self.env.env_inst_code,
                    payload=appointments[index * step: (index + 1) * step],
                )

                msg_dict = python_asdict(m)
                msg = json.dumps(msg_dict, default=generic_json_encoder).encode("utf-8")

                future = self.producer.send(self.get_env_window_topic_name(), value=msg)
                existing_team = team_service.get(
                    db_session=planner.db_session,
                    team_id=planner.team_id,
                )

                team_to_update = TeamUpdate(
                    name=existing_team.name,
                    code=existing_team.code,
                    flex_form_data=existing_team.flex_form_data,
                    latest_env_kafka_offset=future.get().offset,
                )

                new_worker = team_service.update(
                    db_session=planner.db_session,
                    team_contact=existing_team,
                    team_contact_in=team_to_update,
                )
                index = index + 1

    def post_appointment(self, planner, message_type, appointment):
        m = KafkaEnvMessage(
            message_type=message_type,
            message_source_type=KandboxMessageSourceType.BATCH_INPUT,
            message_source_code=self.env.env_inst_code,
            payload=[appointment],
        )

        msg_dict = python_asdict(m)
        msg = json.dumps(msg_dict, default=generic_json_encoder).encode("utf-8")

        future = self.producer.send(self.get_env_window_topic_name(), value=msg)
        existing_team = team_service.get(
            db_session=planner.db_session,
            team_id=planner.team_id,
        )

        team_to_update = TeamUpdate(
            name=existing_team.name,
            code=existing_team.code,
            flex_form_data=existing_team.flex_form_data,
            latest_env_kafka_offset=future.get().offset,
        )

        new_worker = team_service.update(
            db_session=planner.db_session,
            team_contact=existing_team,
            team_contact_in=team_to_update,
        )

    def post_abenses(self, planner, message_type, absences_code):
        absences = [
            planner.absence_db_dict[w]
            for w in absences_code
            if planner.absence_db_dict.get(w) is not None
        ]

        if len(absences) > 0:
            index = 0
            step = 20
            lens = len(absences)

            while index * step < lens:
                m = KafkaEnvMessage(
                    message_type=message_type,
                    message_source_type=KandboxMessageSourceType.BATCH_INPUT,
                    message_source_code=self.env.env_inst_code,
                    payload=absences[index * step: (index + 1) * step],
                )

                msg_dict = python_asdict(m)
                msg = json.dumps(msg_dict, default=generic_json_encoder).encode("utf-8")

                future = self.producer.send(self.get_env_window_topic_name(), value=msg)

                existing_team = team_service.get(
                    db_session=planner.db_session,
                    team_id=planner.team_id,
                )

                team_to_update = TeamUpdate(
                    name=existing_team.name,
                    code=existing_team.code,
                    flex_form_data=existing_team.flex_form_data,
                    latest_env_kafka_offset=future.get().offset,
                )

                new_worker = team_service.update(
                    db_session=planner.db_session,
                    team_contact=existing_team,
                    team_contact_in=team_to_update,
                )

                index = index + 1

    def trigger_update_planning_window(self, start_minutes):
        m = KafkaEnvMessage(
            message_type=KafkaMessageType.UPDATE_PLANNING_WINDOW,
            message_source_type=KandboxMessageSourceType.ENV,
            message_source_code=self.env.env_inst_code,
            payload=[{"horizon_start_minutes": start_minutes}],
        )

        msg_dict = python_asdict(m)
        msg = json.dumps(msg_dict, default=generic_json_encoder).encode("utf-8")

        self.producer.send(self.get_env_window_topic_name(), value=msg)

    def trigger_refresh_single_recommendation(self, job_code: str):
        m = KafkaEnvMessage(
            message_type=KafkaMessageType.REFRESH_RECOMMENDATION_SINGLE_APPOINTMENT,
            message_source_type=KandboxMessageSourceType.ENV,
            message_source_code=self.env.env_inst_code,
            payload=[{"job_code": job_code}],
        )

        msg_dict = python_asdict(m)
        msg = json.dumps(msg_dict, default=generic_json_encoder).encode("utf-8")

        self.producer.send(self.get_env_window_topic_name(), value=msg)

    def process_env_out_message(self, msg):
        begin_time = datetime.now()
        try:
            env_message = KafkaEnvMessage(**json.loads(msg.value))
        except:
            log.error(f"process_env_out_message: Unknow message: {msg}")
            return
        print("Not implemented.")

    def process_env_message(self, msg, auto_replay_in_process=True):
        try:
            env_message = KafkaEnvMessage(**json.loads(msg.value))
        except:
            log.error(f"process_env_message: Unknow message: {msg}")
            return
        begin_time = datetime.now()

        def _refresh_planning_window(obj_dict):

            self.env.mutate_refresh_planning_window_from_redis()

        def _update_planning_window(obj_dict):
            # Message should be:
            # { "message_type": "Update_Planning_Window",  "message_source_type": "ENV", "message_source_code": "env_MY_2_8_duanmac15",   "payload": [{"horizon_start_minutes":1441}] }
            if not auto_replay_in_process:
                log.info(
                    f"{datetime.now()} : _update_planning_window skipped since auto_replay_in_process==False"
                )
                return

            try:
                if obj_dict["horizon_start_minutes"] < 0:
                    self.env.horizon_start_minutes = None
                else:
                    self.env.horizon_start_minutes = obj_dict["horizon_start_minutes"]

                    if TESTING_MODE != "yes":
                        log.error(
                            f"Received a testing-only message while TESTING_MODE!=yes: {obj_dict}"
                        )
                        return
            except KeyError:
                log.error(f"_update_planning_window: Wrong message format in {obj_dict}")
                return

            self.env.mutate_extend_planning_window()
            log.info(f"{datetime.now()} : _update_planning_window done. obj_dict = {obj_dict}")

        def _refresh_recommendation(obj_dict):
            # Message should be:
            # { "message_type": "Refresh_Recommendation",  "message_source_type": "ENV", "message_source_code": "env_MY_2_8_duanmac15",   "payload": [{"day_seq":-1}] }

            self.env.recommendation_server.refresh_all_recommendations()

        def _refresh_recommendation_single_appointment(obj_dict):
            # Message should be:
            # {"message_type": "Refresh_Recommendation_Single_Appointment", "message_source_type": "ENV", "message_source_code": "env_MY_2_5_duanmac15", "payload": [{"job_code": "026b7694-f1da-48e1-8324-980665cf45fc"}]}
            try:
                if obj_dict["job_code"] not in self.env.jobs_dict.keys():
                    log.error(
                        f"JOB:{obj_dict['job_code']}: _refresh_recommendation_single_appointment: job does not exist in env",
                    )
                    return
            except KeyError:
                log.error(f"_refresh_recommendation_single_appointment: no job_code in {obj_dict}")
                return

            self.env.recommendation_server.refresh_recommendations_single_appointment(
                job_code=obj_dict["job_code"]
            )

        def _create_job(obj_dict):
            try:
                if obj_dict["code"] in self.env.jobs_dict.keys():
                    log.error(
                        f"JOB:{obj_dict['code']}: _create_job, job already existed",
                    )
                    return
            except KeyError:
                log.error(f"_create_job: keyerror:  no code in {obj_dict}")
                return

            try:
                job = self.env.env_encode_single_job(obj_dict)
                # Lookup right location by location_code saved in the appointment.
                # Save Locaiton object instead of original tuple
                job.location = self.env.locations_dict[job.location.location_code]
            except KeyError:
                log.error("KeyError, can not find location, or worker for job: {}".format(obj_dict["code"]))
                return
            self.env.mutate_create_job(job, auto_replay=auto_replay_in_process)
            return

        def _update_job_metadata(obj_dict):
            try:
                if obj_dict["code"] not in self.env.jobs_dict.keys():
                    log.error(
                        f"JOB:{obj_dict['code']}: _update_job_metadata, job does not exist",
                    )
                    return
            except KeyError:
                log.error(f"_update_job_metadata: no code in {obj_dict}")
                return

            new_job = self.env.env_encode_single_job(obj_dict)
            # Lookup right location by location_code saved in the appointment.
            # Save Locaiton object instead of original tuple
            try:
                new_job.location = self.env.locations_dict[new_job.location.location_code]
            except KeyError:
                log.error(f"can not find location job to _update_job_metadata: {new_job}")
                return

            # curr_job = self.env.jobs_dict[new_job.job_code]
            # to_reschedule = False
            # if (
            #     (curr_job.planning_status != new_job.planning_status)
            #     or (curr_job.scheduled_start_minutes != new_job.scheduled_start_minutes)
            #     or (curr_job.scheduled_worker_codes != new_job.scheduled_worker_codes)
            #     # Duration is determined by scheduled_worker_codes and requested duration.
            # ):
            #     to_reschedule = True

            # to_reschedule should only happen when replay is enabled on this instance. On API, it should not replay, but only to update its job metadata
            # if to_reschedule & auto_replay_in_process:
            #     # TODO, to review, here I assume if to reschedule, i will ignore any metadata changes.
            #     # 2020-11-23 09:33:46
            #     a_dict = self.env.gen_action_dict_from_job(job=new_job, is_forced_action=True)
            #     self.env.mutate_update_job_by_action_dict(a_dict=a_dict, post_changes_flag=False)
            #     log.warn(
            #         f"_update_job_metadata: The planning changes from OSS are detected and applied for job={new_job.job_code} "
            #     )

            _update_job_reschedule(obj_dict)
            self.env.mutate_update_job_metadata(new_job)

        def _update_job_reschedule(obj_dict):  # Reserved for kafka message
            try:
                if obj_dict["code"] not in self.env.jobs_dict.keys():
                    log.error(
                        f"JOB:{obj_dict['code']}: _update_job_reschedule: job does not exist in env",
                    )
                    return
                else:
                    log.info(f"_update_job_reschedule: received job event {obj_dict}")
            except KeyError:
                log.error(f"_update_job_reschedule: no code in {obj_dict}")
                return

            new_job = self.env.env_encode_single_job(obj_dict)

            curr_job = self.env.jobs_dict[new_job.job_code]
            to_reschedule = False
            if (
                (curr_job.planning_status != new_job.planning_status)
                or (curr_job.scheduled_start_minutes != new_job.scheduled_start_minutes)
                or (curr_job.scheduled_worker_codes != new_job.scheduled_worker_codes)
                # Duration is determined by scheduled_worker_codes and requested duration.
            ):
                to_reschedule = True

            if to_reschedule:
                if auto_replay_in_process:
                    a_dict = self.env.gen_action_dict_from_job(job=new_job, is_forced_action=True)
                    self.env.mutate_update_job_by_action_dict(
                        a_dict=a_dict, post_changes_flag=False
                    )
                    log.info(
                        f"_update_job_reschedule: The planning changes from pubsub are detected and applied for job={new_job.job_code}, done with mutate_update_job_by_action_dict"
                    )
                else:
                    curr_job.planning_status = new_job.planning_status
                    curr_job.scheduled_start_minutes = new_job.scheduled_start_minutes
                    curr_job.scheduled_worker_codes = new_job.scheduled_worker_codes
                    curr_job.scheduled_duration_minutes = new_job.scheduled_duration_minutes

                    log.info(
                        f"_update_job_reschedule: not auto_replay_in_process, updated planning info without modifying slots for job={new_job.job_code}"
                    )
            else:
                log.info(
                    f"_update_job_reschedule: no changes are detected for job={new_job.job_code}, skipped from mutate_update_job_by_action_dict"
                )
                return False

        def _refresh_job_reschedule(obj_dict):  # Reserved for kafka message
            try:
                new_job = obj_dict
                job_code = new_job["job_code"]
            except KeyError:
                log.error(f"_refresh_job_reschedule: no job_code in {obj_dict}")
                return

            if job_code not in self.env.jobs_dict.keys():
                log.error(
                    f"JOB:{job_code}: _refresh_job_reschedule: job does not exist in env",
                )
                return
            curr_job = self.env.jobs_dict[job_code]
            curr_job.planning_status = new_job["planning_status"]
            curr_job.scheduled_start_minutes = new_job["scheduled_start_minutes"]
            curr_job.scheduled_worker_codes = new_job["scheduled_worker_codes"]
            curr_job.scheduled_duration_minutes = new_job["scheduled_duration_minutes"]
            log.info(
                f"JOB:{job_code}: _refresh_job_reschedule done, planning_status = {new_job['planning_status']}, scheduled_worker_codes = {new_job['scheduled_worker_codes']},   scheduled_start_minutes = {new_job['scheduled_start_minutes']},  ",
            )

        def _create_appointment(obj_dict):
            # db_appt = AppointmentFromDB(**obj_dict)
            if obj_dict["appointment_code"] in self.env.jobs_dict.keys():
                curr_appt = self.env.jobs_dict[obj_dict["appointment_code"]]
                log.error(
                    f"APPT:{obj_dict['appointment_code']}: mutate_create_appointment, the appointment already exists  with status = {curr_appt.appointment_status}",
                )
                return
            if obj_dict["appointment_code"] in config.DEBUGGING_JOB_CODE_SET:
                print("pause for config.DEBUGGING_JOB_CODE_SET")

            if obj_dict["location_code"] is None:  # included_job_codes is [none]?
                log.error(
                    f"APPT:{obj_dict['appointment_code']}: location_code is None, skipped. ",
                )
                return

            if (
                obj_dict["appointment_status"] != AppointmentStatus.PENDING
            ):  # included_job_codes is [none]?
                log.error(
                    f"APPT:{obj_dict['appointment_code']}: status = {obj_dict['appointment_status']}, not PENDING, skipped. ",
                )
                return

            new_appt = self.env.env_encode_single_appointment(obj_dict)
            if new_appt is None:
                log.error(f"failed to encode appointment to env: {obj_dict}")
                return

            # Lookup right location by location_code saved in the appointment.
            # Save Locaiton object instead of original tuple
            try:
                new_appt.location = self.env.locations_dict[new_appt.location.location_code]
            except KeyError:
                log.error(f"can not find location for appointment: {new_appt.location[3]}")
                return
            self.env.mutate_create_appointment(new_appt, auto_replay=auto_replay_in_process)
            if auto_replay_in_process:
                self.env.recommendation_server.search_for_recommendations(
                    job_code=new_appt.job_code
                )

        def _update_appointment(obj_dict):
            if obj_dict["appointment_code"] not in self.env.jobs_dict.keys():
                log.error(
                    f"APPT:{obj_dict['appointment_code']}: _update_appointment, appt does not exist.",
                )
                return

            if obj_dict["appointment_status"] != AppointmentStatus.PENDING:
                self.env.mutate_delete_appointment(job_code=obj_dict["appointment_code"])
            else:
                log.error(
                    f"APPT:{obj_dict['appointment_code']}: _update_appointment, forbiddended to update with same PENDING status.",
                )
                return

        def _create_absence(obj_dict):
            # db_appt = AppointmentFromDB(**obj_dict)
            if obj_dict["absence_code"] in self.env.jobs_dict.keys():
                log.error(
                    f"ABSENCE:{obj_dict['absence_code']}: the absence_code already exists.",
                )
                return
            if obj_dict["absence_code"] in config.DEBUGGING_JOB_CODE_SET:
                print("pause for config.DEBUGGING_JOB_CODE_SET")

            new_appt = self.env.env_encode_single_absence(obj_dict)
            self.env.mutate_create_worker_absence(new_appt, auto_replay=auto_replay_in_process)

        def _update_absence(obj_dict):
            if obj_dict["absence_code"] not in self.env.jobs_dict.keys():
                log.error(
                    f"ABSENCE:{obj_dict['absence_code']}:  , absence does not exist.",
                )
                return

            log.warn(
                f"ABSENCE:{obj_dict['absence_code']}: _update_ , not implemented.",
            )
            return

        def _create_worker(obj_dict):
            # db_appt = AppointmentFromDB(**obj_dict)
            if obj_dict["code"] in self.env.workers_dict.keys():
                log.error(
                    f"WORKER:{obj_dict['code']}: worker already exists",
                )
                return
            # I assume that when the message arrives here, db already have it.
            self.env.kp_data_adapter.reload_data_from_db()
            new_worker = self.env.env_encode_single_worker(obj_dict)

            self.env.mutate_create_worker(new_worker)

            return

        def _update_worker(obj_dict):
            # db_appt = AppointmentFromDB(**obj_dict)
            if obj_dict["code"] not in self.env.workers_dict.keys():
                log.error(
                    f"WORKER:{obj_dict['code']}: worker does not exist",
                )
                return
            # I assume that when the message arrives here, db already have it.
            new_worker = self.env.env_encode_single_worker(obj_dict)

            self.env.mutate_update_worker(new_worker)

            return

        def _update_worker_attributes(obj_dict):
            # db_appt = AppointmentFromDB(**obj_dict)
            for worker_code in obj_dict:
                if worker_code not in self.env.workers_dict.keys():
                    log.error(
                        f"WORKER:{worker_code}: worker does not exists, can not _update_worker_attributes"
                    )
                    return
                self.env.workers_dict[worker_code].__dict__.update(obj_dict[worker_code])
                log.warn(
                    f"WORKER:{worker_code}: _update_worker_attributes worker updated, {obj_dict[worker_code]} "
                )

        def _set_slots(code_list):
            for slot_code in code_list:
                slot_code_str = slot_code  # .decode("utf-8")
                # if slot_code_str == "env_MY_2/s/MY_D_3_CT05_06865_06895_J":
                #     log.debug("debug")
                self.env.slot_server.get_from_redis_to_internal_cache(slot_code_str)

        def _delete_slots(code_list):

            for slot_code in code_list:
                slot_code_str = slot_code  # .decode("utf-8")
                # if slot_code_str == "env_MY_2/s/MY_D_3_CT05_06865_06895_J":
                #     log.debug("debug")
                self.env.slot_server._remove_slot_code_from_internal_cache(slot_code_str)
                log.debug(f"_delete_slots: {slot_code_str}  is removed from cache...")

        def _invalid_message_type_func(obj_dict):
            log.error("Invalid message_type")
            return
            # raise LookupError("Invalid message_type")

        switcher = {
            KafkaMessageType.CREATE_APPOINTMENT: _create_appointment,
            KafkaMessageType.UPDATE_APPOINTMENT: _update_appointment,
            KafkaMessageType.CREATE_ABSENCE: _create_absence,
            KafkaMessageType.UPDATE_ABSENCE: _update_absence,
            #
            KafkaMessageType.CREATE_WORKER: _create_worker,
            KafkaMessageType.CREATE_JOB: _create_job,
            KafkaMessageType.UPDATE_WORKER: _update_worker,
            KafkaMessageType.UPDATE_JOB: _update_job_metadata,
            KafkaMessageType.RESCHEDULE_JOB: _update_job_reschedule,
            KafkaMessageType.UPDATE_PLANNING_WINDOW: _update_planning_window,
            KafkaMessageType.REFRESH_PLANNING_WINDOW: _refresh_planning_window,
            KafkaMessageType.REFRESH_RECOMMENDATION: _refresh_recommendation,
            KafkaMessageType.REFRESH_RECOMMENDATION_SINGLE_APPOINTMENT: _refresh_recommendation_single_appointment,
            KafkaMessageType.REFRESH_JOB: _refresh_job_reschedule,
            KafkaMessageType.UPDATE_WORKER_ATTRIBUTES: _update_worker_attributes,
            # for slots
            KafkaMessageType.UPDATE_WORKING_TIME_SLOTS: _set_slots,
            KafkaMessageType.DELETE_WORKING_TIME_SLOTS: _delete_slots,
        }
        # Get the function from switcher dictionary
        func = switcher.get(env_message.message_type, _invalid_message_type_func)
        if self.env.env_inst_code == env_message.message_source_code:
            log.warn(
                f"Date: {begin_time}, env_inst_code = {self.env.env_inst_code}, Received and skippted my own env message: {env_message.message_type}, offset = {msg.offset}"
            )
            return
        elif env_message.message_type in {
            KafkaMessageType.UPDATE_PLANNING_WINDOW,
            KafkaMessageType.REFRESH_RECOMMENDATION,
            KafkaMessageType.REFRESH_RECOMMENDATION_SINGLE_APPOINTMENT,
        }:
            if auto_replay_in_process:
                func(env_message.payload[0])
            else:
                log.warn(f"not auto_replay_in_process for message {env_message.message_type}")
        elif env_message.message_type in {
            KafkaMessageType.REFRESH_PLANNING_WINDOW,
        }:
            if not auto_replay_in_process:
                func(env_message.payload[0])
            else:
                log.warn(
                    f"auto_replay_in_process == true (recommender), skipping Message Type = {env_message.message_type}"
                )

        elif env_message.message_type in [
            KafkaMessageType.CREATE_WORKER,
            KafkaMessageType.UPDATE_WORKER,
            KafkaMessageType.REFRESH_JOB,
            KafkaMessageType.UPDATE_WORKER_ATTRIBUTES,
        ]:
            for obj_dict in env_message.payload:
                # Execute the worker_changing function
                func(obj_dict)

        # All those messages are from database or pubsub, and should conform to database structure.
        elif env_message.message_type in [
            KafkaMessageType.CREATE_APPOINTMENT,
            KafkaMessageType.UPDATE_APPOINTMENT,
            KafkaMessageType.CREATE_ABSENCE,
            KafkaMessageType.UPDATE_ABSENCE,
            KafkaMessageType.CREATE_JOB,
            KafkaMessageType.UPDATE_JOB,
            KafkaMessageType.RESCHEDULE_JOB,
        ]:
            for obj_dict in env_message.payload:
                # Job messages
                try:
                    if "scheduled_start_datetime" in obj_dict.keys():
                        if isinstance(obj_dict["scheduled_start_datetime"], str):
                            obj_dict["scheduled_start_datetime"] = datetime.strptime(
                                obj_dict["scheduled_start_datetime"], "%Y-%m-%d %H:%M:%S"
                            )

                    if "requested_start_datetime" in obj_dict.keys():
                        if isinstance(obj_dict["requested_start_datetime"], str):
                            obj_dict["requested_start_datetime"] = datetime.strptime(
                                obj_dict["requested_start_datetime"], "%Y-%m-%d %H:%M:%S"
                            )
                except Exception as e:  # ValueError
                    log.error(
                        f"Error decoding scheduled_start_datetime and requested_start_datetime. The message is skipped. obj_dict= {obj_dict}, error = {str(e)}"
                    )
                    # return
                func(obj_dict)

        elif env_message.message_type in (
            KafkaMessageType.UPDATE_WORKING_TIME_SLOTS,
            KafkaMessageType.DELETE_WORKING_TIME_SLOTS,
        ):

            changed_slot_codes_list = env_message.payload
            if len(changed_slot_codes_list) < 1:
                log.error(f"Skipping empty slot message: {env_message}")
                return False

            # log.debug(f"Received valid slot message: {env_msg_str}")

            return func(changed_slot_codes_list)

        # Return only after loop.
        total_time = datetime.now() - begin_time
        log.debug(
            f"Date: {begin_time}, Elapsed: {total_time}: Received and processed env message: {env_message.message_type}, offset = {msg.offset}, msg.timestamp = {msg.timestamp}"
        )

    def consume_env_messages(self):
        """Main loop for kafka message"""
        # log.info(  "Looking for new env messages in one refresh request:env={}, offset={} ".format(
        #                     self.env.env_inst_code,self.env.kafka_input_window_offset  ) )
        i = 0
        try:
            for msg in self.consumer:
                i += 1
                if i % 20 == 1:  # True:  #
                    log.info(
                        "Received {}-th new env messages in one refresh request:env={}, topic= {}, timestamp= {},partition {}, offset = {}".format(
                            i,
                            self.env.env_inst_code,
                            msg.topic,
                            msg.timestamp,
                            msg.partition,
                            msg.offset,
                        )
                    )

                if self.role == KafkaRoleType.RECOMMENDER:
                    if msg.offset > self.env.get_env_window_replay_till_offset():
                        # auto_replay = True
                        try:
                            # Is this timeout seconds?
                            with self.env.redis_conn.lock(
                                self.env.get_env_replay_lock_redis_key(), timeout=120
                            ) as lock:
                                self.process_env_message(msg, auto_replay_in_process=True)
                                # Commit last offset. Save it into Redis ...
                                self.env.set_env_window_replay_till_offset(msg.offset)
                        except LockNotOwnedError:
                            log.debug(
                                "premature lock expire. This process took longer than 120 seconds"
                            )
                        except LockError as le:
                            # the lock wasn't acquired
                            print("lock error:", le)
                            # log.error("Failed to get lock to replay the env")

                    else:
                        self.process_env_message(msg, auto_replay_in_process=False)

                else:
                    # I will take in the job data, but not to mutate any slot information
                    self.process_env_message(msg, auto_replay_in_process=False)

                self.env.kafka_input_window_offset = msg.offset + 1
        except AssertionError as e:
            print(e)
            log.error(f"AssertionError while trying consume_env_messages")
        # log.info("Finished Looking for new env messages in one refresh request:env={}, offset={} ".format(
        #                     self.env.env_inst_code,self.env.kafka_input_window_offset  )   )
        return

    def consume_env_out_messages(self):
        """Main loop for kafka out message"""
        i = 0
        for msg in self.consumer:
            i += 1
            if i % 20 == 1:  # True:  #
                log.info(
                    "Received {}-th new env messages in one refresh request:env={}, topic= {}, timestamp= {},partition {}, offset = {}".format(
                        i,
                        self.env.env_inst_code,
                        msg.topic,
                        msg.timestamp,
                        msg.partition,
                        msg.offset,
                    )
                )

            curr_offset = int(self.env.redis_conn.get(self.env.get_env_out_kafka_offset_key()))

            if msg.offset > curr_offset:

                self.process_env_out_message(msg)

                # Commit last offset. Save it into Redis ...
                self.env.redis_conn.set(self.env.get_env_out_kafka_offset_key(), msg.offset)

            else:
                log.info(
                    f"message (offset = {msg.offset} > curr_offset = {curr_offset}) is skipped."
                )

        # try:
        # except AssertionError as e:
        #     print(e)
        #     log.error(f"AssertionError while trying consume_env_messages")
        # log.info("Finished Looking for new env messages in one refresh request:env={}, offset={} ".format(
        #                     self.env.env_inst_code,self.env.kafka_input_window_offset  )   )
        return

    def kafka_send_out(self):
        """ Not implemented yet"""
        self.output_consumer = KafkaConsumer(
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS.split(";"),
            fetch_max_wait_ms=10,
            consumer_timeout_ms=20,
        )

        tp = TopicPartition(self.get_env_window_out_topic_name(), 0)

        existing_team = team_service.get_by_code(
            db_session=self.db_adapter.db_session,
            team_id=self.env.config["team_id"],
        )

        if existing_team.latest_env_db_sink_offset is None:
            latest_env_db_sink_offset = 0
        else:
            latest_env_db_sink_offset = existing_team.latest_env_db_sink_offset + 1

        self.output_consumerconsumer.assign([tp])

        self.output_consumer.consumer.seek(tp, latest_env_db_sink_offset)

        while True:
            for msg in consumer:
                m = json.loads(msg.value)

                for j, data in enumerate(m["payload"]):
                    self.change_job(data)

                team_to_update = TeamUpdate(
                    code=existing_team.code,
                    name=existing_team.name,
                    description=existing_team.description,
                    flex_form_data=existing_team.flex_form_data,
                    latest_env_db_sink_offset=msg.offset,
                )

                _ = team_service.update(
                    db_session=self.db_adapter.db_session,
                    team_contact=existing_team,
                    team_contact_in=team_to_update,
                )

            time.sleep(1)
