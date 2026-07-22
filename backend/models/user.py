"""The User model: one account that owns applications and resume versions.

One row per person. For now there is exactly one row — me — created by a seed
script, not by public signup. The `user_id` foreign key we add to applications
and resume_versions next points back here, so every piece of data is owned by a
user from day one. That is the single bit of multi-user readiness we build ahead
of need: cheap to add now, dangerous to retrofit later.
"""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import String, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class User(Base):
    __tablename__ = "users"

    # Same UUID-as-36-char-string pattern as Application. Generated on insert.
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )

    # The login identifier. unique=True is the first uniqueness constraint in the
    # schema: the database itself rejects a second row with the same email, which
    # is what lets login match exactly one user. That constraint is backed by an
    # index automatically, so no separate index=True is needed here.
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

    # The bcrypt hash of the password, never the plaintext. String(255) is ample
    # headroom over bcrypt's 60-char output.
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    # Created only — no updated_at until there is a change-email/password flow.
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )

    def __repr__(self) -> str:
        return f"<User {self.id} {self.email}>"
