from enum import Enum


class Visibility(str, Enum):
    open = "Open"
    restricted = "Restricted"


class SearchTypes(str, Enum):
    term = "Term"
    definition = "Definition"
    worker = "Worker"
    team_contact = "Team"
    service = "Service"
    policy = "Policy"
    tag = "Tag"
    task = "Task"
    document = "Document"
    plugin = "Plugin"
    job = "Job"
