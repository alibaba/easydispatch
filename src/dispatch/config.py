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


config = Config(".env")

LOG_LEVEL = config("LOG_LEVEL", default=logging.WARNING)

module_levels = {
    "dispatch.main": logging.ERROR,
    "recommendation_server": logging.DEBUG,
    "rllib_env_job2slot": logging.ERROR,
    "dispatch.plugins.kandbox_planner.routing.travel_time_routingpy_redis": logging.ERROR,
}


ENV = config("ENV", default="local")

DISPATCH_UI_URL = config("DISPATCH_UI_URL")
DISPATCH_HELP_EMAIL = config("DISPATCH_HELP_EMAIL")
DISPATCH_HELP_SLACK_CHANNEL = config("DISPATCH_HELP_SLACK_CHANNEL")

# authentication
DISPATCH_AUTHENTICATION_PROVIDER_SLUG = config(
    "DISPATCH_AUTHENTICATION_PROVIDER_SLUG", default="dispatch-auth-provider-basic"
)
VUE_APP_DISPATCH_AUTHENTICATION_PROVIDER_SLUG = DISPATCH_AUTHENTICATION_PROVIDER_SLUG

DISPATCH_JWT_SECRET = config("DISPATCH_JWT_SECRET", default=None)
DISPATCH_JWT_ALG = config("DISPATCH_JWT_ALG", default="HS256")
DISPATCH_JWT_EXP = config("DISPATCH_JWT_EXP", default=8640000)  # Seconds

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
DATABASE_HOSTNAME = config("DATABASE_HOSTNAME")
DATABASE_CREDENTIALS = config("DATABASE_CREDENTIALS", cast=Secret)
DATABASE_NAME = config("DATABASE_NAME", default="dispatch")
DATABASE_PORT = config("DATABASE_PORT", default="5432")
SQLALCHEMY_DATABASE_URI = f"postgresql+psycopg2://{DATABASE_CREDENTIALS}@{DATABASE_HOSTNAME}:{DATABASE_PORT}/{DATABASE_NAME}"
# MASTER_

# job plugins
INCIDENT_PLUGIN_CONTACT_SLUG = config("INCIDENT_PLUGIN_CONTACT_SLUG", default="dispatch-contact")
INCIDENT_PLUGIN_CONVERSATION_SLUG = config(
    "INCIDENT_PLUGIN_CONVERSATION_SLUG", default="slack-conversation"
)
INCIDENT_PLUGIN_DOCUMENT_SLUG = config(
    "INCIDENT_PLUGIN_DOCUMENT_SLUG", default="google-docs-document"
)
INCIDENT_PLUGIN_DOCUMENT_RESOLVER_SLUG = config(
    "INCIDENT_PLUGIN_DOCUMENT_RESOLVER_SLUG", default="dispatch-document-resolver"
)
INCIDENT_PLUGIN_EMAIL_SLUG = config(
    "INCIDENT_PLUGIN_EMAIL_SLUG", default="google-gmail-conversation"
)
INCIDENT_PLUGIN_GROUP_SLUG = config(
    "INCIDENT_PLUGIN_GROUP_SLUG", default="google-group-participant-group"
)
INCIDENT_PLUGIN_PARTICIPANT_RESOLVER_SLUG = config(
    "INCIDENT_PLUGIN_PARTICIPANT_RESOLVER_SLUG", default="dispatch-participant-resolver"
)
INCIDENT_PLUGIN_STORAGE_SLUG = config(
    "INCIDENT_PLUGIN_STORAGE_SLUG", default="google-drive-storage"
)

INCIDENT_PLUGIN_CONFERENCE_SLUG = config(
    "INCIDENT_PLUGIN_CONFERENCE_SLUG", default="google-calendar-conference"
)
INCIDENT_PLUGIN_TICKET_SLUG = config("INCIDENT_PLUGIN_TICKET_SLUG", default="jira-ticket")

INCIDENT_PLUGIN_TASK_SLUG = config("INCIDENT_PLUGIN_TASK_SLUG", default="google-drive-task")

# job resources
INCIDENT_CONVERSATION_COMMANDS_REFERENCE_DOCUMENT_ID = config(
    "INCIDENT_CONVERSATION_COMMANDS_REFERENCE_DOCUMENT_ID"
)
INCIDENT_DOCUMENT_INVESTIGATION_SHEET_ID = config("INCIDENT_DOCUMENT_INVESTIGATION_SHEET_ID")
INCIDENT_FAQ_DOCUMENT_ID = config("INCIDENT_FAQ_DOCUMENT_ID")
INCIDENT_STORAGE_ARCHIVAL_FOLDER_ID = config("INCIDENT_STORAGE_ARCHIVAL_FOLDER_ID")
INCIDENT_STORAGE_INCIDENT_REVIEW_FILE_ID = config("INCIDENT_STORAGE_INCIDENT_REVIEW_FILE_ID")
INCIDENT_STORAGE_EXECUTIVE_REPORT_FILE_ID = config("INCIDENT_STORAGE_EXECUTIVE_REPORT_FILE_ID")
INCIDENT_STORAGE_RESTRICTED = config("INCIDENT_STORAGE_RESTRICTED", cast=bool, default=True)
INCIDENT_NOTIFICATION_CONVERSATIONS = config(
    "INCIDENT_NOTIFICATION_CONVERSATIONS", cast=CommaSeparatedStrings, default=""
)
INCIDENT_NOTIFICATION_DISTRIBUTION_LISTS = config(
    "INCIDENT_NOTIFICATION_DISTRIBUTION_LISTS", cast=CommaSeparatedStrings, default=""
)
INCIDENT_ONCALL_SERVICE_ID = config("INCIDENT_ONCALL_SERVICE_ID", default=None)
if not INCIDENT_ONCALL_SERVICE_ID:
    INCIDENT_DAILY_SUMMARY_ONCALL_SERVICE_ID = config(
        "INCIDENT_DAILY_SUMMARY_ONCALL_SERVICE_ID", default=None
    )
    if INCIDENT_DAILY_SUMMARY_ONCALL_SERVICE_ID:
        log.warn(
            "INCIDENT_DAILY_SUMMARY_ONCALL_SERVICE_ID has been deprecated. Please use INCIDENT_ONCALL_SERVICE_ID instead."
        )
        INCIDENT_ONCALL_SERVICE_ID = INCIDENT_DAILY_SUMMARY_ONCALL_SERVICE_ID

