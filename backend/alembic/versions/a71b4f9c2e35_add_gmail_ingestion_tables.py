"""add ingested_emails and status_suggestions

Revision ID: a71b4f9c2e35
Revises: c4d1e8b7a209
Create Date: 2026-09-03 00:00:00.000000

Written by hand rather than by autogenerate, for two reasons autogenerate gets
wrong here:

1. `status_suggestions.suggested_status` reuses the ApplicationStatus enum, and
   Postgres ALREADY has that type (`applicationstatus`, 14 labels, created by
   5a510583d8ee for the applications table). A generated migration emits a plain
   sa.Enum, which tries to CREATE TYPE again and fails with "type already
   exists". It is bound below with create_type=False on Postgres so the column
   references the existing type instead of redefining it.

2. Postgres does not drop an enum type when you drop the table using it, so a
   downgrade would leave `suggestionstate` behind and the next upgrade would
   fail on "type already exists". The downgrade drops it explicitly. It must NOT
   drop `applicationstatus`, which the applications table still depends on.

This is the "v3 enum gotcha" docs/decisions.md warned about, showing up exactly
where it was predicted.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a71b4f9c2e35'
down_revision: Union[str, Sequence[str], None] = 'c4d1e8b7a209'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Mirrors models.application.ApplicationStatus. Spelled out rather than imported
# so this migration keeps describing the schema as it was at THIS revision, even
# if the model changes later.
APPLICATION_STATUS_VALUES = (
    'discovered', 'drafting', 'ready', 'applied', 'recruiter_engaged',
    'phone_screen', 'technical_interview', 'onsite', 'offer', 'accepted',
    'declined', 'rejected', 'ghosted', 'missed_deadline',
)

SUGGESTION_STATE_VALUES = ('pending', 'accepted', 'dismissed')


def _existing_application_status_enum():
    """The ApplicationStatus enum as an ALREADY EXISTING type.

    On Postgres this must not re-issue CREATE TYPE; create_type=False makes the
    column reference `applicationstatus` as it stands. On SQLite an enum is just
    a VARCHAR plus a CHECK constraint with no separate type to collide with, so
    the plain sa.Enum is correct there.
    """
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
    # ingested_emails first: status_suggestions carries a foreign key to it.
    op.create_table(
        'ingested_emails',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('message_id', sa.String(length=255), nullable=False),
        sa.Column('thread_id', sa.String(length=255), nullable=True),
        sa.Column('received_at', sa.DateTime(), nullable=False),
        sa.Column('from_email', sa.String(length=320), nullable=False),
        sa.Column('from_name', sa.String(length=255), nullable=True),
        sa.Column('subject', sa.String(length=998), nullable=True),
        sa.Column('snippet', sa.String(length=500), nullable=True),
        sa.Column('classification', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        # THE idempotency guarantee. Written explicitly rather than left to
        # autogenerate because the entire Gmail retry design rests on it: n8n
        # re-POSTs a rolling two day window with no cursor, so duplicate
        # deliveries are expected, not exceptional. This constraint is what makes
        # the second delivery fail atomically at the database instead of racing
        # a SELECT-then-INSERT check in the service and inserting twice.
        #
        # Keyed on (user_id, message_id): Gmail ids are unique per mailbox, not
        # globally.
        sa.UniqueConstraint(
            'user_id', 'message_id', name='uq_ingested_email_user_message'
        ),
    )

    op.create_table(
        'status_suggestions',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        # Nullable on purpose: null means the email resolved to zero or to
        # several applications, and a suggestion with no target cannot flip a
        # status. "Propose, never decide" enforced by the schema.
        sa.Column('application_id', sa.String(length=36), nullable=True),
        sa.Column('candidate_application_ids', sa.JSON(), nullable=True),
        sa.Column(
            'suggested_status', _existing_application_status_enum(), nullable=False
        ),
        sa.Column('reason', sa.String(length=500), nullable=False),
        sa.Column('source_email_id', sa.String(length=36), nullable=False),
        # A genuinely new type: this one IS created here, and dropped again in
        # downgrade below.
        sa.Column(
            'state',
            sa.Enum(*SUGGESTION_STATE_VALUES, name='suggestionstate'),
            nullable=False,
        ),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['application_id'], ['applications.id'], ),
        sa.ForeignKeyConstraint(['source_email_id'], ['ingested_emails.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Reverse order: the child table's foreign key must go before its parent.
    op.drop_table('status_suggestions')
    op.drop_table('ingested_emails')

    # Postgres keeps an enum type after the table using it is dropped, so
    # without this a downgrade then upgrade fails on "type suggestionstate
    # already exists". SQLite has no separate type to clean up.
    #
    # `applicationstatus` is deliberately NOT dropped: the applications table
    # still uses it, and dropping it here would take that table's status column
    # with it.
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        sa.Enum(name='suggestionstate').drop(bind, checkfirst=True)
