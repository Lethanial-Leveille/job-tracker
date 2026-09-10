"""FastAPI app entry point.

v1 skeleton: the app starts, connects to SQLite, and answers /health. No
tables, no CRUD, no AI yet — those arrive one piece at a time.
"""

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import SessionLocal, get_db
from routers.applications import router as applications_router
from routers.auth import router as auth_router
from routers.companies import router as companies_router
from routers.discovered import router as discovered_router
from routers.resume import router as resume_router
from routers.suggestions import router as suggestions_router
from routers.webhooks import router as webhooks_router
from services.discovery import release_orphaned_runs

@asynccontextmanager
async def lifespan(_: FastAPI):
    """Startup housekeeping.

    Discovery pulls run as background tasks inside this process, so a restart
    kills any that were in flight and leaves their rows claiming to be running.
    Since every deploy restarts the process, that is not an edge case — it is
    what happens whenever a deploy lands during a pull. Clearing them here is
    exact rather than heuristic: if this code is executing, nothing that was
    running still is.
    """
    db = SessionLocal()
    try:
        released = release_orphaned_runs(db)
        if released:
            print(f"Released {released} discovery run(s) interrupted by a restart.")
    finally:
        db.close()
    yield


app = FastAPI(title="Prowl", version="0.1.0", lifespan=lifespan)

app.include_router(auth_router)
app.include_router(applications_router)
app.include_router(companies_router)
app.include_router(discovered_router)
app.include_router(resume_router)
app.include_router(suggestions_router)
app.include_router(webhooks_router)

@app.get("/health")
def health(db: Session = Depends(get_db)) -> dict[str, str]:
    """Liveness check that also proves the SQLite connection works.

    Running `SELECT 1` forces a real round trip to the database, so a 200 here
    means the whole stack answered: web server, framework, and DB.
    """
    db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected"}
