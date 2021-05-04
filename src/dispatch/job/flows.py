"""
.. module: dispatch.job.flows
    :platform: Unix
    :copyright: (c) 2019 by Netflix Inc., see AUTHORS for more
    :license: Apache, see LICENSE for more details.

.. moduleauthor:: Kevin Glisson <kglisson@netflix.com>
.. moduleauthor:: Marc Vilanova <mvilanova@netflix.com>
"""
import logging

from datetime import datetime
from typing import Any, List, Optional

from dispatch.config import (
    INCIDENT_CONVERSATION_COMMANDS_REFERENCE_DOCUMENT_ID,
    INCIDENT_DOCUMENT_INVESTIGATION_SHEET_ID,
    INCIDENT_FAQ_DOCUMENT_ID,
    INCIDENT_PLUGIN_CONTACT_SLUG,
    INCIDENT_PLUGIN_CONVERSATION_SLUG,
    INCIDENT_PLUGIN_CONFERENCE_SLUG,
    INCIDENT_PLUGIN_DOCUMENT_SLUG,
    INCIDENT_PLUGIN_GROUP_SLUG,
    INCIDENT_PLUGIN_PARTICIPANT_RESOLVER_SLUG,
    INCIDENT_PLUGIN_STORAGE_SLUG,
    INCIDENT_RESOURCE_CONVERSATION_COMMANDS_REFERENCE_DOCUMENT,
    INCIDENT_RESOURCE_FAQ_DOCUMENT,
    INCIDENT_RESOURCE_INCIDENT_REVIEW_DOCUMENT,
    INCIDENT_RESOURCE_INVESTIGATION_DOCUMENT,
    INCIDENT_RESOURCE_INVESTIGATION_SHEET,
    INCIDENT_RESOURCE_NOTIFICATIONS_GROUP,
    INCIDENT_RESOURCE_TACTICAL_GROUP,
    INCIDENT_STORAGE_ARCHIVAL_FOLDER_ID,
    INCIDENT_STORAGE_INCIDENT_REVIEW_FILE_ID,
    INCIDENT_STORAGE_RESTRICTED,
)
from dispatch.conference import service as conference_service
from dispatch.conference.models import ConferenceCreate
from dispatch.conversation import service as conversation_service
from dispatch.conversation.models import ConversationCreate
from dispatch.database import SessionLocal
from dispatch.decorators import background_task
from dispatch.event import service as event_service
from dispatch.group import service as group_service
from dispatch.group.models import GroupCreate
from dispatch.job import service as job_service
from dispatch.job.models import JobRead
from dispatch.worker import service as worker_service
from dispatch.participant import flows as participant_flows
from dispatch.participant import service as participant_service
from dispatch.participant.models import Participant
from dispatch.participant_role import flows as participant_role_flows
from dispatch.participant_role.models import ParticipantRoleType
from dispatch.plugin import service as plugin_service
from dispatch.plugins.base import plugins
from dispatch.report.enums import ReportTypes
from dispatch.report.messaging import send_job_report_reminder
from dispatch.service import service as service_service
from dispatch.storage import service as storage_service
from dispatch.ticket import service as ticket_service
from dispatch.ticket.models import TicketCreate

from .messaging import (
    send_job_update_notifications,
    send_job_commander_readded_notification,
    send_job_new_role_assigned_notification,
    send_job_notifications,
    send_job_participant_announcement_message,
    send_job_resources_ephemeral_message_to_participant,
    send_job_review_document_notification,
    send_job_welcome_participant_messages,
    send_job_suggested_reading_messages,
)
from .models import Job, JobPlanningStatus


log = logging.getLogger(__name__)


def get_job_participants(job: Job, db_session: SessionLocal):
    """Get additional job participants based on priority, type, and description."""
    p = plugins.get(INCIDENT_PLUGIN_PARTICIPANT_RESOLVER_SLUG)
    workers, team_contacts = p.get(
        job.job_type,
        job.job_priority,
        job.description,
        db_session=db_session,
    )

    event_service.log(
        db_session=db_session,
        source=p.job_code,
        description="Job participants resolved",
        job_id=job.id,
    )

    return workers, team_contacts


