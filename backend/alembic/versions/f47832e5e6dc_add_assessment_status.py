"""add assessment status

Revision ID: f47832e5e6dc
Revises: 2bd1fe05567a
Create Date: 2026-09-06 14:17:43.792636

Adds `assessment` to the ApplicationStatus enum: the online assessment (a coding
test, or an async/AI-scored one) that sits between applying and speaking to a
human. Without it an assessment invite had to be filed as a "phone screen",
which is a different stage — the Gmail classifier was doing exactly that.

This is the "v3 enum gotcha" from docs/decisions.md in its other form: adding a
value to a native Postgres enum needs an explicit ALTER TYPE, because Alembic
does not autogenerate one.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'f47832e5e6dc'
down_revision: Union[str, Sequence[str], None] = '2bd1fe05567a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        # SQLite stores this enum as VARCHAR plus a CHECK constraint, and the
        # only SQLite path here builds tables fresh (the test suite's
        # create_all), which picks the new member straight off the model. There
        # is nothing to alter.
        return

    # ALTER TYPE ... ADD VALUE cannot run inside the transaction that later uses
    # the new label, and on older Postgres cannot run in a transaction at all.
    # autocommit_block steps outside Alembic's transaction for exactly this case.
    #
    # The value is appended rather than positioned: nothing in the app sorts by
    # this column (applications order by deadline), so the type's internal order
    # does not matter, and appending has fewer ways to fail.
    with op.get_context().autocommit_block():
        op.execute(
            "ALTER TYPE applicationstatus ADD VALUE IF NOT EXISTS 'assessment'"
        )


def downgrade() -> None:
    """Downgrade schema."""
    # Postgres cannot remove a value from an enum type. Undoing this would mean
    # recreating applicationstatus and rewriting every column that depends on it
    # (applications.status, status_events.from_status/to_status,
    # status_suggestions.suggested_status) — far more dangerous than leaving one
    # unused label behind. Deliberate no-op.
    pass
