import logging

from datetime import datetime
from schedule import every
from sqlalchemy import func

from dispatch.config import (
    INCIDENT_PLUGIN_CONVERSATION_SLUG,
    INCIDENT_ONCALL_SERVICE_ID,
    INCIDENT_NOTIFICATION_CONVERSATIONS,
    INCIDENT_PLUGIN_TICKET_SLUG,
    INCIDENT_PLUGIN_STORAGE_SLUG,
)
from dispatch.conversation.enums import ConversationButtonActions
from dispatch.decorators import background_task
from dispatch.enums import Visibility
from dispatch.extensions import sentry_sdk
from dispatch.worker import service as worker_service
from dispatch.messaging import (
    INCIDENT_DAILY_SUMMARY_ACTIVE_INCIDENTS_DESCRIPTION,
    INCIDENT_DAILY_SUMMARY_DESCRIPTION,
    INCIDENT_DAILY_SUMMARY_NO_ACTIVE_INCIDENTS_DESCRIPTION,
    INCIDENT_DAILY_SUMMARY_NO_STABLE_CLOSED_INCIDENTS_DESCRIPTION,
    INCIDENT_DAILY_SUMMARY_STABLE_CLOSED_INCIDENTS_DESCRIPTION,
)
from dispatch.nlp import build_phrase_matcher, build_term_vocab, extract_terms_from_text
from dispatch.plugins.base import plugins
from dispatch.scheduler import scheduler
from dispatch.service import service as service_service
from dispatch.tag import service as tag_service
from dispatch.tag.models import Tag

from .enums import LocationStatus
from .flows import update_external_location_ticket
from .service import calculate_cost, get_all, get_all_by_status, get_all_last_x_hours_by_status


log = logging.getLogger(__name__)


@scheduler.add(every(1).hours, name="location-tagger")
@background_task
def auto_tagger(db_session):
    """Attempts to take existing tags and associate them with locations."""
    tags = tag_service.get_all(db_session=db_session).all()
    log.debug(f"Fetched {len(tags)} tags from database.")

    tag_strings = [t.name.lower() for t in tags if t.discoverable]
    phrases = build_term_vocab(tag_strings)
    matcher = build_phrase_matcher("dispatch-tag", phrases)

    p = plugins.get(
        INCIDENT_PLUGIN_STORAGE_SLUG
    )  # this may need to be refactored if we support multiple document types

    for location in get_all(db_session=db_session).all():
        log.debug(f"Processing location. Name: {location.name}")

        doc = location.location_document
        try:
            mime_type = "text/plain"
            text = p.get(doc.resource_id, mime_type)
        except Exception as e:
            log.debug(f"Failed to get document. Reason: {e}")
            sentry_sdk.capture_exception(e)
            continue

        extracted_tags = list(set(extract_terms_from_text(text, matcher)))

        matched_tags = (
            db_session.query(Tag)
            .filter(func.upper(Tag.name).in_([func.upper(t) for t in extracted_tags]))
            .all()
        )

        location.tags.extend(matched_tags)
        db_session.commit()

        log.debug(
            f"Associating tags with location. Location: {location.name}, Tags: {extracted_tags}"
        )


@scheduler.add(every(5).minutes, name="calculate-locations-cost")
@background_task
def calculate_locations_cost(db_session=None):
    """Calculates the cost of all locations."""

    # we want to update all locations, all the time
    locations = get_all(db_session=db_session)

    for location in locations:
        try:
            # we calculate the cost
            location_cost = calculate_cost(location.id, db_session)

            # if the cost hasn't changed, don't continue
            if location.cost == location_cost:
                continue

            # we update the location
            location.cost = location_cost
            db_session.add(location)
            db_session.commit()

            log.debug(f"Location cost for {location.name} updated in the database.")

            if location.ticket.resource_id:
                # we update the external ticket
                update_external_location_ticket(location, db_session)
                log.debug(f"Location cost for {location.name} updated in the ticket.")
            else:
                log.debug(f"Ticket not found. Location cost for {location.name} not updated.")

        except Exception as e:
            # we shouldn't fail to update all locations when one fails
            sentry_sdk.capture_exception(e)
