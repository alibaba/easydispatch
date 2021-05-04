"""
.. module: dispatch.job.messaging
    :platform: Unix
    :copyright: (c) 2019 by Netflix Inc., see AUTHORS for more
    :license: Apache, see LICENSE for more details.
"""
import logging

from dispatch.config import (
    INCIDENT_NOTIFICATION_CONVERSATIONS,
    INCIDENT_NOTIFICATION_DISTRIBUTION_LISTS,
    INCIDENT_PLUGIN_CONTACT_SLUG,
    INCIDENT_PLUGIN_CONVERSATION_SLUG,
    INCIDENT_PLUGIN_EMAIL_SLUG,
    INCIDENT_RESOURCE_CONVERSATION_COMMANDS_REFERENCE_DOCUMENT,
    INCIDENT_RESOURCE_FAQ_DOCUMENT,
    INCIDENT_RESOURCE_INVESTIGATION_DOCUMENT,
    INCIDENT_PLUGIN_DOCUMENT_RESOLVER_SLUG,
)
from dispatch.database import SessionLocal
from dispatch.enums import Visibility
from dispatch.job import service as job_service
from dispatch.job.enums import JobPlanningStatus
from dispatch.job.models import Job, JobRead
from dispatch.messaging import (
    INCIDENT_COMMANDER,
    INCIDENT_COMMANDER_READDED_NOTIFICATION,
    INCIDENT_NAME,
    INCIDENT_NAME_WITH_ENGAGEMENT,
    INCIDENT_NEW_ROLE_NOTIFICATION,
    INCIDENT_NOTIFICATION,
    INCIDENT_NOTIFICATION_COMMON,
    INCIDENT_PARTICIPANT_SUGGESTED_READING_ITEM,
    INCIDENT_PARTICIPANT_WELCOME_MESSAGE,
    INCIDENT_PRIORITY_CHANGE,
    INCIDENT_RESOURCES_MESSAGE,
    INCIDENT_REVIEW_DOCUMENT,
    INCIDENT_STATUS_CHANGE,
    INCIDENT_TYPE_CHANGE,
    MessageType,
)
from dispatch.participant import service as participant_service
from dispatch.participant_role import service as participant_role_service
from dispatch.plugins.base import plugins


log = logging.getLogger(__name__)


def get_suggested_documents(db_session, job_type: str, priority: str, description: str):
    """Get additional job documents based on priority, type, and description."""
    p = plugins.get(INCIDENT_PLUGIN_DOCUMENT_RESOLVER_SLUG)
    documents = p.get(job_type, priority, description, db_session=db_session)
    return documents


def send_welcome_ephemeral_message_to_participant(
    participant_email: str, job_id: int, db_session: SessionLocal
):
    """Sends an ephemeral message to the participant."""
    # we load the job instance
    job = job_service.get(db_session=db_session, job_id=job_id)

    # we send the ephemeral message
    convo_plugin = plugins.get(INCIDENT_PLUGIN_CONVERSATION_SLUG)
    convo_plugin.send_ephemeral(
        job.conversation.channel_id,
        participant_email,
        "Job Welcome Message",
        INCIDENT_PARTICIPANT_WELCOME_MESSAGE,
        MessageType.job_participant_welcome,
        name=job.name,
        title=job.job_code,
        status=job.planning_status,
        type=job.job_type.name,
        type_description=job.job_type.description,
        priority=job.job_priority.name,
        priority_description=job.job_priority.description,
        commander_fullname=job.commander.name,
        commander_weblink=job.commander.weblink,
        document_weblink=job.job_document.weblink,
        storage_weblink=job.storage.weblink,
        ticket_weblink=job.ticket.weblink,
        faq_weblink=job.job_faq.weblink,
        conference_weblink=job.conference.weblink,
        conference_challenge=job.conference.conference_challenge,
        conversation_commands_reference_document_weblink=job.job_conversation_commands_reference_document.weblink,
    )

    log.debug(f"Welcome ephemeral message sent to {participant_email}.")


