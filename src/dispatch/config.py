import redis
from datetime import datetime
import logging
import os
import base64

from starlette.config import Config
from starlette.datastructures import CommaSeparatedStrings

log = logging.getLogger(__name__)


# if we have metatron available to us, lets use it to decrypt our secrets in memory
try:
    import metatron.decrypt

    class Secret:
        """
        Holds a string value that should not be revealed in tracebacks etc.
        You should cast the value to `str` at the point it is required.
        """

        def __init__(self, value: str):
            self._value = value
            self._decrypted_value = (
                metatron.decrypt.MetatronDecryptor()
                .decryptBytes(base64.b64decode(self._value))
                .decode("utf-8")
            )

        def __repr__(self) -> str:
            class_name = self.__class__.__name__
            return f"{class_name}('**********')"

        def __str__(self) -> str:
            return self._decrypted_value


except Exception:
    # Let's see if we have boto3 for KMS available to us, let's use it to decrypt our secrets in memory
    try:
        import boto3

        class Secret:
            """
            Holds a string value that should not be revealed in tracebacks etc.
            You should cast the value to `str` at the point it is required.
            """

            def __init__(self, value: str):
                self._value = value
                self._decrypted_value = (
                    boto3.client("kms")
                    .decrypt(CiphertextBlob=base64.b64decode(value))["Plaintext"]
                    .decode("utf-8")
                )

            def __repr__(self) -> str:
                class_name = self.__class__.__name__
                return f"{class_name}('**********')"

            def __str__(self) -> str:
                return self._decrypted_value

    except Exception:
        from starlette.datastructures import Secret


config = Config("dev.env")

LOG_LEVEL = config("LOG_LEVEL", default=logging.WARNING)
LOG_FILE = config("LOG_FILE", default='dispatch_log_file.csv')
LOG_FILE_CALL_BACK = config("LOG_FILE_CALL_BACK", default='c.csv')

module_levels = {
    "dispatch.main": logging.INFO,
    "recommendation_server": logging.INFO,
    "rllib_env_job2slot": logging.ERROR,
    "dispatch.plugins.kandbox_planner.routing.travel_time_routingpy_redis": logging.ERROR,
    "kandbox_kafka_adapter": logging.INFO,
    "dispatch.event": logging.ERROR,
    "dispatch.contrib.uupaotui": logging.ERROR,
    "dispatch.job.service": logging.INFO,
    "ipms_apms_rps_callback": logging.INFO,
    "dispatch.contrib.uupaotui.processor.core": logging.INFO,
    "dispatch.contrib.baituo.baituo_dispatch": logging.INFO,
    "zulip": logging.INFO,
}


ENV = config("ENV", default="local")
DEBUG = False
DISPATCH_UI_URL = config("DISPATCH_UI_URL", default='https://localhost:8000')
DISPATCH_HELP_EMAIL = config("DISPATCH_HELP_EMAIL", default='dispatch@example.com')
DISPATCH_HELP_SLACK_CHANNEL = config("DISPATCH_HELP_SLACK_CHANNEL", default='general')

# authentication
DISPATCH_AUTHENTICATION_PROVIDER_SLUG = config(
    "DISPATCH_AUTHENTICATION_PROVIDER_SLUG", default="dispatch-auth-provider-basic"
)
VUE_APP_DISPATCH_AUTHENTICATION_PROVIDER_SLUG = DISPATCH_AUTHENTICATION_PROVIDER_SLUG

LOCAL_ENCRYPT_KEY= config("LOCAL_ENCRYPT_KEY", default='010101')

DISPATCH_JWT_SECRET = config("DISPATCH_JWT_SECRET", default='secret')
DISPATCH_JWT_ALG = config("DISPATCH_JWT_ALG", default="HS256")
# Seconds, 8640000/60/60/24 == 100 days.
DISPATCH_JWT_EXP = config("DISPATCH_JWT_EXP", default=8640000)

if DISPATCH_AUTHENTICATION_PROVIDER_SLUG == "dispatch-auth-provider-basic":
    if not DISPATCH_JWT_SECRET:
        log.warn("No JWT secret specified, this is required if you are using basic authentication.")

DISPATCH_AUTHENTICATION_DEFAULT_USER = config(
    "DISPATCH_AUTHENTICATION_DEFAULT_USER", default="dispatch@example.com"
)

