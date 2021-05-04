import copy
from enum import Enum

from jinja2 import Template

from typing import List

from dispatch.conversation.enums import ConversationButtonActions
from dispatch.job.enums import JobPlanningStatus

from .config import (
    DISPATCH_UI_URL,
    INCIDENT_RESOURCE_CONVERSATION_COMMANDS_REFERENCE_DOCUMENT,
    INCIDENT_RESOURCE_EXECUTIVE_REPORT_DOCUMENT,
    INCIDENT_RESOURCE_FAQ_DOCUMENT,
    INCIDENT_RESOURCE_INCIDENT_REVIEW_DOCUMENT,
    INCIDENT_RESOURCE_INVESTIGATION_DOCUMENT,
    INCIDENT_RESOURCE_INVESTIGATION_SHEET,
)


class MessageType(str, Enum):
    job_daily_summary = "job-daily-summary"
    job_daily_summary_no_jobs = "job-daily-summary-no-jobs"
    job_executive_report = "job-executive-report"
    job_notification = "job-notification"
    job_participant_welcome = "job-participant-welcome"
    job_resources_message = "job-resources-message"
    job_tactical_report = "job-tactical-report"
    job_task_list = "job-task-list"
    job_task_reminder = "job-task-reminder"
    job_participant_suggested_reading = "job-participant-suggested-reading"


INCIDENT_STATUS_DESCRIPTIONS = { 
}

INCIDENT_TASK_REMINDER_DESCRIPTION = """
You are assigned to the following job tasks.
This is a reminder that these tasks have passed their due date.
Please review and update them as appropriate. Resolving them will stop the reminders.""".replace(
    "\n", " "
).strip()

INCIDENT_TASK_LIST_DESCRIPTION = """The following are open job tasks."""

INCIDENT_DAILY_SUMMARY_DESCRIPTION = """
Daily Jobs Summary""".replace(
    "\n", " "
).strip()

INCIDENT_DAILY_SUMMARY_ACTIVE_INCIDENTS_DESCRIPTION = f"""
Active Jobs (<{DISPATCH_UI_URL}/jobs/status|Details>)""".replace(
    "\n", " "
).strip()

INCIDENT_DAILY_SUMMARY_NO_ACTIVE_INCIDENTS_DESCRIPTION = """
There are no active jobs at this moment.""".replace(
    "\n", " "
).strip()

INCIDENT_DAILY_SUMMARY_STABLE_CLOSED_INCIDENTS_DESCRIPTION = """
Stable or Closed Jobs (last 24 hours)""".replace(
    "\n", " "
).strip()

INCIDENT_DAILY_SUMMARY_NO_STABLE_CLOSED_INCIDENTS_DESCRIPTION = """
There are no stable or closed jobs in the last 24 hours.""".replace(
    "\n", " "
).strip()

INCIDENT_COMMANDER_DESCRIPTION = """
The Job Commander (IC) is responsible for
knowing the full context of the job.
Contact them about any questions or concerns.""".replace(
    "\n", " "
).strip()

INCIDENT_COMMANDER_READDED_DESCRIPTION = """
{{ commander_fullname }} (Job Commander) has been re-added to the conversation.
Please, handoff the Job Commander role before leaving the conversation.""".replace(
    "\n", " "
).strip()

INCIDENT_TICKET_DESCRIPTION = """
Ticket for tracking purposes. It contains a description of
the job and links to resources.""".replace(
    "\n", " "
).strip()

INCIDENT_CONVERSATION_DESCRIPTION = """
Private conversation for real-time discussion. All job participants get added to it.
""".replace(
    "\n", " "
).strip()

INCIDENT_CONVERSATION_COMMANDS_REFERENCE_DOCUMENT_DESCRIPTION = """
Document containing the list of slash commands available to the Job Commander (IC)
and participants in the job conversation.""".replace(
    "\n", " "
).strip()

INCIDENT_CONFERENCE_DESCRIPTION = """
Video conference and phone bridge to be used throughout the job.  Password: {{conference_challenge}}
""".replace(
    "\n", ""
).strip()

INCIDENT_STORAGE_DESCRIPTION = """
Common storage for all job artifacts and
documents. Add logs, screen captures, or any other data collected during the
investigation to this drive. It is shared with all job participants.""".replace(
    "\n", " "
).strip()

INCIDENT_INVESTIGATION_DOCUMENT_DESCRIPTION = """
This is a document for all job facts and context. All
job participants are expected to contribute to this document.
It is shared with all job participants.""".replace(
    "\n", " "
).strip()