def send_welcome_email_to_participant(
    participant_email: str, job_id: int, db_session: SessionLocal
):
    """Sends a welcome email to the participant."""
    # we load the job instance
    job = job_service.get(db_session=db_session, job_id=job_id)

    email_plugin = plugins.get(INCIDENT_PLUGIN_EMAIL_SLUG)
    email_plugin.send(
        participant_email,
        INCIDENT_PARTICIPANT_WELCOME_MESSAGE,
        MessageType.job_participant_welcome,
        name=job.name,
        title=job.job_code,
        status=job.planning_status,
        type=job.job_type.name,
        type_description=job.job_type.description,
        priority=job.job_priority.name,
        priority_description=job.job_priority.description,
        commander_fullname=job.commander.name,
        commander_weblink=job.commander.weblink,
        document_weblink=job.job_document.weblink,
        storage_weblink=job.storage.weblink,
        ticket_weblink=job.ticket.weblink,
        faq_weblink=job.job_faq.weblink,
        conference_weblink=job.conference.weblink,
        conference_challenge=job.conference.conference_challenge,
        conversation_commands_reference_document_weblink=job.job_conversation_commands_reference_document.weblink,
        contact_fullname=job.commander.name,
        contact_weblink=job.commander.weblink,
    )

    log.debug(f"Welcome email sent to {participant_email}.")


def send_job_welcome_participant_messages(
    participant_email: str, job_id: int, db_session: SessionLocal
):
    """Sends welcome messages to the participant."""
    # we send the welcome ephemeral message
    send_welcome_ephemeral_message_to_participant(participant_email, job_id, db_session)

    # we send the welcome email
    send_welcome_email_to_participant(participant_email, job_id, db_session)

    log.debug(f"Welcome participant messages sent {participant_email}.")


def send_job_suggested_reading_messages(
    participant_email: str, job_id: int, db_session: SessionLocal
):
    """Sends a suggested reading message to a participant."""
    job = job_service.get(db_session=db_session, job_id=job_id)

    suggested_documents = get_suggested_documents(
        db_session, job.job_type, job.job_priority, job.description
    )

    if suggested_documents:
        # we send the ephemeral message
        convo_plugin = plugins.get(INCIDENT_PLUGIN_CONVERSATION_SLUG)
        convo_plugin.send_ephemeral(
            job.conversation.channel_id,
            participant_email,
            "Suggested Reading",
            [INCIDENT_PARTICIPANT_SUGGESTED_READING_ITEM],
            MessageType.job_participant_suggested_reading,
            items=[i.__dict__ for i in suggested_documents],  # plugin deals with dicts
        )

        log.debug(f"Suggested reading ephemeral message sent to {participant_email}.")


def send_job_status_notifications(job: Job, db_session: SessionLocal):
    """Sends job status notifications to conversations and distribution lists."""
    notification_text = "Job Notification"
    notification_type = MessageType.job_notification
    message_template = INCIDENT_NOTIFICATION.copy()

    # we send status notifications to conversations
    convo_plugin = plugins.get(INCIDENT_PLUGIN_CONVERSATION_SLUG)

    if job.planning_status != JobPlanningStatus.closed:
        message_template.insert(0, INCIDENT_NAME_WITH_ENGAGEMENT)
    else:
        message_template.insert(0, INCIDENT_NAME)

    for conversation in INCIDENT_NOTIFICATION_CONVERSATIONS:
        convo_plugin.send(
            conversation,
            notification_text,
            message_template,
            notification_type,
            name=job.name,
            title=job.job_code,
            status=job.planning_status,
            priority=job.job_priority.name,
            priority_description=job.job_priority.description,
            type=job.job_type.name,
            type_description=job.job_type.description,
            commander_fullname=job.commander.name,
            commander_weblink=job.commander.weblink,
            document_weblink=job.job_document.weblink,
            storage_weblink=job.storage.weblink,
            ticket_weblink=job.ticket.weblink,
            faq_weblink=job.job_faq.weblink,
            job_id=job.id,
        )

    # we send status notifications to distribution lists
    email_plugin = plugins.get(INCIDENT_PLUGIN_EMAIL_SLUG)
    for distro in INCIDENT_NOTIFICATION_DISTRIBUTION_LISTS:
        email_plugin.send(
            distro,
            message_template,
            notification_type,
            name=job.name,
            title=job.job_code,
            status=job.planning_status,
            type=job.job_type.name,
            type_description=job.job_type.description,
            priority=job.job_priority.name,
            priority_description=job.job_priority.description,
            commander_fullname=job.commander.name,
            commander_weblink=job.commander.weblink,
            document_weblink=job.job_document.weblink,
            storage_weblink=job.storage.weblink,
            ticket_weblink=job.ticket.weblink,
            faq_weblink=job.job_faq.weblink,
            job_id=job.id,
            contact_fullname=job.commander.name,
            contact_weblink=job.commander.weblink,
        )

    log.debug("Job status notifications sent.")