def create_job_ticket(job: Job, db_session: SessionLocal):
    """Create an external ticket for tracking."""
    plugin = plugin_service.get_active(db_session=db_session, plugin_type="ticket")

    title = job.job_code
    if job.visibility == Visibility.restricted:
        title = job.job_type.name

    job_type_plugin_metadata = job_type_service.get_by_name(
        db_session=db_session, name=job.job_type.name
    ).get_meta(plugin.slug)

    ticket = plugin.instance.create(
        job.id,
        title,
        job.job_type.name,
        job.job_priority.name,
        job.commander.code,
        job.reporter.code,
        job_type_plugin_metadata,
    )
    ticket.update({"resource_type": plugin.slug})

    event_service.log(
        db_session=db_session,
        source=plugin.job_code,
        description="External ticket created",
        job_id=job.id,
    )

    return ticket


def update_external_job_ticket(
    job: Job,
    db_session: SessionLocal,
):
    """Update external job ticket."""
    title = job.job_code
    description = job.description
    if job.visibility == Visibility.restricted:
        title = description = job.job_type.name

    plugin = plugin_service.get_active(db_session=db_session, plugin_type="ticket")

    job_type_plugin_metadata = job_type_service.get_by_name(
        db_session=db_session, name=job.job_type.name
    ).get_meta(plugin.slug)

    plugin.instance.update(
        job.ticket.resource_id,
        title,
        description,
        job.job_type.name,
        job.job_priority.name,
        job.planning_status.lower(),
        job.commander.code,
        job.reporter.code,
        job.conversation.weblink,
        job.job_document.weblink,
        job.storage.weblink,
        job.conference.weblink,
        job.cost,
        job_type_plugin_metadata=job_type_plugin_metadata,
    )

    log.debug("The external ticket has been updated.")


def create_participant_groups(
    job: Job,
    direct_participants: List[Any],
    indirect_participants: List[Any],
    db_session: SessionLocal,
):
    """Create external participant groups."""
    p = plugins.get(INCIDENT_PLUGIN_GROUP_SLUG)

    group_name = f"{job.name}"
    notification_group_name = f"{group_name}-notifications"

    direct_participant_emails = [x.code for x in direct_participants]
    tactical_group = p.create(
        group_name, direct_participant_emails
    )  # add participants to core group

    indirect_participant_emails = [x.code for x in indirect_participants]
    indirect_participant_emails.append(
        tactical_group["email"]
    )  # add all those already in the tactical group
    notification_group = p.create(notification_group_name, indirect_participant_emails)

    tactical_group.update(
        {"resource_type": INCIDENT_RESOURCE_TACTICAL_GROUP, "resource_id": tactical_group["id"]}
    )
    notification_group.update(
        {
            "resource_type": INCIDENT_RESOURCE_NOTIFICATIONS_GROUP,
            "resource_id": notification_group["id"],
        }
    )

    event_service.log(
        db_session=db_session,
        source=p.job_code,
        description="Tactical and notification groups created",
        job_id=job.id,
    )

    return tactical_group, notification_group


def delete_participant_groups(job: Job, db_session: SessionLocal):
    """Deletes the external participant groups."""
    # we get the tactical group
    tactical_group = group_service.get_by_job_id_and_resource_type(
        db_session=db_session,
        job_id=job.id,
        resource_type=INCIDENT_RESOURCE_TACTICAL_GROUP,
    )

    # we get the notifications group
    notifications_group = group_service.get_by_job_id_and_resource_type(
        db_session=db_session,
        job_id=job.id,
        resource_type=INCIDENT_RESOURCE_NOTIFICATIONS_GROUP,
    )

    p = plugins.get(INCIDENT_PLUGIN_GROUP_SLUG)
    p.delete(code=tactical_group.code)
    p.delete(code=notifications_group.code)

    event_service.log(
        db_session=db_session,
        source=p.job_code,
        description="Tactical and notification groups deleted",
        job_id=job.id,
    )