INCIDENT_INVESTIGATION_SHEET_DESCRIPTION = """
This is a sheet for tracking impacted assets. All
job participants are expected to contribute to this sheet.
It is shared with all job participants.""".replace(
    "\n", " "
).strip()

INCIDENT_FAQ_DOCUMENT_DESCRIPTION = """
First time responding to an information security job? This
document answers common questions encountered when
helping us respond to an job.""".replace(
    "\n", " "
).strip()

INCIDENT_REVIEW_DOCUMENT_DESCRIPTION = """
This document will capture all lessons learned, questions, and action items raised during the job.""".replace(
    "\n", " "
).strip()

INCIDENT_EXECUTIVE_REPORT_DOCUMENT_DESCRIPTION = """
This is a document that contains an executive report about the job.""".replace(
    "\n", " "
).strip()

INCIDENT_DOCUMENT_DESCRIPTIONS = {
    INCIDENT_RESOURCE_CONVERSATION_COMMANDS_REFERENCE_DOCUMENT: INCIDENT_CONVERSATION_COMMANDS_REFERENCE_DOCUMENT_DESCRIPTION,
    INCIDENT_RESOURCE_EXECUTIVE_REPORT_DOCUMENT: INCIDENT_EXECUTIVE_REPORT_DOCUMENT_DESCRIPTION,
    INCIDENT_RESOURCE_FAQ_DOCUMENT: INCIDENT_FAQ_DOCUMENT_DESCRIPTION,
    INCIDENT_RESOURCE_INCIDENT_REVIEW_DOCUMENT: INCIDENT_REVIEW_DOCUMENT_DESCRIPTION,
    INCIDENT_RESOURCE_INVESTIGATION_DOCUMENT: INCIDENT_INVESTIGATION_DOCUMENT_DESCRIPTION,
    INCIDENT_RESOURCE_INVESTIGATION_SHEET: INCIDENT_INVESTIGATION_SHEET_DESCRIPTION,
}

INCIDENT_PARTICIPANT_WELCOME_DESCRIPTION = """
You\'re being contacted because we think you may
be able to help us during this information security job.
Please review the content below and join us in the
job Slack channel.""".replace(
    "\n", " "
).strip()

INCIDENT_WELCOME_CONVERSATION_COPY = """
This is the job conversation. Please pull in any
workers you feel may be able to help resolve this job.""".replace(
    "\n", " "
).strip()

INCIDENT_PARTICIPANT_SUGGESTED_READING_DESCRIPTION = """
Dispatch thinks the following documents are
relevant to this job.""".replace(
    "\n", " "
).strip()

INCIDENT_NOTIFICATION_PURPOSES_FYI = """
This message is for notification purposes only.""".replace(
    "\n", " "
).strip()

INCIDENT_CAN_REPORT_REMINDER = """
It's time to send a new CAN report. Go to the Demisto UI and run the
CAN Report playbook from the Playground Work Plan.""".replace(
    "\n", " "
).strip()

INCIDENT_VULNERABILITY_DESCRIPTION = """
We are tracking the details of the vulnerability that led to this job
in the VUL Jira issue linked above.""".replace(
    "\n", " "
).strip()

INCIDENT_STABLE_DESCRIPTION = """
The risk has been contained and the job marked as stable.""".replace(
    "\n", " "
).strip()

INCIDENT_CLOSED_DESCRIPTION = """
The job has been resolved and marked as closed.""".replace(
    "\n", " "
).strip()

INCIDENT_TACTICAL_REPORT_DESCRIPTION = """
The following conditions, actions, and needs summarize the current status of the job.""".replace(
    "\n", " "
).strip()

INCIDENT_NEW_ROLE_DESCRIPTION = """
{{assigner_fullname}} has assigned the role of {{assignee_role}} to {{assignee_fullname}}.
Please, contact {{assignee_firstname}} about any questions or concerns.""".replace(
    "\n", " "
).strip()

INCIDENT_REPORT_REMINDER_DESCRIPTION = """You have not provided a {{report_type}} for this job recently.
You can use `{{command}}` in the conversation to assist you in writing one.""".replace(
    "\n", " "
).strip()

INCIDENT_TASK_NEW_DESCRIPTION = """
The following job task has been created in the job document.\n\n*Description:* {{task_description}}\n\n*Assignees:* {{task_assignees|join(',')}}"""

INCIDENT_TASK_RESOLVED_DESCRIPTION = """
The following job task has been resolved in the job document.\n\n*Description:* {{task_description}}\n\n*Assignees:* {{task_assignees|join(',')}}"""

INCIDENT_TYPE_CHANGE_DESCRIPTION = """
The job type has been changed from *{{ job_type_old }}* to *{{ job_type_new }}*."""