def send_job_notifications(job: Job, db_session: SessionLocal):
    """Sends all job notifications."""
    # we send the job status notifications
    send_job_status_notifications(job, db_session)

    log.debug("Job notifications sent.")


def send_job_update_notifications(job: Job, previous_job: JobRead):
    """Sends notifications about job changes."""
    notification_text = "Job Notification"
    notification_type = MessageType.job_notification
    notification_template = INCIDENT_NOTIFICATION_COMMON.copy()

    change = False
    if previous_job.planning_status != job.planning_status:
        change = True
        notification_template.append(INCIDENT_STATUS_CHANGE)

    if previous_job.job_type.name != job.job_type.name:
        change = True
        notification_template.append(INCIDENT_TYPE_CHANGE)

    if previous_job.job_priority.name != job.job_priority.name:
        change = True
        notification_template.append(INCIDENT_PRIORITY_CHANGE)

    if not change:
        # we don't need to notify
        log.debug("Job change notifications not sent.")
        return

    notification_template.append(INCIDENT_COMMANDER)
    convo_plugin = plugins.get(INCIDENT_PLUGIN_CONVERSATION_SLUG)

    # we send an update to the job conversation
    job_conversation_notification_template = notification_template.copy()
    job_conversation_notification_template.insert(0, INCIDENT_NAME)

    # we can't send messages to closed channels
    if job.planning_status != JobPlanningStatus.closed:
        convo_plugin.send(
            job.conversation.channel_id,
            notification_text,
            job_conversation_notification_template,
            notification_type,
            name=job.name,
            ticket_weblink=job.ticket.weblink,
            title=job.job_code,
            job_type_old=previous_job.job_type.name,
            job_type_new=job.job_type.name,
            job_priority_old=previous_job.job_priority.name,
            job_priority_new=job.job_priority.name,
            job_status_old=previous_job.planning_status.value,
            job_status_new=job.planning_status,
            commander_fullname=job.commander.name,
            commander_weblink=job.commander.weblink,
        )

    if job.visibility == Visibility.open:
        notification_conversation_notification_template = notification_template.copy()
        if job.planning_status != JobPlanningStatus.closed:
            notification_conversation_notification_template.insert(0, INCIDENT_NAME_WITH_ENGAGEMENT)
        else:
            notification_conversation_notification_template.insert(0, INCIDENT_NAME)

        # we send an update to the job notification conversations
        for conversation in INCIDENT_NOTIFICATION_CONVERSATIONS:
            convo_plugin.send(
                conversation,
                notification_text,
                notification_conversation_notification_template,
                notification_type,
                name=job.name,
                ticket_weblink=job.ticket.weblink,
                title=job.job_code,
                job_id=job.id,
                job_type_old=previous_job.job_type.name,
                job_type_new=job.job_type.name,
                job_priority_old=previous_job.job_priority.name,
                job_priority_new=job.job_priority.name,
                job_status_old=previous_job.planning_status.value,
                job_status_new=job.planning_status,
                commander_fullname=job.commander.name,
                commander_weblink=job.commander.weblink,
            )

        # we send an update to the job notification distribution lists
        email_plugin = plugins.get(INCIDENT_PLUGIN_EMAIL_SLUG)
        for distro in INCIDENT_NOTIFICATION_DISTRIBUTION_LISTS:
            email_plugin.send(
                distro,
                notification_template,
                notification_type,
                name=job.name,
                title=job.job_code,
                status=job.planning_status,
                priority=job.job_priority.name,
                priority_description=job.job_priority.description,
                commander_fullname=job.commander.name,
                commander_weblink=job.commander.weblink,
                document_weblink=job.job_document.weblink,
                storage_weblink=job.storage.weblink,
                ticket_weblink=job.ticket.weblink,
                faq_weblink=job.job_faq.weblink,
                job_id=job.id,
                job_priority_old=previous_job.job_priority.name,
                job_priority_new=job.job_priority.name,
                job_type_old=previous_job.job_type.name,
                job_type_new=job.job_type.name,
                job_status_old=previous_job.planning_status.value,
                job_status_new=job.planning_status,
                contact_fullname=job.commander.name,
                contact_weblink=job.commander.weblink,
            )

    log.debug("Job update notifications sent.")