def create_conference(job: Job, participants: List[str], db_session: SessionLocal):
    """Create external conference room."""
    p = plugins.get(INCIDENT_PLUGIN_CONFERENCE_SLUG)
    conference = p.create(job.name, participants=participants)

    conference.update(
        {"resource_type": INCIDENT_PLUGIN_CONFERENCE_SLUG, "resource_id": conference["id"]}
    )

    event_service.log(
        db_session=db_session,
        source=p.job_code,
        description="Job conference created",
        job_id=job.id,
    )

    return conference


def delete_conference(job: Job, db_session: SessionLocal):
    """Deletes the conference."""
    conference = conference_service.get_by_job_id(db_session=db_session, job_id=job.id)
    p = plugins.get(INCIDENT_PLUGIN_CONFERENCE_SLUG)
    p.delete(conference.conference_id)

    event_service.log(
        db_session=db_session,
        source=p.job_code,
        description="Job conference deleted",
        job_id=job.id,
    )


def create_job_storage(job: Job, participant_group_emails: List[str], db_session: SessionLocal):
    """Create an external file store for job storage."""
    p = plugins.get(INCIDENT_PLUGIN_STORAGE_SLUG)
    storage = p.create(job.name, participant_group_emails)
    storage.update({"resource_type": INCIDENT_PLUGIN_STORAGE_SLUG, "resource_id": storage["id"]})

    event_service.log(
        db_session=db_session,
        source=p.job_code,
        description="Job storage created",
        job_id=job.id,
    )

    if INCIDENT_STORAGE_RESTRICTED:
        p.restrict(storage["resource_id"])
        event_service.log(
            db_session=db_session,
            source=p.job_code,
            description="Job storage restricted",
            job_id=job.id,
        )

    return storage


def archive_job_artifacts(job: Job, db_session: SessionLocal):
    """Archives artifacts in the job storage."""
    p = plugins.get(INCIDENT_PLUGIN_STORAGE_SLUG)
    p.archive(
        source_team_drive_id=job.storage.resource_id,
        dest_team_drive_id=INCIDENT_STORAGE_ARCHIVAL_FOLDER_ID,
        folder_name=job.name,
    )
    event_service.log(
        db_session=db_session,
        source=p.job_code,
        description="Job artifacts archived",
        job_id=job.id,
    )


def unrestrict_job_storage(job: Job, db_session: SessionLocal):
    """Unrestricts the job storage."""
    p = plugins.get(INCIDENT_PLUGIN_STORAGE_SLUG)
    p.unrestrict(job.storage.resource_id)

    event_service.log(
        db_session=db_session,
        source=p.job_code,
        description="Job storage unrestricted",
        job_id=job.id,
    )


def create_collaboration_documents(job: Job, db_session: SessionLocal):
    """Create external collaboration document."""
    p = plugins.get(INCIDENT_PLUGIN_STORAGE_SLUG)

    document_name = f"{job.name} - Job Document"

    # TODO can we make move and copy in one api call? (kglisson)
    document = p.copy_file(
        job.storage.resource_id,
        job.job_type.template_document.resource_id,
        document_name,
    )
    p.move_file(job.storage.resource_id, document["id"])

    # NOTE this should be optional
    if INCIDENT_DOCUMENT_INVESTIGATION_SHEET_ID:
        sheet_name = f"{job.name} - Job Tracking Sheet"
        sheet = p.copy_file(
            job.storage.resource_id, INCIDENT_DOCUMENT_INVESTIGATION_SHEET_ID, sheet_name
        )
        p.move_file(job.storage.resource_id, sheet["id"])

    p.create_file(job.storage.resource_id, "logs")
    p.create_file(job.storage.resource_id, "screengrabs")

    # TODO this logic should probably be pushed down into the plugins i.e. making them return
    # the fields we expect instead of re-mapping. (kglisson)
    document.update(
        {
            "name": document_name,
            "resource_type": INCIDENT_RESOURCE_INVESTIGATION_DOCUMENT,
            "resource_id": document["id"],
        }
    )
    sheet.update(
        {
            "name": sheet_name,
            "resource_type": INCIDENT_RESOURCE_INVESTIGATION_SHEET,
            "resource_id": sheet["id"],
        }
    )

    event_service.log(
        db_session=db_session,
        source=p.job_code,
        description="Job investigation document and sheet created",
        job_id=job.id,
    )

    return document, sheet


