"""cascade delete resume versions and null status suggestions

Deleting an application raised a ForeignKeyViolation whenever a tailored resume
had ever been saved against it, because resume_versions.application_id had no ON
DELETE rule and Postgres defaults to NO ACTION. The route surfaced that as an
opaque 500, so in practice every application you had worked on was undeletable.

Two different rules, because the two tables mean different things:

- resume_versions CASCADE: a saved version is a draft tailored for one specific
  posting. Without that posting it refers to nothing, so it goes with it.
- status_suggestions SET NULL: the suggestion records that an email actually
  arrived. Its application_id is already nullable and null already means "could
  not be resolved to one application", so a deleted target lands it in a state
  the schema models. The evidence survives; only the link is dropped.

SQLite is skipped. It cannot ALTER a constraint (the table would have to be
rebuilt), it does not enforce foreign keys unless PRAGMA foreign_keys is on, and
the only SQLite database left is the stale local dev.db. The test suite builds
its schema from the models with create_all, so it picks the new rules up
directly without this migration.

Revision ID: 8d5710133576
Revises: a71b4f9c2e35
"""

from alembic import op

revision = "8d5710133576"
down_revision = "a71b4f9c2e35"
branch_labels = None
depends_on = None

# (table, constraint name, on-delete action)
_FKS = [
    ("resume_versions", "resume_versions_application_id_fkey", "CASCADE"),
    ("status_suggestions", "status_suggestions_application_id_fkey", "SET NULL"),
]


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table, name, action in _FKS:
        op.drop_constraint(name, table, type_="foreignkey")
        op.create_foreign_key(
            name, table, "applications", ["application_id"], ["id"], ondelete=action
        )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table, name, _ in _FKS:
        op.drop_constraint(name, table, type_="foreignkey")
        op.create_foreign_key(
            name, table, "applications", ["application_id"], ["id"]
        )