DISPATCH_AUTHENTICATION_PROVIDER_PKCE_JWKS = config(
    "DISPATCH_AUTHENTICATION_PROVIDER_PKCE_JWKS", default=None
)

if DISPATCH_AUTHENTICATION_PROVIDER_SLUG == "dispatch-auth-provider-pkce":
    if not DISPATCH_AUTHENTICATION_PROVIDER_PKCE_JWKS:
        log.warn(
            "No PKCE JWKS url provided, this is required if you are using PKCE authentication."
        )

VUE_APP_DISPATCH_AUTHENTICATION_PROVIDER_PKCE_OPEN_ID_CONNECT_URL = config(
    "VUE_APP_DISPATCH_AUTHENTICATION_PROVIDER_PKCE_OPEN_ID_CONNECT_URL", default=None
)
VUE_APP_DISPATCH_AUTHENTICATION_PROVIDER_PKCE_CLIENT_ID = config(
    "VUE_APP_DISPATCH_AUTHENTICATION_PROVIDER_PKCE_CLIENT_ID", default=None
)

# static files
DEFAULT_STATIC_DIR = os.path.join(
    os.path.abspath(os.path.dirname(__file__)), "static/dispatch/dist"
)
STATIC_DIR = config("STATIC_DIR", default=DEFAULT_STATIC_DIR)

# metrics
METRIC_PROVIDERS = config("METRIC_PROVIDERS", cast=CommaSeparatedStrings, default="")

# sentry middleware
SENTRY_DSN = config("SENTRY_DSN", cast=Secret, default=None)

# database

DATABASE_HOSTNAME = config("DATABASE_HOSTNAME", default='localhost')
DATABASE_CREDENTIALS = config("DATABASE_CREDENTIALS", cast=Secret, default='')
DATABASE_NAME = config("DATABASE_NAME", default="")
PYTEST_FLAG = config('PYTEST_FLAG', cast=bool, default=False)

DATABASE_PORT = config("DATABASE_PORT", default="5432")
SQLALCHEMY_DATABASE_URI = f"postgresql+psycopg2://{DATABASE_CREDENTIALS}@{DATABASE_HOSTNAME}:{DATABASE_PORT}/{DATABASE_NAME}"
if PYTEST_FLAG:
    SQLALCHEMY_DATABASE_URI = f"postgresql+psycopg2://{DATABASE_CREDENTIALS}@{DATABASE_HOSTNAME}:{DATABASE_PORT}/dispatch_test"
# MASTER_

INCIDENT_PLUGIN_CONTACT_SLUG = config("INCIDENT_PLUGIN_CONTACT_SLUG", default="dispatch-contact")



# Incident Cost Configuration
ANNUAL_COST_EMPLOYEE = config("ANNUAL_COST_EMPLOYEE", cast=int, default="650000")
BUSINESS_HOURS_YEAR = config("BUSINESS_HOURS_YEAR", cast=int, default="2080")


# kafka
KAFKA_BOOTSTRAP_SERVERS = config("KAFKA_BOOTSTRAP_SERVERS", default="localhost:9092")


# redis
REDIS_HOST = config("REDIS_HOST", default="127.0.0.1")
REDIS_PORT = config("REDIS_PORT", default="6379")
REDIS_PASSWORD = config("REDIS_PASSWORD", default=None)

if REDIS_PASSWORD == "":
    redis_pool = redis.ConnectionPool(host=REDIS_HOST, port=REDIS_PORT,
                                      password=None, decode_responses=True)
else:
    redis_pool = redis.ConnectionPool(host=REDIS_HOST, port=REDIS_PORT,
                                      password=REDIS_PASSWORD, decode_responses=True)

# redis_pool = redis.ConnectionPool(host='10.0.0.1', port=6379, db=0)

# kandbox
NBR_OF_OBSERVED_WORKERS = config("NBR_OF_OBSERVED_WORKERS", cast=int, default=8)
MINUTES_PER_DAY = config("MINUTES_PER_DAY", cast=int, default=1440)
MAX_NBR_OF_JOBS_PER_DAY_WORKER = config("MAX_NBR_OF_JOBS_PER_DAY_WORKER", cast=int, default=16)
SCORING_FACTOR_STANDARD_TRAVEL_MINUTES = config(
    "SCORING_FACTOR_STANDARD_TRAVEL_MINUTES", cast=int, default=100
)
DATA_START_DAY = config("DATA_START_DAY", default="20201015")