def create_conversation(job: Job, participants: List[str], db_session: SessionLocal):
    """Create external communication conversation."""
    # we create the conversation
    p = plugins.get(INCIDENT_PLUGIN_CONVERSATION_SLUG)
    conversation = p.create(job.name, participants)

    conversation.update(
        {"resource_type": INCIDENT_PLUGIN_CONVERSATION_SLUG, "resource_id": conversation["name"]}
    )

    event_service.log(
        db_session=db_session,
        source=p.job_code,
        description="Job conversation created",
        job_id=job.id,
    )

    return conversation


def set_conversation_topic(job: Job):
    """Sets the conversation topic."""
    convo_plugin = plugins.get(INCIDENT_PLUGIN_CONVERSATION_SLUG)
    conversation_topic = f":helmet_with_white_cross: {job.commander.name} - Type: {job.job_type.name} - Priority: {job.job_priority.name} - Status: {job.planning_status}"
    convo_plugin.set_topic(job.conversation.channel_id, conversation_topic)


def update_document(
    document_id: str,
    name: str,
    priority: str,
    status: str,
    type: str,
    title: str,
    description: str,
    commander_fullname: str,
    conversation_weblink: str,
    document_weblink: str,
    storage_weblink: str,
    ticket_weblink: str,
    conference_weblink: str = None,
    conference_challenge: str = None,
):
    """Update external collaboration document."""
    p = plugins.get(INCIDENT_PLUGIN_DOCUMENT_SLUG)
    p.update(
        document_id,
        name=name,
        priority=priority,
        status=status,
        type=type,
        title=title,
        description=description,
        commander_fullname=commander_fullname,
        conversation_weblink=conversation_weblink,
        document_weblink=document_weblink,
        storage_weblink=storage_weblink,
        ticket_weblink=ticket_weblink,
        conference_weblink=conference_weblink,
        conference_challenge=conference_challenge,
    )


def add_participant_to_conversation(participant_email: str, job_id: int, db_session: SessionLocal):
    """Adds a participant to the conversation."""
    # we load the job instance
    job = job_service.get(db_session=db_session, job_id=job_id)

    convo_plugin = plugins.get(INCIDENT_PLUGIN_CONVERSATION_SLUG)
    convo_plugin.add(job.conversation.channel_id, [participant_email])


@background_task
def add_participant_to_tactical_group(user_email: str, job_id: int, db_session=None):
    """Adds participant to the tactical group."""
    # we get the tactical group
    tactical_group = group_service.get_by_job_id_and_resource_type(
        db_session=db_session,
        job_id=job_id,
        resource_type=INCIDENT_RESOURCE_TACTICAL_GROUP,
    )

    p = plugins.get(INCIDENT_PLUGIN_GROUP_SLUG)
    p.add(tactical_group.code, [user_email])


