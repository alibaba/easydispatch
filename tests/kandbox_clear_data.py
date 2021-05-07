import requests
import json
import time
import click

from kafka import KafkaAdminClient, KafkaConsumer

import redis
from redis.exceptions import LockError

from sqlalchemy_utils import database_exists
from sqlalchemy import MetaData, create_engine
from sqlalchemy.schema import CreateSchema
from sqlalchemy.orm import sessionmaker
from psycopg2.errors import DuplicateSchema, ProgrammingError

from dispatch.config import (
    SQLALCHEMY_DATABASE_URI,
    DATABASE_HOSTNAME,
    DATABASE_NAME,
    DATABASE_PORT,
    DATABASE_CREDENTIALS,
    REDIS_HOST,
    REDIS_PORT,
    REDIS_PASSWORD,
    KAFKA_BOOTSTRAP_SERVERS,
)

# fmt:off

data_start_day = "20201015"
token = ""

def login():
    url = "http://localhost:8000/api/v1/auth/login"
    data = {"email": "_Please_Set_Your_Own_", "password": "_Please_Set_Your_Own_"}

    rep = requests.post(url, json.dumps(data))

    rep_data = json.loads(rep.content)

    if rep.status_code == 200:
        return rep_data["token"]
    else:
        print("login fail")
        return ""

def clear_kafka():
    kafka_admin_client = KafkaAdminClient(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
    )

    kafka_consumer = KafkaConsumer(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS.split(";"),
    )

    kafka_admin_client.delete_topics(list(kafka_consumer.topics()))
    print("--kafka cleared --")


def clear_redis():
    if REDIS_PASSWORD == "":
        redis_conn = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, password=None)
    else:
        redis_conn = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD)

    redis_conn.flushdb()
    print("--redis cleared --")

def clear_all_data():
    clear_kafka()
    clear_redis()

    if not database_exists(str(SQLALCHEMY_DATABASE_URI)):
        print("Failed, the database does not exist.")
        return False

    engine = create_engine(str(SQLALCHEMY_DATABASE_URI))

    db_session = sessionmaker(bind=engine)
    session = db_session()

    session.execute("delete from event;")
    session.execute("delete from assoc_job_tags;")
    session.execute("delete from job_scheduled_secondary_workers;")


    session.execute("delete from job;")
    # session.execute("delete from worker_absence;")
    # session.execute("delete from appointment;")
    session.execute("delete from worker;")
    session.execute("delete from location;")
    # session.execute("update team set latest_env_kafka_offset=0;")
    session.execute("delete from team;")
    session.execute("delete from tag;")
    session.execute("delete from service_plugin;")
    session.execute("delete from plugin;")
    session.execute("delete from service;")
    session.execute("delete from dispatch_user;")

    session.execute("commit;")
    print("--postgres DB cleared --")


def clear_data_for_redispatching():
    clear_kafka()
    clear_redis()

    if not database_exists(str(SQLALCHEMY_DATABASE_URI)):
        print("Failed, the database does not exist.")
        return False

    engine = create_engine(str(SQLALCHEMY_DATABASE_URI))

    db_session = sessionmaker(bind=engine)
    session = db_session()

    session.execute("delete from job_scheduled_secondary_workers;")
    session.execute("update job set planning_status = 'U';") 
    session.execute("update team set latest_env_kafka_offset=0;")
    session.execute("commit;")
    print("--postgres DB cleared --")


def clear_all_worker_jobs():
    print("--Started removing jobs--")

    clear_kafka()
    clear_redis()

    if not database_exists(str(SQLALCHEMY_DATABASE_URI)):
        print("Failed, the database does not exist.")
        return False

    engine = create_engine(str(SQLALCHEMY_DATABASE_URI))

    db_session = sessionmaker(bind=engine)
    session = db_session()

    session.execute("delete from event;")
    session.execute("delete from job_scheduled_secondary_workers;")
    session.execute("delete from job;") 
    session.execute("delete from worker;")
    session.execute("commit;")
    click.secho("Success. clear_all_worker_jobs is done.", fg="green")


#
# clear_all_data()
clear_all_worker_jobs()
# clear_data_for_redispatching()
