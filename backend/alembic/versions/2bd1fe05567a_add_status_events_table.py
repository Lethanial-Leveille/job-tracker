"""add status_events table

Revision ID: 2bd1fe05567a
Revises: 8d5710133576
Create Date: 2026-09-05 14:00:25.597651

Written by hand, not left to autogenerate, for the same enum reasons as the
Gmail migration (a71b4f9c2e35):

1. `from_status`/`to_status` reuse the ApplicationStatus enum, which Postgres
   ALREADY has (`applicationstatus`). A plain sa.Enum would try to CREATE TYPE
   again and fail; create_type=False references the existing type instead.
2. `source` is a genuinely new type (`statuseventsource`), created here and
   dropped in downgrade — Postgres keeps an enum after its table is dropped, so
   without the explicit drop a downgrade-then-upgrade fails on "already exists".
   `applicationstatus` is deliberately NOT dropped (the applications table needs it).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2bd1fe05567a'
down_revision: Union[str, Sequence[str], None] = '8d5710133576'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Spelled out (not imported) so this migration keeps describing the schema as it
# was at THIS revision even if the model changes later.
APPLICATION_STATUS_VALUES = (
    'discovered', 'drafting', 'ready', 'applied', 'recruiter_engaged',
    'phone_screen', 'technical_interview', 'onsite', 'offer', 'accepted',
    'declined', 'rejected', 'ghosted', 'missed_deadline',
)

STATUS_EVENT_SOURCE_VALUES = ('manual', 'email')


def _existing_application_status_enum():
    """ApplicationStatus as an ALREADY EXISTING type: no CREATE TYPE on Postgres."""
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        from sqlalchemy.dialects import postgresql

        return postgresql.ENUM(
            *APPLICATION_STATUS_VALUES,
            name='applicationstatus',
            create_type=False,
        )
    return sa.Enum(*APPLICATION_STATUS_VALUES, name='applicationstatus')


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'status_events',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('application_id', sa.String(length=36), nullable=False),
        # Null marks the application's first status (created at it).
        sa.Column('from_status', _existing_application_status_enum(), nullable=True),
        sa.Column('to_status', _existing_application_status_enum(), nullable=False),
        # A genuinely new type: created here, dropped in downgrade.
        sa.Column(
            'source',
            sa.Enum(*STATUS_EVENT_SOURCE_VALUES, name='statuseventsource'),
            nullable=False,
        ),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['application_id'], ['applications.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('status_events')

    # Postgres keeps the enum type after its table is dropped; clean it up so a
    # re-upgrade doesn't fail. applicationstatus stays (applications needs it).
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        sa.Enum(name='statuseventsource').drop(bind, checkfirst=True)