# TODO create some ability to checkpoint
# We could use the model itself as the checkpoint, commiting resources as we go
# Then checking for the existence of those resources before creating them for
# this job.
@background_task
def job_create_flow(*, job_id: int, checkpoint: str = None, db_session=None):
    """Creates all resources required for new jobs."""
    job = job_service.get(db_session=db_session, job_id=job_id)

    # get the job participants based on job type and priority
    worker_participants, team_participants = get_job_participants(job, db_session)

    # add workers to job
    for worker in worker_participants:
        participant_flows.add_participant(
            user_code=worker.code, job_id=job.id, db_session=db_session
        )

    event_service.log(
        db_session=db_session,
        source="Dispatch Core App",
        description="Job participants added to job",
        job_id=job.id,
    )

    # create the job ticket
    ticket = create_job_ticket(job, db_session)
    job.ticket = ticket_service.create(db_session=db_session, ticket_in=TicketCreate(**ticket))

    event_service.log(
        db_session=db_session,
        source="Dispatch Core App",
        description="External ticket added to job",
        job_id=job.id,
    )

    # we set the job name
    name = ticket["resource_id"]
    job.name = name

    # we create the participant groups (tactical and notification)
    try:
        worker_participants = [x.worker for x in job.participants]
        tactical_group, notification_group = create_participant_groups(
            job, worker_participants, team_participants, db_session
        )

        for g in [tactical_group, notification_group]:
            group_in = GroupCreate(
                name=g["name"],
                code=g["email"],
                resource_type=g["resource_type"],
                resource_id=g["resource_id"],
                weblink=g["weblink"],
            )
            job.groups.append(group_service.create(db_session=db_session, group_in=group_in))

        event_service.log(
            db_session=db_session,
            source="Dispatch Core App",
            description="Tactical and notification groups added to job",
            job_id=job.id,
        )

        # we create storage resource
        storage = create_job_storage(
            job, [tactical_group["email"], notification_group["email"]], db_session
        )
        job.storage = storage_service.create(
            db_session=db_session,
            resource_id=storage["resource_id"],
            resource_type=storage["resource_type"],
            weblink=storage["weblink"],
        )

        event_service.log(
            db_session=db_session,
            source="Dispatch Core App",
            description="Storage added to job",
            job_id=job.id,
        )

        # we create the job documents
        job_document, job_sheet = create_collaboration_documents(job, db_session)

        faq_document = {
            "name": "Job FAQ",
            "resource_id": INCIDENT_FAQ_DOCUMENT_ID,
            "weblink": f"https://docs.google.com/document/d/{INCIDENT_FAQ_DOCUMENT_ID}",
            "resource_type": INCIDENT_RESOURCE_FAQ_DOCUMENT,
        }

        conversation_commands_reference_document = {
            "name": "Job Conversation Commands Reference Document",
            "resource_id": INCIDENT_CONVERSATION_COMMANDS_REFERENCE_DOCUMENT_ID,
            "weblink": f"https://docs.google.com/document/d/{INCIDENT_CONVERSATION_COMMANDS_REFERENCE_DOCUMENT_ID}",
            "resource_type": INCIDENT_RESOURCE_CONVERSATION_COMMANDS_REFERENCE_DOCUMENT,
        }

        for d in [
            job_document,
            job_sheet,
            faq_document,
            conversation_commands_reference_document,
        ]:
            document_in = DocumentCreate(
                name=d["name"],
                resource_id=d["resource_id"],
                resource_type=d["resource_type"],
                weblink=d["weblink"],
            )
            job.documents.append(
                document_service.create(db_session=db_session, document_in=document_in)
            )

        event_service.log(
            db_session=db_session,
            source="Dispatch Core App",
            description="Documents added to job",
            job_id=job.id,
        )

        conference = create_conference(job, [tactical_group["email"]], db_session)

        conference_in = ConferenceCreate(
            resource_id=conference["resource_id"],
            resource_type=conference["resource_type"],
            weblink=conference["weblink"],
            conference_id=conference["id"],
            conference_challenge=conference["challenge"],
        )
        job.conference = conference_service.create(
            db_session=db_session, conference_in=conference_in
        )

        event_service.log(
            db_session=db_session,
            source="Dispatch Core App",
            description="Conference added to job",
            job_id=job.id,
        )

        # we create the conversation for real-time communications
        participant_emails = [x.worker.code for x in job.participants]
        conversation = create_conversation(job, participant_emails, db_session)

        conversation_in = ConversationCreate(
            resource_id=conversation["resource_id"],
            resource_type=conversation["resource_type"],
            weblink=conversation["weblink"],
            channel_id=conversation["id"],
        )
        job.conversation = conversation_service.create(
            db_session=db_session, conversation_in=conversation_in
        )

        event_service.log(
            db_session=db_session,
            source="Dispatch Core App",
            description="Conversation added to job",
            job_id=job.id,
        )

    except Exception as e:
        log.warn("failed to create ... , job_id ={}".format(job_id), e)

    db_session.add(job)
    db_session.commit()
    try:

        # we set the conversation topic
        set_conversation_topic(job)

        # we update the job ticket
        update_external_job_ticket(job, db_session)

        # we update the investigation document
        update_document(
            job_document["id"],
            job.name,
            job.job_priority.name,
            job.planning_status,
            job.job_type.name,
            job.job_code,
            job.description,
            job.commander.name,
            job.conversation.weblink,
            job_document["weblink"],
            job.storage.weblink,
            job.ticket.weblink,
            job.conference.weblink,
            job.conference.conference_challenge,
        )

        for participant in job.participants:
            # we announce the participant in the conversation
            send_job_participant_announcement_message(participant.worker.code, job.id, db_session)

            # we send the welcome messages to the participant
            send_job_welcome_participant_messages(participant.worker.code, job.id, db_session)

            send_job_suggested_reading_messages(participant.worker.code, job.id, db_session)

        event_service.log(
            db_session=db_session,
            source="Dispatch Core App",
            description="Participants announced and welcome messages sent",
            job_id=job.id,
        )

        if job.visibility == Visibility.open:
            send_job_notifications(job, db_session)
            event_service.log(
                db_session=db_session,
                source="Dispatch Core App",
                description="Job notifications sent",
                job_id=job.id,
            )

    except Exception as e:
        log.warn("failed to create more ... , job_id ={}".format(job_id), e)


