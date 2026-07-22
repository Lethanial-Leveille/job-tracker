"""FastAPI app entry point.

v1 skeleton: the app starts, connects to SQLite, and answers /health. No
tables, no CRUD, no AI yet — those arrive one piece at a time.
"""

from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import get_db
from routers.applications import router as applications_router
from routers.resume import router as resume_router

app = FastAPI(title="Job & Scholarship Tracker", version="0.1.0")

app.include_router(applications_router)
app.include_router(resume_router)

@app.get("/health")
def health(db: Session = Depends(get_db)) -> dict[str, str]:
    """Liveness check that also proves the SQLite connection works.

    Running `SELECT 1` forces a real round trip to the database, so a 200 here
    means the whole stack answered: web server, framework, and DB.
    """
    db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected"}