def send_job_participant_announcement_message(
    participant_email: str, job_id: int, db_session=SessionLocal
):
    """Announces a participant in the conversation."""
    notification_text = "New Job Participant"
    notification_type = MessageType.job_notification
    notification_template = []

    # we load the job instance
    job = job_service.get(db_session=db_session, job_id=job_id)

    participant = participant_service.get_by_job_id_and_email(
        db_session=db_session, job_id=job_id, code=participant_email
    )

    contact_plugin = plugins.get(INCIDENT_PLUGIN_CONTACT_SLUG)
    participant_info = contact_plugin.get(participant_email)

    participant_name = participant_info["fullname"]
    participant_team = participant_info["team"]
    participant_department = participant_info["department"]
    participant_location = participant_info["location"]
    participant_weblink = participant_info["weblink"]

    convo_plugin = plugins.get(INCIDENT_PLUGIN_CONVERSATION_SLUG)
    participant_avatar_url = convo_plugin.get_participant_avatar_url(participant_email)

    participant_active_roles = participant_role_service.get_all_active_roles(
        db_session=db_session, participant_id=participant.id
    )
    participant_roles = []
    for role in participant_active_roles:
        participant_roles.append(role.role)

    blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*{notification_text}*"}},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*Name:* <{participant_weblink}|{participant_name}>\n"
                    f"*Team*: {participant_team}, {participant_department}\n"
                    f"*Location*: {participant_location}\n"
                    f"*Job Role(s)*: {(', ').join(participant_roles)}\n"
                ),
            },
            "accessory": {
                "type": "image",
                "image_url": participant_avatar_url,
                "alt_text": participant_name,
            },
        },
    ]

    convo_plugin.send(
        job.conversation.channel_id,
        notification_text,
        notification_template,
        notification_type,
        blocks=blocks,
    )

    log.debug("Job participant announcement message sent.")


def send_job_commander_readded_notification(job_id: int, db_session: SessionLocal):
    """Sends a notification about re-adding the job commander to the conversation."""
    notification_text = "Job Notification"
    notification_type = MessageType.job_notification

    # we load the job instance
    job = job_service.get(db_session=db_session, job_id=job_id)

    convo_plugin = plugins.get(INCIDENT_PLUGIN_CONVERSATION_SLUG)
    convo_plugin.send(
        job.conversation.channel_id,
        notification_text,
        INCIDENT_COMMANDER_READDED_NOTIFICATION,
        notification_type,
        commander_fullname=job.commander.name,
    )

    log.debug("Job commander readded notification sent.")


