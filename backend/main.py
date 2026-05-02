from contextlib import asynccontextmanager

from fastapi import FastAPI

from database import Base, engine
from routers.applications import router as applications_router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Runs once at startup: create any tables that don't exist yet
    Base.metadata.create_all(bind=engine)
    yield
    # Anything after yield runs at shutdown (nothing needed yet)


app = FastAPI(
    title="Job Tracker",
    description="Personal application tracker for internships, scholarships, and research.",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(applications_router)


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok"}