PRELOAD_ORG_CODE = config("PRELOAD_ORG_CODE", default="0")
PRELOAD_TEAM_ID = config("PRELOAD_TEAM_ID", default=2)

MIN_START_MINUTES_FROM_NOW = 60

APPOINTMENT_DEBUG_LIST_STR = config("APPOINTMENT_DEBUG_LIST", default="")
if len(APPOINTMENT_DEBUG_LIST_STR) < 1:
    APPOINTMENT_DEBUG_LIST = set()
else:
    APPOINTMENT_DEBUG_LIST = set(APPOINTMENT_DEBUG_LIST_STR.split(";"))

# say hello sleep time
SAY_HELLO_SLEEP_TIME = config("SAY_HELLO_SLEEP_TIME", cast=int, default=2)
SAY_HELLO_URL = config("SAY_HELLO_URL", default="http://localhost")

# print("loaded config.")

# Those two are not in devenv and should be set differently.
PRELOAD_KANBOX_ENV = config("PRELOAD_KANBOX_ENV", default="no")
PLANNER_SERVER_ROLE = config("PLANNER_SERVER_ROLE", default="api")
# project names like alibaba,x,y,z,pickdrop
# PROJECT_NAME = config("PROJECT_NAME", default="baseline")

# api_async_task or standalone_recommander
RECOMMDER_DEPLOYMENT = config("RECOMMDER_DEPLOYMENT", default="api_async_task")

ENABLE_REGISTER = config("ENABLE_REGISTER", default="no")

MAX_MINUTES_PER_TECH = 10_000_000  # 10,000,000 minutes =  20 years.
MAX_TRANSACTION_RETRY = 2
PUBLISH_TO_PUBSUB = config("PUBLISH_TO_PUBSUB", default="no")


# Kandbox config
basedir = os.path.abspath(os.path.dirname(__file__))
# print("kandbox_planner config basedir is :", basedir)


# Print the value of
# 'HOME' environment variable
# print("Database :", DATABASE_URI)

KANDBOX_MAXINT = 2147483647

KANDBOX_DATE_FORMAT = "%Y%m%d"
ISO_DATE_FORMAT = "%Y-%m-%d"
# datetime.strptime('2019-07-01',"%Y-%m-%d")
ORIG_SYS_DATE_FORMAT = "%m/%d/%Y"

KANDBOX_DATETIME_FORMAT_WITH_MS = "%Y-%m-%d %H:%M:%S.%f"  # For postgres as well
KANDBOX_DATETIME_FORMAT_ISO = "%Y-%m-%dT%H:%M:%S"
KANDBOX_DATETIME_FORMAT_ISO_SPACE = "%Y-%m-%d %H:%M:%S"
KANDBOX_DATETIME_FORMAT_GTS_SLOT = "%Y%m%d%H%M"

# FOR MODEL
NBR_DAYS_PER_TECH = 7  # 1, NUMBER of days for training the model, and observe
MAX_TIMESLOT_PER_DAY = 2
NBR_FEATURE_PER_TIMESLOT = 4
MAX_WORKING_TIME_DURATION = 60 * 12

NBR_OF_DAYS_PLANNING_WINDOW = 2

# KANDBOX_JOB_MINIMUM_START_DAY = '20200422'  # datetime.strftime(datetime.now(), KANDBOX_DATE_FORMAT) #'20200415'

# For london Regression Testing
KANDBOX_TEST_START_DAY = "20200519"  # s KANDBOX_JOB_MINIMUM_START_DAY # '20200402'
KANDBOX_TEST_END_DAY = "20200529"
KANDBOX_TEST_OPTI1DAY_START_DAY = "20200521"  # '20200503'
KANDBOX_TEST_OPTI1DAY_END_DAY = "20200525"

KANDBOX_OPTI1DAY_EXEC_SECONDS = 2
KANDBOX_TEST_WORKING_DIR = "/tmp"
BATCH_OSS_LOCAL_STORAGE_PATH = "/tmp"
RL_MAX_EPOCHS = 5
RL_TRAINING_DAYS = 8