@background_task
def job_active_flow(job_id: int, command: Optional[dict] = None, db_session=None):
    """Runs the job active flow."""
    # we load the job instance
    job = job_service.get(db_session=db_session, job_id=job_id)

    # we remind the job commander to write a tactical report
    send_job_report_reminder(job, ReportTypes.tactical_report)

    # we update the status of the external ticket
    update_external_job_ticket(job, db_session)


@background_task
def job_stable_flow(job_id: int, command: Optional[dict] = None, db_session=None):
    """Runs the job stable flow."""
    # we load the job instance
    job = job_service.get(db_session=db_session, job_id=job_id)

    # we set the stable time
    job.stable_at = datetime.utcnow()

    # we remind the job commander to write a tactical report
    send_job_report_reminder(job, ReportTypes.tactical_report)

    # we update the external ticket
    update_external_job_ticket(job, db_session)

    if not job.job_review_document:
        storage_plugin = plugins.get(INCIDENT_PLUGIN_STORAGE_SLUG)

        # we create a copy of the job review document template and we move it to the job storage
        job_review_document_name = f"{job.name} - Post Job Review Document"
        job_review_document = storage_plugin.copy_file(
            team_drive_id=job.storage.resource_id,
            file_id=INCIDENT_STORAGE_INCIDENT_REVIEW_FILE_ID,
            name=job_review_document_name,
        )

        job_review_document.update(
            {
                "name": job_review_document_name,
                "resource_type": INCIDENT_RESOURCE_INCIDENT_REVIEW_DOCUMENT,
            }
        )

        storage_plugin.move_file(
            new_team_drive_id=job.storage.resource_id, file_id=job_review_document["id"]
        )

        event_service.log(
            db_session=db_session,
            source=storage_plugin.job_code,
            description="Job review document added to storage",
            job_id=job.id,
        )

        document_in = DocumentCreate(
            name=job_review_document["name"],
            resource_id=job_review_document["id"],
            resource_type=job_review_document["resource_type"],
            weblink=job_review_document["weblink"],
        )
        job.documents.append(
            document_service.create(db_session=db_session, document_in=document_in)
        )

        event_service.log(
            db_session=db_session,
            source="Dispatch Core App",
            description="Job review document added to job",
            job_id=job.id,
        )

        # we update the job review document
        update_document(
            job_review_document["id"],
            job.name,
            job.job_priority.name,
            job.planning_status,
            job.job_type.name,
            job.job_code,
            job.description,
            job.commander.name,
            job.conversation.weblink,
            job.job_document.weblink,
            job.storage.weblink,
            job.ticket.weblink,
        )

        # we send a notification about the job review document to the conversation
        send_job_review_document_notification(
            job.conversation.channel_id, job_review_document["weblink"]
        )

    db_session.add(job)
    db_session.commit()