INCIDENT_STATUS_CHANGE_DESCRIPTION = """
The job status has been changed from *{{ job_status_old }}* to *{{ job_status_new }}*."""

INCIDENT_PRIORITY_CHANGE_DESCRIPTION = """
The job priority has been changed from *{{ job_priority_old }}* to *{{ job_priority_new }}*."""

INCIDENT_NAME_WITH_ENGAGEMENT = {
    "title": "{{name}} Job Notification",
    "title_link": "{{ticket_weblink}}",
    "text": INCIDENT_NOTIFICATION_PURPOSES_FYI,
    "button_text": "Join Job",
    "button_value": "{{job_id}}",
    "button_action": ConversationButtonActions.invite_user,
}

INCIDENT_NAME = {
    "title": "{{name}} Job Notification",
    "title_link": "{{ticket_weblink}}",
    "text": INCIDENT_NOTIFICATION_PURPOSES_FYI,
}

INCIDENT_TITLE = {"title": "Job Title", "text": "{{title}}"}

INCIDENT_DESCRIPTION = {"title": "Job Description", "text": "{{description}}"}

INCIDENT_STATUS = {
    "title": "Job Status - {{status}}",
    "status_mapping": INCIDENT_STATUS_DESCRIPTIONS,
}

INCIDENT_TYPE = {"title": "Job Type - {{type}}", "text": "{{type_description}}"}

INCIDENT_PRIORITY = {
    "title": "Job Priority - {{priority}}",
    "text": "{{priority_description}}",
}

INCIDENT_PRIORITY_FYI = {
    "title": "Job Priority - {{priority}}",
    "text": "{{priority_description}}",
}

INCIDENT_COMMANDER = {
    "title": "Job Commander - {{commander_fullname}}",
    "title_link": "{{commander_weblink}}",
    "text": INCIDENT_COMMANDER_DESCRIPTION,
}

INCIDENT_CONFERENCE = {
    "title": "Job Conference",
    "title_link": "{{conference_weblink}}",
    "text": INCIDENT_CONFERENCE_DESCRIPTION,
}

INCIDENT_STORAGE = {
    "title": "Job Storage",
    "title_link": "{{storage_weblink}}",
    "text": INCIDENT_STORAGE_DESCRIPTION,
}

INCIDENT_CONVERSATION_COMMANDS_REFERENCE_DOCUMENT = {
    "title": "Job Conversation Commands Reference Document",
    "title_link": "{{conversation_commands_reference_document_weblink}}",
    "text": INCIDENT_CONVERSATION_COMMANDS_REFERENCE_DOCUMENT_DESCRIPTION,
}

INCIDENT_INVESTIGATION_DOCUMENT = {
    "title": "Job Investigation Document",
    "title_link": "{{document_weblink}}",
    "text": INCIDENT_INVESTIGATION_DOCUMENT_DESCRIPTION,
}

INCIDENT_INVESTIGATION_SHEET = {
    "title": "Job Investigation Sheet",
    "title_link": "{{sheet_weblink}}",
    "text": INCIDENT_INVESTIGATION_SHEET_DESCRIPTION,
}

INCIDENT_REVIEW_DOCUMENT = {
    "title": "Job Review Document",
    "title_link": "{{review_document_weblink}}",
    "text": INCIDENT_REVIEW_DOCUMENT_DESCRIPTION,
}

INCIDENT_FAQ_DOCUMENT = {
    "title": "Job FAQ Document",
    "title_link": "{{faq_weblink}}",
    "text": INCIDENT_FAQ_DOCUMENT_DESCRIPTION,
}

INCIDENT_TYPE_CHANGE = {"title": "Job Type Change", "text": INCIDENT_TYPE_CHANGE_DESCRIPTION}

INCIDENT_STATUS_CHANGE = {
    "title": "Job Status Change",
    "text": INCIDENT_STATUS_CHANGE_DESCRIPTION,
}

INCIDENT_PRIORITY_CHANGE = {
    "title": "Job Priority Change",
    "text": INCIDENT_PRIORITY_CHANGE_DESCRIPTION,
}

INCIDENT_PARTICIPANT_SUGGESTED_READING_ITEM = {
    "title": "{{name}}",
    "title_link": "{{weblink}}",
    "text": "{{description}}",
}

INCIDENT_PARTICIPANT_WELCOME = {
    "title": "Welcome to {{name}}",
    "title_link": "{{ticket_weblink}}",
    "text": INCIDENT_PARTICIPANT_WELCOME_DESCRIPTION,
}

