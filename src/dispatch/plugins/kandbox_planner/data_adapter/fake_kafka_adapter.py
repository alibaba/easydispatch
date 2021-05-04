from datetime import datetime
import json
from typing import List
from redis.exceptions import LockError, LockNotOwnedError
import logging
from dispatch import  config
import time

import copy

log = logging.getLogger("kandbox_kafka_adapter")

from kafka import KafkaProducer, KafkaConsumer, TopicPartition

from dispatch.plugins.kandbox_planner.env.env_enums import (
    KafkaMessageType,
    KandboxMessageSourceType,
    KandboxMessageTopicType,
    JobType,
    AppointmentStatus,
)

# MIN_RECOMMENDATION_COUNT = 5
# MAX_RECOMMENDATION_COUNT = 20
# TRIM_RECOMMENDATION_COUNT = 10


from dispatch.plugins.kandbox_planner.env.env_models import (
    KafkaEnvMessage,
    Appointment,
    Job,
    Worker,
    JobLocationBase,
)


from dispatch.config import KAFKA_BOOTSTRAP_SERVERS, PLANNER_SERVER_ROLE, TESTING_MODE

import socket

from dataclasses import asdict as python_asdict

from dispatch.plugins.kandbox_planner.util.kandbox_json_util import generic_json_encoder

from dispatch.team import service as team_service
from dispatch.team.models import TeamUpdate


class FakeKafkaAdapter:
    def __init__(self, env):  # team_id is included in env
        self.env = env

        log.info("Initialized fake slot consumer")

    # def __del__(self):
    #     self.producer.close()

    def get_env_window_topic_name(self) -> str:
        return f"{KandboxMessageTopicType.ENV_WINDOW}.{self.env.team_env_key}"

    def get_env_window_out_topic_name(self) -> str:
        return f"{KandboxMessageTopicType.ENV_WINDOW_OUTPUT}.{self.env.team_env_key}"

    def get_env_slot_topic_name(self) -> str:
        return f"{KandboxMessageTopicType.ENV_SLOT}.{self.env.team_env_key}"

    def post_env_message(self, message_type, payload):
        """This is used by ENV to post a message"""
        return True

    def post_refresh_planning_window(self):
        """This is used by ENV to post a message
        TODO, to replace by post_env_message"""

        return True

    def post_changed_slot_codes(
        self, message_type: KafkaMessageType, changed_slot_codes_list: List
    ):
        """This is used by ENV to post changed job to external"""

        return

    def post_changed_jobs(self, changed_job_codes_set):
        """This is used by ENV to post changed job to external"""

        return

    def post_jobs(self, planner, message_type, job_codes):
        """This is used by External Adapter to post any changed objects including workers, jobs to ENV"""
        return

    def post_job(self, planner, message_type, job):
        return

    def post_workers(self, planner, message_type, worker_codes):
        return

    def post_appointments(self, planner, message_type, appointment_codes):
        return

    def post_appointment(self, planner, message_type, appointment):
        return

    def post_abenses(self, planner, message_type, absences_code):
        return

    def trigger_update_planning_window(self, start_minutes):
        return

    def trigger_refresh_single_recommendation(self, job_code: str):
        return

    def process_env_out_message(self, msg):
        print("Not implemented.")

    def process_env_message(self, msg, auto_replay_in_process=True):
        return

    def consume_env_messages(self):
        """Main loop for kafka message"""
        return

    def consume_env_out_messages(self):
        """Main loop for kafka out message"""

        return

    def process_slot_message(self, msg):
        return

    def consume_slot_messages(self):
        i = 0
        return

        return