def send_job_participant_has_role_ephemeral_message(
    assigner_email: str, assignee_contact_info: dict, assignee_role: str, job: Job
):
    """Sends an ephemeral message to the assigner to let them know that the assignee already has the role."""
    notification_text = "Job Assign Role Notification"

    convo_plugin = plugins.get(INCIDENT_PLUGIN_CONVERSATION_SLUG)
    convo_plugin.send_ephemeral(
        job.conversation.channel_id,
        assigner_email,
        notification_text,
        blocks=[
            {
                "type": "section",
                "text": {
                    "type": "plain_text",
                    "text": f"{assignee_contact_info['fullname']} already has the {assignee_role} role.",
                },
            }
        ],
    )

    log.debug("Job participant has role message sent.")


def send_job_participant_role_not_assigned_ephemeral_message(
    assigner_email: str, assignee_contact_info: dict, assignee_role: str, job: Job
):
    """Sends an ephemeral message to the assigner to let them know that we were not able to assign the role."""
    notification_text = "Job Assign Role Notification"

    convo_plugin = plugins.get(INCIDENT_PLUGIN_CONVERSATION_SLUG)
    convo_plugin.send_ephemeral(
        job.conversation.channel_id,
        assigner_email,
        notification_text,
        blocks=[
            {
                "type": "section",
                "text": {
                    "type": "plain_text",
                    "text": f"We were not able to assign the {assignee_role} role to {assignee_contact_info['fullname']}.",
                },
            }
        ],
    )

    log.debug("Job participant role not assigned message sent.")


def send_job_new_role_assigned_notification(
    assigner_contact_info: dict, assignee_contact_info: dict, assignee_role: str, job: Job
):
    """Notified the conversation about the new participant role."""
    notification_text = "Job Notification"
    notification_type = MessageType.job_notification

    convo_plugin = plugins.get(INCIDENT_PLUGIN_CONVERSATION_SLUG)
    convo_plugin.send(
        job.conversation.channel_id,
        notification_text,
        INCIDENT_NEW_ROLE_NOTIFICATION,
        notification_type,
        assigner_fullname=assigner_contact_info["fullname"],
        assignee_fullname=assignee_contact_info["fullname"],
        assignee_firstname=assignee_contact_info["fullname"].split(" ")[0],
        assignee_weblink=assignee_contact_info["weblink"],
        assignee_role=assignee_role,
    )

    log.debug("Job new role assigned message sent.")


def send_job_review_document_notification(conversation_id: str, review_document_weblink: str):
    """Sends the review document notification."""
    notification_text = "Job Notification"
    notification_type = MessageType.job_notification

    convo_plugin = plugins.get(INCIDENT_PLUGIN_CONVERSATION_SLUG)
    convo_plugin.send(
        conversation_id,
        notification_text,
        [INCIDENT_REVIEW_DOCUMENT],
        notification_type,
        review_document_weblink=review_document_weblink,
    )

    log.debug("Job review document notification sent.")


def send_job_resources_ephemeral_message_to_participant(
    user_id: str, job_id: int, db_session: SessionLocal
):
    """Sends the list of job resources to the participant via an ephemeral message."""
    # we load the job instance
    job = job_service.get(db_session=db_session, job_id=job_id)

    review_document_weblink = ""
    if job.job_review_document:
        review_document_weblink = job.job_review_document.weblink

    # we send the ephemeral message
    convo_plugin = plugins.get(INCIDENT_PLUGIN_CONVERSATION_SLUG)
    convo_plugin.send_ephemeral(
        job.conversation.channel_id,
        user_id,
        "Job Resources Message",
        INCIDENT_RESOURCES_MESSAGE,
        MessageType.job_resources_message,
        commander_fullname=job.commander.name,
        commander_weblink=job.commander.weblink,
        document_weblink=job.job_document.weblink,
        review_document_weblink=review_document_weblink,
        storage_weblink=job.storage.weblink,
        faq_weblink=job.job_faq.weblink,
        conversation_commands_reference_document_weblink=job.job_conversation_commands_reference_document.weblink,
        conference_weblink=job.conference.weblink,
    )

    log.debug(f"List of job resources sent to {user_id} via ephemeral message.")