INCIDENT_PARTICIPANT_WELCOME_MESSAGE = [
    INCIDENT_PARTICIPANT_WELCOME,
    INCIDENT_TITLE,
    INCIDENT_STATUS,
    INCIDENT_TYPE,
    INCIDENT_PRIORITY,
    INCIDENT_COMMANDER,
    INCIDENT_INVESTIGATION_DOCUMENT,
    INCIDENT_STORAGE,
    INCIDENT_CONFERENCE,
    INCIDENT_CONVERSATION_COMMANDS_REFERENCE_DOCUMENT,
    INCIDENT_FAQ_DOCUMENT,
]

INCIDENT_RESOURCES_MESSAGE = [
    INCIDENT_COMMANDER,
    INCIDENT_INVESTIGATION_DOCUMENT,
    INCIDENT_REVIEW_DOCUMENT,
    INCIDENT_STORAGE,
    INCIDENT_CONFERENCE,
    INCIDENT_CONVERSATION_COMMANDS_REFERENCE_DOCUMENT,
    INCIDENT_FAQ_DOCUMENT,
]

INCIDENT_NOTIFICATION_COMMON = [INCIDENT_TITLE]

INCIDENT_NOTIFICATION = INCIDENT_NOTIFICATION_COMMON.copy()
INCIDENT_NOTIFICATION.extend(
    [INCIDENT_STATUS, INCIDENT_TYPE, INCIDENT_PRIORITY_FYI, INCIDENT_COMMANDER]
)

INCIDENT_TACTICAL_REPORT = [
    {"title": "Job Tactical Report", "text": INCIDENT_TACTICAL_REPORT_DESCRIPTION},
    {"title": "Conditions", "text": "{{conditions}}"},
    {"title": "Actions", "text": "{{actions}}"},
    {"title": "Needs", "text": "{{needs}}"},
]

INCIDENT_EXECUTIVE_REPORT = [
    {"title": "Job Title", "text": "{{title}}"},
    {"title": "Current Status", "text": "{{current_status}}"},
    {"title": "Overview", "text": "{{overview}}"},
    {"title": "Next Steps", "text": "{{next_steps}}"},
]

INCIDENT_REPORT_REMINDER = [
    {
        "title": "{{name}} Job - {{report_type}} Reminder",
        "title_link": "{{ticket_weblink}}",
        "text": INCIDENT_REPORT_REMINDER_DESCRIPTION,
    },
    INCIDENT_TITLE,
]


INCIDENT_TASK_REMINDER = [
    {"title": "Job - {{ name }}", "text": "{{ title }}"},
    {"title": "Creator", "text": "{{ creator }}"},
    {"title": "Description", "text": "{{ description }}"},
    {"title": "Priority", "text": "{{ priority }}"},
    {"title": "Created At", "text": "", "datetime": "{{ created_at}}"},
    {"title": "Resolve By", "text": "", "datetime": "{{ resolve_by }}"},
    {"title": "Link", "text": "{{ weblink }}"},
]

INCIDENT_NEW_ROLE_NOTIFICATION = [
    {
        "title": "New {{assignee_role}} - {{assignee_fullname}}",
        "title_link": "{{assignee_weblink}}",
        "text": INCIDENT_NEW_ROLE_DESCRIPTION,
    }
]

INCIDENT_TASK_NEW_NOTIFICATION = [
    {
        "title": "New Job Task",
        "title_link": "{{task_weblink}}",
        "text": INCIDENT_TASK_NEW_DESCRIPTION,
    }
]

INCIDENT_TASK_RESOLVED_NOTIFICATION = [
    {
        "title": "Resolved Job Task",
        "title_link": "{{task_weblink}}",
        "text": INCIDENT_TASK_RESOLVED_DESCRIPTION,
    }
]

INCIDENT_COMMANDER_READDED_NOTIFICATION = [
    {"title": "Job Commander Re-Added", "text": INCIDENT_COMMANDER_READDED_DESCRIPTION}
]


def render_message_template(message_template: List[dict], **kwargs):
    """Renders the jinja data included in the template itself."""
    data = []
    new_copy = copy.deepcopy(message_template)
    for d in new_copy:
        if d.get("status_mapping"):
            d["text"] = d["status_mapping"][kwargs["status"]]

        if d.get("datetime"):
            d["datetime"] = Template(d["datetime"]).render(**kwargs)

        d["text"] = Template(d["text"]).render(**kwargs)
        d["title"] = Template(d["title"]).render(**kwargs)

        if d.get("title_link"):
            d["title_link"] = Template(d["title_link"]).render(**kwargs)

        if d.get("button_text"):
            d["button_text"] = Template(d["button_text"]).render(**kwargs)

        if d.get("button_value"):
            d["button_value"] = Template(d["button_value"]).render(**kwargs)

        data.append(d)
    return data