INCIDENT_RESOURCE_TACTICAL_GROUP = config(
    "INCIDENT_RESOURCE_TACTICAL_GROUP", default="google-group-participant-tactical-group"
)
INCIDENT_RESOURCE_NOTIFICATIONS_GROUP = config(
    "INCIDENT_RESOURCE_NOTIFICATIONS_GROUP", default="google-group-participant-notifications-group"
)
INCIDENT_RESOURCE_INVESTIGATION_DOCUMENT = config(
    "INCIDENT_RESOURCE_INVESTIGATION_DOCUMENT", default="google-docs-investigation-document"
)
INCIDENT_RESOURCE_INVESTIGATION_SHEET = config(
    "INCIDENT_RESOURCE_INVESTIGATION_SHEET", default="google-docs-investigation-sheet"
)
INCIDENT_RESOURCE_INCIDENT_REVIEW_DOCUMENT = config(
    "INCIDENT_RESOURCE_INCIDENT_REVIEW_DOCUMENT", default="google-docs-job-review-document"
)
INCIDENT_RESOURCE_EXECUTIVE_REPORT_DOCUMENT = config(
    "INCIDENT_RESOURCE_EXECUTIVE_REPORT_DOCUMENT", default="google-docs-executive-report-document"
)
INCIDENT_RESOURCE_CONVERSATION_COMMANDS_REFERENCE_DOCUMENT = config(
    "INCIDENT_RESOURCE_CONVERSATION_COMMANDS_REFERENCE_DOCUMENT",
    default="google-docs-conversation-commands-reference-document",
)
INCIDENT_RESOURCE_FAQ_DOCUMENT = config(
    "INCIDENT_RESOURCE_FAQ_DOCUMENT", default="google-docs-faq-document"
)
INCIDENT_RESOURCE_INCIDENT_TASK = config(
    "INCIDENT_RESOURCE_INCIDENT_TASK", default="google-docs-job-task"
)
ONCALL_PLUGIN_SLUG = config("ONCALL_PLUGIN_SLUG", default="opsgenie-oncall")

# Job Cost Configuration
ANNUAL_COST_EMPLOYEE = config("ANNUAL_COST_EMPLOYEE", cast=int, default="650000")
BUSINESS_HOURS_YEAR = config("BUSINESS_HOURS_YEAR", cast=int, default="2080")


# Incident Cost Configuration
ANNUAL_COST_EMPLOYEE = config("ANNUAL_COST_EMPLOYEE", cast=int, default="650000")
BUSINESS_HOURS_YEAR = config("BUSINESS_HOURS_YEAR", cast=int, default="2080")

# kafka
KAFKA_BOOTSTRAP_SERVERS = config("KAFKA_BOOTSTRAP_SERVERS", default="localhost:9092")


# redis
REDIS_HOST = config("REDIS_HOST", default="127.0.0.1")
REDIS_PORT = config("REDIS_PORT", default="6379")
REDIS_PASSWORD = config("REDIS_PASSWORD", default=None)


# kandbox
NBR_OF_OBSERVED_WORKERS = config("NBR_OF_OBSERVED_WORKERS", cast=int, default=8)
MINUTES_PER_DAY = config("MINUTES_PER_DAY", cast=int, default=1440)
MAX_NBR_OF_JOBS_PER_DAY_WORKER = config("MAX_NBR_OF_JOBS_PER_DAY_WORKER", cast=int, default=8)
SCORING_FACTOR_STANDARD_TRAVEL_MINUTES = config(
    "SCORING_FACTOR_STANDARD_TRAVEL_MINUTES", cast=int, default=100
)
DATA_START_DAY = config("DATA_START_DAY", default="20201015")

PRELOAD_ORG_CODE = config("PRELOAD_ORG_CODE", default="0")
PRELOAD_TEAM_ID = config("PRELOAD_TEAM_ID", default=2)
TESTING_MODE = config("TESTING_MODE", default="yes")

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
google_calendar_token_path = "/tmp/token.pickle"


POSITION_SLOT_TYPE = 6
POSITION_ASSIGNED_JOB_INDEX = 7

APPOINTMENT_LOCAL_FILE = os.getenv("APPOINTMENT_LOCAL_FILE")

DEBUGGING_JOB_CODE_SET = {
    "0429-9-Replacement_Ventilation-255",
}


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
