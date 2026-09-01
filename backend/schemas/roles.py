"""The canonical role families: one fixed vocabulary for an untidy field.

Why this exists: postings title the same job many different ways. Across the
first sixteen applications in the tracker, fourteen were the same role written
fourteen ways — "Software Engineer Intern", "Software Engineer, Internship",
"Summer 2027 Intern - Software Engineer", "Engineering Internship", "2027 Summer
Internship - Software Engineering". Scanning that list, nothing lines up.

So the parser classifies each posting into one of the values below, stored in
`applications.role_family`, while `role_or_program` keeps the real posted title.
The list renders the tidy value; the detail drawer shows what it was actually
called. Nothing is lost — "Software Engineer Intern / Basketball Operations"
normalizes to the plain family and keeps its Basketball Operations detail.

Two deliberate choices:

- This is a Literal, not a database enum. The DB column is a plain VARCHAR, so
  adding a family here is a code change rather than an ALTER TYPE migration
  (see docs/decisions.md, the v3 native-enum gotcha). This module is the single
  source of truth: the Pydantic schemas import it, so the API rejects anything
  outside the set even though the column itself would accept it.
- "Other" is a real member, not a fallback to be embarrassed about. A posting
  that fits nothing here should say so plainly instead of being force-fit into
  the nearest family, which would quietly corrupt the grouping.
"""

from typing import Literal, get_args

RoleFamily = Literal[
    "Software Engineer Intern",
    "Embedded Engineer Intern",
    "AI and ML Engineer Intern",
    "Frontend Engineer Intern",
    "Backend Engineer Intern",
    "Data Engineer Intern",
    "Hardware Engineer Intern",
    "Other",
]

# The same values as a runtime tuple, for prompts and validation loops. Derived
# from the Literal rather than retyped, so the two can never drift apart.
ROLE_FAMILIES: tuple[str, ...] = get_args(RoleFamily)
