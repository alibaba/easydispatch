from typing import List, Optional

from dispatch.logs.models import LogBase, LogCreate, Logs


def create(*, db_session, log_in: LogCreate) -> Logs:

    logs = Logs(
        **log_in.dict(),
    )
    db_session.add(logs)
    db_session.commit()
    return logs


def create_all(*, db_session, log_in: List[LogCreate]) -> List[Logs]:
    contacts = [Logs(**t.dict()) for t in log_in]
    db_session.bulk_save_objects(contacts)
    db_session.commit()
    return contacts
