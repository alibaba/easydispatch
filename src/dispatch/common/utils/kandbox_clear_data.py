import requests
import json
import time
import click

# from kafka import KafkaAdminClient, KafkaConsumer

import redis
from redis.exceptions import LockError

from sqlalchemy_utils import database_exists
from sqlalchemy import MetaData, create_engine
from sqlalchemy.schema import CreateSchema
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
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
    REDIS_DB,
    KAFKA_BOOTSTRAP_SERVERS,
)
# 
# from etc.experimental_code.cvrp.ortools_cvrp1 import main

# fmt:off

# data_start_day = "20201015"
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
        redis_conn = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, password=None,db=REDIS_DB)
    else:
        redis_conn = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD,db=REDIS_DB)

    redis_conn.flushdb()
    print("--redis cleared --")

def clear_all_data():
    assert False, "be careful"
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


def clear_all_data_for_redispatching():
    clear_kafka()

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
    print("--postgres DB, all planning status are set to U --")
    click.secho("Success. all planning status are set to U, Kafka cleared, redis untouched.", fg="green")



def clear_team_data_for_redispatching(org_code, team_id):

    # TODO, reset team offset.
    clear_kafka()

    if not database_exists(str(SQLALCHEMY_DATABASE_URI)):
        print("Failed, the database does not exist.")
        return False

    engine = create_engine(str(SQLALCHEMY_DATABASE_URI))

    db_session = sessionmaker(bind=engine)
    session = db_session()

    session.execute(f"delete from job_scheduled_secondary_workers where job_code in (select id from job where team_id={team_id});")
    session.execute(f"update job set planning_status = 'U'  where team_id={team_id};") 
    session.execute(f"update team set latest_env_kafka_offset=0  where id={team_id};")
    session.execute("commit;")
    print("--postgres DB, all planning status are set to U --")
    click.secho("Success. all planning status are set to U, Kafka cleared, redis untouched.", fg="green")
    click.secho("Please call reset window to reset redis.", fg="yellow")


def clear_all_worker_jobs():
    print("--Started removing jobs--")

    clear_kafka()
    # clear_redis()

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
    session.execute("delete from location;")
    session.execute("commit;")
    click.secho("Success. clear_all_worker_jobs is done.", fg="yellow")



def clear_all_worker_jobs_in_team(db_session, org_code: str, team_id: int,delete_dispatch_user=None ):
    click.secho(f"--Started removing jobs for {org_code}.{team_id}--")
    schema_name = "dispatch_organization_" + org_code

    # clear_kafka()
    # clear_redis()

    db_session.execute(text("delete from {}.job_event".format(schema_name)))
    db_session.execute(text("delete from {}.job where team_id = {}".format(schema_name, team_id)))

    db_session.execute(text("""
        delete from {}.order_event  
        where order_code in (
            select order_code from {}.order
            where team_id = {}
        )""".format(schema_name, schema_name, team_id)))
    db_session.execute(text("delete from {}.order where team_id = {}".format(schema_name, team_id)))
    db_session.execute(text("delete from {}.location_group".format(schema_name)))
    db_session.execute(text("delete from {}.worker_event".format(schema_name)))
    db_session.execute(text("delete from {}.worker where team_id = {}".format(schema_name, team_id)))
    db_session.execute(text("delete from {}.location where team_id = {}".format(schema_name, team_id)))
    if delete_dispatch_user:
        # 默认任务 不带 .com 的是 创建的User 
        db_session.execute(text(f"delete from dispatch_core.dispatch_user where org_code = '{org_code}' and email  not like '%.com%' "))
        
    db_session.commit()

    click.secho(f"clear_all_worker_jobs_in_team is done for team: {org_code}.{team_id}", fg="yellow")

#
# clear_all_data()
# clear_all_worker_jobs()
# clear_all_data_for_redispatching()
if __name__ == '__main__':
    clear_kafka()