@background_task
def job_closed_flow(job_id: int, command: Optional[dict] = None, db_session=None):
    """Runs the job closed flow."""
    # we load the job instance
    job = job_service.get(db_session=db_session, job_id=job_id)

    # we set the closed time
    job.closed_at = datetime.utcnow()

    # we archive the conversation
    convo_plugin = plugins.get(INCIDENT_PLUGIN_CONVERSATION_SLUG)
    convo_plugin.archive(job.conversation.channel_id)

    # we update the external ticket
    update_external_job_ticket(job, db_session)

    if job.visibility == Visibility.open:
        if INCIDENT_STORAGE_RESTRICTED:
            # we unrestrict the storage
            unrestrict_job_storage(job, db_session)

        # we archive the artifacts in the storage
        archive_job_artifacts(job, db_session)

        # we delete the tactical and notification groups
        delete_participant_groups(job, db_session)

    # we delete the conference
    delete_conference(job, db_session)

    db_session.add(job)
    db_session.commit()


@background_task
def job_update_flow(
    user_email: str, job_id: int, previous_job: JobRead, notify=True, db_session=None
):
    """Runs the job update flow."""
    # we load the job instance
    job = job_service.get(db_session=db_session, job_id=job_id)

    # we load the worker
    worker = worker_service.get_by_code(db_session=db_session, code=user_email)

    conversation_topic_change = False
    if previous_job.job_code != job.job_code:
        event_service.log(
            db_session=db_session,
            source="Job Participant",
            description=f'{worker.name} changed the job title to "{job.job_code}"',
            job_id=job.id,
            worker_id=worker.id,
        )

    if previous_job.description != job.description:
        event_service.log(
            db_session=db_session,
            source="Job Participant",
            description=f"{worker.name} changed the job description",
            details={"description": job.description},
            job_id=job.id,
            worker_id=worker.id,
        )

    if previous_job.job_type.name != job.job_type.name:
        conversation_topic_change = True

        event_service.log(
            db_session=db_session,
            source="Job Participant",
            description=f"{worker.name} changed the job type to {job.job_type.name}",
            job_id=job.id,
            worker_id=worker.id,
        )

    if previous_job.job_priority.name != job.job_priority.name:
        conversation_topic_change = True

        event_service.log(
            db_session=db_session,
            source="Job Participant",
            description=f"{worker.name} changed the job priority to {job.job_priority.name}",
            job_id=job.id,
            worker_id=worker.id,
        )

    if previous_job.planning_status.value != job.planning_status:
        conversation_topic_change = True

        event_service.log(
            db_session=db_session,
            source="Job Participant",
            description=f"{worker.name} marked the job as {job.planning_status}",
            job_id=job.id,
            worker_id=worker.id,
        )


@background_task
def job_assign_role_flow(
    assigner_email: str, job_id: int, assignee_email: str, assignee_role: str, db_session=None
):
    """Runs the job participant role assignment flow."""
    # we resolve the assigner and assignee's contact information
    contact_plugin = plugins.get(INCIDENT_PLUGIN_CONTACT_SLUG)
    assigner_contact_info = contact_plugin.get(assigner_email)
    assignee_contact_info = contact_plugin.get(assignee_email)

    # we load the job instance
    job = job_service.get(db_session=db_session, job_id=job_id)

    # we get the participant object for the assignee
    assignee_participant = participant_service.get_by_job_id_and_email(
        db_session=db_session, job_id=job.id, code=assignee_contact_info["email"]
    )

    if not assignee_participant:
        # The assignee is not a participant. We add them to the job
        job_add_or_reactivate_participant_flow(assignee_email, job.id, db_session=db_session)

    # we run the participant assign role flow
    result = participant_role_flows.assign_role_flow(
        job.id, assignee_contact_info, assignee_role, db_session
    )

    if result == "assignee_has_role":
        # NOTE: This is disabled until we can determine the source of the caller
        # we let the assigner know that the assignee already has this role
        # send_job_participant_has_role_ephemeral_message(
        #    assigner_email, assignee_contact_info, assignee_role, job
        # )
        return

    if result == "role_not_assigned":
        # NOTE: This is disabled until we can determine the source of the caller
        # we let the assigner know that we were not able to assign the role
        # send_job_participant_role_not_assigned_ephemeral_message(
        #    assigner_email, assignee_contact_info, assignee_role, job
        # )
        return

    if assignee_role != ParticipantRoleType.participant:
        # we send a notification to the job conversation
        send_job_new_role_assigned_notification(
            assigner_contact_info, assignee_contact_info, assignee_role, job
        )

    if assignee_role == ParticipantRoleType.job_commander:
        # we update the conversation topic
        set_conversation_topic(job)

        # we update the external ticket
        update_external_job_ticket(job, db_session)