OPTI1DAY_AUTOMATIC = False
if os.getenv("OPTI1DAY_AUTOMATIC", default="False") == "True":
    OPTI1DAY_AUTOMATIC = True

RL_PLANNER_AUTOMATIC = False
if os.getenv("RL_PLANNER_AUTOMATIC", default="False") == "True":
    RL_PLANNER_AUTOMATIC = True

SEND_GOOGLE_CALENDAR = False
google_calendar_token_path = ""


POSITION_SLOT_TYPE = 6
POSITION_ASSIGNED_JOB_INDEX = 7

APPOINTMENT_LOCAL_FILE = os.getenv("APPOINTMENT_LOCAL_FILE")

DEBUGGING_JOB_CODE_SET = { }


DEBUGGING_SLOT_CODE_SET = {
    # "env_duan3_1/s/Alexia_118560_119100_F", []
}

ENABLE_REDIS_CACHE_SERVER = True
# DEBUG_ENABLE_APPOINTMENT_REPLAY = False

TRAVEL_MINUTES_WARNING_LEVEL = 200
TRAVEL_MINUTES_WARNING_RESULT = 10000

DEFAULT_START_DAY = "K_START"


REDIS_KEY_SEPERATOR = "/"

APPOINTMENT_ON_REDIS_KEY_PREFIX = "A/"
TRAINED_MODEL_PATH = config("TRAINED_MODEL_PATH", default="/tmp")


# Food Delivery

UU_START_FLAG = config('UU_START_FLAG', default=None)
UU_API_TOKEN = config('UU_API_TOKEN', default=None)
UU_API_URL = config('UU_API_URL', default=None)
UU_CITY = config('UU_CITY', default=None)
UU_MQ_USERNAME = config('UU_MQ_USERNAME', default=None)
UU_MQ_PASSWORD = config('UU_MQ_PASSWORD', default=None)
UU_MQ_PORT = config('UU_MQ_PORT', default=None)
UU_MQ_HOST = config('UU_MQ_HOST', default=None)
UU_MQ_VIRTUAL_HOST = config('UU_MQ_VIRTUAL_HOST', default=None)
BACKGROUND_ENV_SYNC_INTERVAL_SECONDS = config('BACKGROUND_ENV_SYNC_INTERVAL_SECONDS', default=20)

# Field Service
LOCATION_SERVICE_URL = config(
    'LOCATION_SERVICE_URL', default='')
LOCATION_SERVICE_TOKEN = config('LOCATION_SERVICE_TOKEN',default='')
LOCATION_SERVICE_REQUEST_METHOD = config('LOCATION_SERVICE_REQUEST_METHOD', default='POST')

CALLBACK_USER_NAME = config('CALLBACK_USER_NAME', default="")
CALLBACK_PASSWORD = config('CALLBACK_PASSWORD', default="")
CALLBACK_TOKEN_URL = config(
    'CALLBACK_TOKEN_URL', default="")
APMS_CALLBACK_URL = config(
    'APMS_CALLBACK_URL', default="http://")
IPMS_CALLBACK_URL = config(
    'IPMS_CALLBACK_URL', default="http://")
PLDT_START_FLAG = config('PLDT_START_FLAG', cast=bool, default=False)

DISPATCH_PICK_DROP_FLAG = config('DISPATCH_PICK_DROP_FLAG', cast=bool, default=False)

WEBZ_SITE = config(
    'WEBZ_SITE', default="http://localhost:8080")


ALEMBIC_TENANT_REVISION_PATH = config(
    "ALEMBIC_TENANT_REVISION_PATH",
    default=f"{os.path.dirname(os.path.realpath(__file__))}/database_util/revisions/tenant",
)

ALEMBIC_CORE_REVISION_PATH = config(
    "ALEMBIC_TENANT_REVISION_PATH",
    default=f"{os.path.dirname(os.path.realpath(__file__))}/database_util/revisions/core",
)
ALEMBIC_INI_PATH = config(
    "ALEMBIC_INI_PATH",
    default=f"{os.path.dirname(os.path.realpath(__file__))}/alembic.ini",
)
ALEMBIC_MULTI_TENANT_MIGRATION_PATH = config(
    "ALEMBIC_MULTI_TENANT_MIGRATION_PATH",
    default=f"{os.path.dirname(os.path.realpath(__file__))}/database_util/revisions/multi-tenant-migration.sql",
)
