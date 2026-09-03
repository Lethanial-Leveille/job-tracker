"""add fit_report to applications

Revision ID: c4d1e8b7a209
Revises: 189e547fa121
Create Date: 2026-09-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4d1e8b7a209'
down_revision: Union[str, Sequence[str], None] = 'fa83dd1ecb8a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Both nullable with no default: every existing row simply has no report
    # until one is computed on demand, so there is nothing to backfill.
    with op.batch_alter_table('applications', schema=None) as batch_op:
        batch_op.add_column(sa.Column('fit_report', sa.JSON(), nullable=True))
        batch_op.add_column(
            sa.Column('fit_computed_at', sa.DateTime(), nullable=True)
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('applications', schema=None) as batch_op:
        batch_op.drop_column('fit_computed_at')
        batch_op.drop_column('fit_report')