@background_task
def job_engage_oncall_flow(
    user_id: str, user_email: str, job_id: int, action: dict, db_session=None
):
    """Runs the job engage oncall flow."""
    oncall_service_id = action["submission"]["oncall_service_id"]
    page = action["submission"]["page"]

    # we load the job instance
    job = job_service.get(db_session=db_session, job_id=job_id)

    # we resolve the oncall service
    oncall_service = service_service.get_by_external_id(
        db_session=db_session, external_id=oncall_service_id
    )
    oncall_plugin = plugins.get(oncall_service.type)
    oncall_email = oncall_plugin.get(service_id=oncall_service_id)

    # we add the oncall to the job
    job_add_or_reactivate_participant_flow(oncall_email, job.id, db_session=db_session)

    event_service.log(
        db_session=db_session,
        source=oncall_plugin.job_code,
        description=f"{user_email} engages oncall service {oncall_service.name}",
        job_id=job.id,
    )

    if page == "Yes":
        # we page the oncall
        oncall_plugin.page(oncall_service_id, job.name, job.job_code, job.description)

        event_service.log(
            db_session=db_session,
            source=oncall_plugin.job_code,
            description=f"{oncall_service.name} on-call paged",
            job_id=job.id,
        )


@background_task
def job_add_or_reactivate_participant_flow(
    user_email: str,
    job_id: int,
    role: ParticipantRoleType = None,
    event: dict = None,
    db_session=None,
) -> Participant:
    """Runs the add or reactivate job participant flow."""
    participant = participant_service.get_by_job_id_and_email(
        db_session=db_session, job_id=job_id, code=user_email
    )

    if participant:
        if participant.is_active:
            log.debug(f"{user_email} is already an active participant.")
        else:
            # we reactivate the participant
            reactivated = participant_flows.reactivate_participant(user_email, job_id, db_session)

            if reactivated:
                # we add the participant to the conversation
                add_participant_to_conversation(user_email, job_id, db_session)

                # we announce the participant in the conversation
                send_job_participant_announcement_message(user_email, job_id, db_session)

                # we send the welcome messages to the participant
                send_job_welcome_participant_messages(user_email, job_id, db_session)
    else:
        # we add the participant to the job
        participant = participant_flows.add_participant(user_email, job_id, db_session, role=role)

        # we add the participant to the tactical group
        add_participant_to_tactical_group(user_email, job_id)

        # we add the participant to the conversation
        add_participant_to_conversation(user_email, job_id, db_session)

        # we announce the participant in the conversation
        send_job_participant_announcement_message(user_email, job_id, db_session)

        # we send the welcome messages to the participant
        send_job_welcome_participant_messages(user_email, job_id, db_session)

        # we send a suggested reading message to the participant
        send_job_suggested_reading_messages(user_email, job_id, db_session)

    return participant


@background_task
def job_remove_participant_flow(user_email: str, job_id: int, event: dict = None, db_session=None):
    """Runs the remove participant flow."""
    # we load the job instance
    job = job_service.get(db_session=db_session, job_id=job_id)

    if user_email == job.commander.code:
        # we add the job commander to the conversation again
        add_participant_to_conversation(user_email, job_id, db_session)

        # we send a notification to the channel
        send_job_commander_readded_notification(job_id, db_session)
    else:
        # we remove the participant from the job
        participant_flows.remove_participant(user_email, job_id, db_session)


@background_task
def job_list_resources_flow(job_id: int, command: Optional[dict] = None, db_session=None):
    """Runs the list job resources flow."""
    # we send the list of resources to the participant
    send_job_resources_ephemeral_message_to_participant(command["user_id"], job_id, db_session)
