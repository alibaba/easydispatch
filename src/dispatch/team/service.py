from typing import List, Optional

from fastapi.encoders import jsonable_encoder
from dispatch.service import service as service_service
from .models import Team, TeamCreate, TeamUpdate


def get(*, db_session, team_id: int) -> Optional[Team]:
    return db_session.query(Team).filter(Team.id == team_id).first()


def get_by_code(*, db_session, code: str) -> Optional[Team]:
    return db_session.query(Team).filter(Team.code == code).first()


def get_all(*, db_session) -> List[Optional[Team]]:
    return db_session.query(Team)


# def get_or_create(*, db_session, email: str, **kwargs) -> Team:
#     contact = get_by_code(db_session=db_session, code=email)

#     if not contact:
#         team_contact = TeamCreate(code=email, **kwargs)
#         contact = create(db_session=db_session, team_contact_in=team_contact)

#     return contact


def create(*, db_session, team_contact_in: TeamCreate) -> Team:
    planner_service = None
    if team_contact_in.planner_service:
        planner_service = service_service.get_by_code(db_session=db_session, code=team_contact_in.planner_service.code) 

    team = Team(
        **team_contact_in.dict(exclude={"planner_service"}),
        planner_service=planner_service 
    ) 
    db_session.add(team)
    db_session.commit()
    return team


def create_all(*, db_session, team_contacts_in: List[TeamCreate]) -> List[Team]:
    contacts = [Team(**t.dict()) for t in team_contacts_in]
    db_session.bulk_save_objects(contacts)
    db_session.commit()
    return contacts


def update(
    *, db_session, team_contact: Team, team_contact_in: TeamUpdate
) -> Team:
    team_contact_data = jsonable_encoder(team_contact)

    planner_service = None
    if team_contact_in.planner_service:
        planner_service = service_service.get_by_code(db_session=db_session, code=team_contact_in.planner_service.code) 

    update_data = team_contact_in.dict(
        skip_defaults=True, exclude={"planner_service"}
    )

    for field in team_contact_data:
        if field in update_data:
            setattr(team_contact, field, update_data[field])

    team_contact.planner_service = planner_service
    db_session.add(team_contact)
    db_session.commit()
    return team_contact


def delete(*, db_session, team_id: int):
    team = db_session.query(Team).filter(Team.id == team_id).first()
    team.terms = []
    db_session.delete(team)
    db_session.commit()
