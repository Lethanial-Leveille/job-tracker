"""record how many rows a run re-judged

Revision ID: 444a411ff4b6
Revises: 386f8e5b5278
Create Date: 2026-09-10 21:55:07.462181

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '444a411ff4b6'
down_revision: Union[str, Sequence[str], None] = '386f8e5b5278'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # server_default is required, not optional. The model's `default=0` is a
    # Python-side default applied when the ORM builds a new object, which does
    # nothing for rows that already exist — so adding a NOT NULL column without
    # one fails on any table with data in it. It passed locally against an empty
    # discovery_runs and broke the deploy against a real one.
    op.add_column(
        'discovery_runs',
        sa.Column('rescored', sa.Integer(), nullable=False, server_default='0'),
    )
    # Dropped once the backfill is done, so the column's default lives in one
    # place (the model) rather than two that can disagree.
    op.alter_column('discovery_runs', 'rescored', server_default=None)
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('discovery_runs', 'rescored')
    # ### end Alembic commands ###
