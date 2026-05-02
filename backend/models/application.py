import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # What kind of opportunity this is
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    organization: Mapped[str] = mapped_column(String(255), nullable=False)
    role_or_program: Mapped[str] = mapped_column(String(255), nullable=False)
    posting_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    deadline: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Where in the pipeline this application sits
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="discovered")
    priority: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Raw scraped text and Claude's structured parse of it
    jd_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    jd_parsed: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    match_score: Mapped[int | None] = mapped_column(nullable=True)
    match_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
