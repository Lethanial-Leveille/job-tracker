"""record whether a deadline came from the posting or from me

Revision ID: e6d5835d693e
Revises: 444a411ff4b6
Create Date: 2026-09-25 18:24:15.278641

The column is half of this migration; the classification is the other half, and
it runs here rather than in a script under scripts/ on purpose.

Every other backfill in this project is a separate script, dry run by default,
because each of those rewrites data that already meant something. This one only
fills a column that did not exist a moment ago. It reads `deadline` and
`jd_parsed` and never writes to either, so the worst case is a wrong label on a
brand new field, and `downgrade()` erases the entire question. That safety is
what buys the convenience of not having to remember to run something by hand on
a droplet that is awkward to reach.

How a row is judged. The parser is forbidden from inventing a deadline (see
services/parsing.py), so `jd_parsed["deadline"]` is trustworthy evidence of what
the posting actually said:

  jd_parsed states a date, and it matches the row  ->  "posting"
  jd_parsed ran and states no date, but the row has one  ->  "self"
  anything else  ->  NULL

That last line is doing real work. A row with no `jd_parsed` predates parsing and
there is no evidence either way. A row whose stored date DISAGREES with the
parsed one could be a correction of a bad parse or an override of a real
deadline, and those are opposite meanings. Both stay NULL, because inventing a
label here would recreate exactly the ambiguity this column exists to remove.
"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e6d5835d693e'
down_revision: Union[str, Sequence[str], None] = '444a411ff4b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _iso_day(value: object) -> str | None:
    """Normalize a date, datetime, or date-ish string to 'YYYY-MM-DD'.

    Needed because the two sides arrive in different shapes and from different
    drivers: `deadline` comes back as a date on Postgres and a string on SQLite,
    and the parsed value is whatever JSON held. Comparing them raw would report
    every row as a mismatch and label the whole table NULL.
    """
    if value is None:
        return None
    text = value.isoformat() if hasattr(value, "isoformat") else str(value)
    return text[:10] or None


def upgrade() -> None:
    op.add_column(
        'applications',
        sa.Column('deadline_source', sa.String(length=16), nullable=True),
    )

    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, deadline, jd_parsed FROM applications "
            "WHERE deadline IS NOT NULL"
        )
    ).fetchall()

    counts = {"posting": 0, "self": 0, "unknown": 0}
    for row_id, deadline, jd_parsed in rows:
        parsed = jd_parsed
        if isinstance(parsed, str):
            # SQLite hands back the raw JSON text; Postgres hands back a dict.
            try:
                parsed = json.loads(parsed)
            except ValueError:
                parsed = None

        if not isinstance(parsed, dict):
            counts["unknown"] += 1
            continue

        stated = _iso_day(parsed.get("deadline"))
        stored = _iso_day(deadline)

        if stated is None:
            source = "self"
        elif stated == stored:
            source = "posting"
        else:
            source = None

        if source is None:
            counts["unknown"] += 1
            continue

        counts[source] += 1
        bind.execute(
            sa.text(
                "UPDATE applications SET deadline_source = :src WHERE id = :id"
            ),
            {"src": source, "id": row_id},
        )

    print(
        f"deadline_source backfill: {counts['posting']} from postings, "
        f"{counts['self']} self-imposed, {counts['unknown']} left unknown "
        f"({len(rows)} rows with a deadline)"
    )


def downgrade() -> None:
    op.drop_column('applications', 'deadline_source')
