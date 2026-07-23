"""add user_id to applications and resume_versions

Revision ID: fbf251efc56d
Revises: b79ea37d3021
Create Date: 2026-07-23 16:37:52.455914

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fbf251efc56d'
down_revision: Union[str, Sequence[str], None] = 'b79ea37d3021'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add user_id ownership in three phases, because the tables already hold
    rows that have no owner yet:

      1. add the column NULLABLE (existing rows are allowed to have no owner),
      2. backfill every existing row to the single seeded user, then
      3. enforce NOT NULL and add the foreign key (the models' end state).

    Autogenerate produced a naive non-null add_column, which would fail on a
    populated table; this hand-written version is the standard backfill pattern.
    """
    # Phase 1: add the column nullable.
    with op.batch_alter_table('applications', schema=None) as batch_op:
        batch_op.add_column(sa.Column('user_id', sa.String(length=36), nullable=True))
    with op.batch_alter_table('resume_versions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('user_id', sa.String(length=36), nullable=True))

    # Phase 2: backfill to the single owner (oldest user = user #1). On a fresh
    # deploy DB with no rows, there is nothing to backfill and this is skipped.
    conn = op.get_bind()
    app_nulls = conn.execute(
        sa.text("SELECT count(*) FROM applications WHERE user_id IS NULL")
    ).scalar_one()
    rv_nulls = conn.execute(
        sa.text("SELECT count(*) FROM resume_versions WHERE user_id IS NULL")
    ).scalar_one()
    if app_nulls or rv_nulls:
        owner_id = conn.execute(
            sa.text("SELECT id FROM users ORDER BY created_at LIMIT 1")
        ).scalar()
        if owner_id is None:
            raise RuntimeError(
                "Existing applications/resume_versions rows have no owner and no "
                "user exists to assign them to. Seed a user before migrating."
            )
        conn.execute(
            sa.text("UPDATE applications SET user_id = :uid WHERE user_id IS NULL"),
            {"uid": owner_id},
        )
        conn.execute(
            sa.text("UPDATE resume_versions SET user_id = :uid WHERE user_id IS NULL"),
            {"uid": owner_id},
        )

    # Phase 3: no NULLs remain, so enforce non-null and add the FK to users.
    with op.batch_alter_table('applications', schema=None) as batch_op:
        batch_op.alter_column(
            'user_id', existing_type=sa.String(length=36), nullable=False
        )
        batch_op.create_foreign_key(
            'fk_applications_user_id_users', 'users', ['user_id'], ['id']
        )
    with op.batch_alter_table('resume_versions', schema=None) as batch_op:
        batch_op.alter_column(
            'user_id', existing_type=sa.String(length=36), nullable=False
        )
        batch_op.create_foreign_key(
            'fk_resume_versions_user_id_users', 'users', ['user_id'], ['id']
        )


def downgrade() -> None:
    """Drop the columns. On SQLite, dropping a column rebuilds the table without
    it (and without its foreign key), so no separate drop_constraint is needed."""
    with op.batch_alter_table('resume_versions', schema=None) as batch_op:
        batch_op.drop_column('user_id')
    with op.batch_alter_table('applications', schema=None) as batch_op:
        batch_op.drop_column('user_id')
