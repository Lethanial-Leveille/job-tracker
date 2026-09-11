"""rank discovered jobs by fit and mark what is new

Revision ID: 386f8e5b5278
Revises: 439de67f42b9
Create Date: 2026-09-10 21:33:39.747715

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '386f8e5b5278'
down_revision: Union[str, Sequence[str], None] = '439de67f42b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('discovered_jobs', sa.Column('fit_score', sa.Integer(), nullable=True))
    op.add_column('discovered_jobs', sa.Column('fit_report', sa.JSON(), nullable=True))
    op.add_column('discovered_jobs', sa.Column('run_id', sa.String(length=36), nullable=True))
    op.create_foreign_key('fk_discovered_jobs_run', 'discovered_jobs', 'discovery_runs', ['run_id'], ['id'], ondelete='SET NULL')
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('fk_discovered_jobs_run', 'discovered_jobs', type_='foreignkey')
    op.drop_column('discovered_jobs', 'run_id')
    op.drop_column('discovered_jobs', 'fit_report')
    op.drop_column('discovered_jobs', 'fit_score')
    # ### end Alembic commands ###
