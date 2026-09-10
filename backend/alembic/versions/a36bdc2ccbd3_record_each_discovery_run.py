"""record each discovery run

Revision ID: a36bdc2ccbd3
Revises: 192987c82f73
Create Date: 2026-09-10 17:51:49.395047

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a36bdc2ccbd3'
down_revision: Union[str, Sequence[str], None] = '192987c82f73'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('discovery_runs',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('state', sa.Enum('running', 'succeeded', 'failed', name='runstate'), nullable=False),
    sa.Column('started_at', sa.DateTime(), nullable=False),
    sa.Column('finished_at', sa.DateTime(), nullable=True),
    sa.Column('fetched', sa.Integer(), nullable=False),
    sa.Column('staged', sa.Integer(), nullable=False),
    sa.Column('duplicates', sa.Integer(), nullable=False),
    sa.Column('enriched', sa.Integer(), nullable=False),
    sa.Column('ruled_out', sa.Integer(), nullable=False),
    sa.Column('sources', sa.JSON(), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('discovery_runs')
    # Autogenerate leaves the enum type behind, so a re-upgrade after a
    # downgrade fails with "type runstate already exists". SQLite has no enum
    # types, hence the dialect gate — same pattern as the discovered_jobs
    # migration.
    if op.get_bind().dialect.name == "postgresql":
        sa.Enum(name="runstate").drop(op.get_bind(), checkfirst=True)
