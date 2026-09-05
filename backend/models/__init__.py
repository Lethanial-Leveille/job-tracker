"""Model package: importing ANY model registers ALL of them.

SQLAlchemy resolves a relationship's target by NAME ("ResumeVersion"), and it can
only do that once that class has been imported and entered the registry. So a
module that imports one model and reaches another through a relationship fails
with `failed to locate a name` — and only sometimes, depending on what else the
entry point happened to import first.

That is exactly what happened when Application gained its cascade relationships:
the app kept working (main.py pulls in every model transitively through the
routers) while scripts/load_master_from_yaml.py, which imports only User and the
resume models, started raising on startup. A bug that reproduces in a script but
not in the app is the worst kind to chase.

Re-exporting every model here fixes it at the root: importing `models.anything`
runs this file first, so the registry is always complete. Add new models to this
list when you create them.
"""

from models.application import Application
from models.ingested_email import IngestedEmail
from models.resume import MasterResume
from models.resume_version import ResumeVersion
from models.status_event import StatusEvent
from models.status_suggestion import StatusSuggestion
from models.user import User

__all__ = [
    "Application",
    "IngestedEmail",
    "MasterResume",
    "ResumeVersion",
    "StatusEvent",
    "StatusSuggestion",
    "User",
]
