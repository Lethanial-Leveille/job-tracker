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
    op.add_column('discovery_runs', sa.Column('rescored', sa.Integer(), nullable=False))
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('discovery_runs', 'rescored')
    # ### end Alembic commands ###
