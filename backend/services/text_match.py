"""Fuzzy text matching for employer names and job titles.

A DELIBERATE PORT of frontend/src/lib/dedupe.ts. These functions have a twin in
TypeScript, and the two must agree: the frontend uses them to group the pipeline
by company and to warn about duplicate adds, and the Gmail ingestion uses them
to decide which application an email belongs to. If they drift, the same
employer groups one way on screen and matches another way in the backend, and
the bug is nearly invisible.

Kept faithful to the TypeScript rather than improved, for that reason. Where the
original has a wart it is reproduced and commented, not silently fixed here —
fixing it in one language only is exactly the drift this note is warning about.
tests/test_text_match.py asserts a shared table of cases that both sides must
satisfy.

Pure functions, no database, no HTTP.
"""

import re
from urllib.parse import parse_qsl, urlsplit

# Legal suffixes and articles that companies use inconsistently across job
# boards. "Google", "Google LLC", and "Google, Inc." are one employer.
_ORG_NOISE = frozenset(
    {
        "inc", "llc", "ltd", "limited", "corp", "corporation", "co",
        "company", "plc", "gmbh", "ag", "sa", "nv", "the",
    }
)

# Mirrors the TS character class /[.,'’&]/ — note the curly apostrophe, which
# real company names and email text both contain.
_ORG_STRIP = re.compile(r"[.,'’&]")
_ORG_SPLIT = re.compile(r"[\s/|-]+")


def normalize_organization(name: str) -> str:
    """Reduce an employer name to a comparison key.

    Twin of normalizeOrganization in dedupe.ts. Also the function a future
    organizations table would use to backfill itself.
    """
    words = _ORG_SPLIT.split(_ORG_STRIP.sub("", name.lower()))
    return " ".join(w for w in words if w and w not in _ORG_NOISE)


# Words that appear in nearly every internship title and so say nothing about
# WHICH internship it is.
#
# "co-op" is dead weight, faithfully reproduced from the TypeScript: the split
# below breaks on "-", so "co-op" becomes "co" and "op" and this entry is never
# consulted. Left in place because removing it here alone would put the two
# implementations out of step; worth fixing in BOTH files together sometime.
_ROLE_NOISE = frozenset(
    {
        "intern", "interns", "internship", "internships", "co-op", "coop",
        "summer", "fall", "winter", "spring", "student", "program",
        "the", "and", "of", "for", "a", "an", "i", "ii", "iii",
    }
)

_ROLE_STRIP = re.compile(r"[.,'’&()]")
_ROLE_SPLIT = re.compile(r"[\s/|,-]+")
_YEAR = re.compile(r"^(19|20)\d{2}$")


def stem(word: str) -> str:
    """Collapse the endings that make one word look like two.

    "engineering" and "engineer" both become "engine". Without this, "Software
    Engineer Intern" and "Software Engineering Internship" share no tokens at
    all and score zero, which is the single most common way one job gets titled
    two different ways.

    Each rule only fires if it leaves at least four characters, so short words
    are never mangled into noise. Deliberately not a real stemmer: it has to
    stay predictable enough to reason about when a match looks wrong.
    """
    out = word

    def strip(suffix: str) -> str:
        if out.endswith(suffix) and len(out) - len(suffix) >= 4:
            return out[: -len(suffix)]
        return out

    out = strip("ing")  # engineering -> engineer
    out = strip("ers")  # engineers   -> engine
    out = strip("er")  # engineer    -> engine
    if not out.endswith("ss"):
        out = strip("s")  # systems -> system, business stays
    return out


def role_tokens(role: str) -> set[str]:
    """The meaningful, stemmed words in a job title."""
    words = _ROLE_SPLIT.split(_ROLE_STRIP.sub("", role.lower()))
    return {
        stem(w)
        for w in words
        if w and w not in _ROLE_NOISE and not _YEAR.match(w)
    }


def role_similarity(a: str, b: str) -> float:
    """How much two titles overlap, as a fraction of the SHORTER one.

    Shorter rather than the union, on purpose: "Software Engineer Intern" and
    "Software Engineer Intern, Machine Learning Platform" are plausibly the same
    job written at two lengths, and measuring against the union would score that
    pair low precisely because one side is more detailed.

    Returns 0.0 when either title has no meaningful words left.
    """
    left = role_tokens(a)
    right = role_tokens(b)
    if not left or not right:
        return 0.0
    return len(left & right) / min(len(left), len(right))


# --- URL matching ------------------------------------------------------------
# Twin of normalizeUrl in dedupe.ts, same rule as the functions above: the two
# must agree or the same link is a duplicate in the browser and a new job in the
# backend. Added when the discovery feed needed to check a pulled posting
# against applications server-side; the add flow has always done this in the UI.

# Query parameters that describe how you ARRIVED at a posting rather than which
# posting it is. Stripping these makes the same job shared two ways compare
# equal — and it is why the Dell link with a Facebook click id on it matches the
# same posting shared any other way.
#
# This list is deliberately short. The tempting move is to drop every query
# param, and it is wrong: Greenhouse and Lever put the actual job id in the
# query string (`?gh_jid=4055123`), so a blanket strip would collapse every
# posting at a company into one and report constant false duplicates. Only known
# tracking keys are removed; anything unrecognized is treated as identifying.
_TRACKING_PARAMS = frozenset(
    {
        "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
        "ref", "referer", "referrer", "refid", "source", "src",
        # Greenhouse SOURCE. Not gh_jid, which is the job id.
        "gh_src",
        "trk", "trackingid", "originalsubdomain",
        # Present in the TypeScript's behavior but not its list: Facebook and
        # Instagram append these to every shared link, and postings arrive that
        # way constantly. Add them to dedupe.ts too when you touch it next.
        "fbclid", "igshid", "gclid", "mc_cid", "mc_eid",
    }
)

_TRAILING_SLASHES = re.compile(r"/+$")


def normalize_url(raw: str) -> str | None:
    """Reduce a URL to a comparison key, or None for empty input.

    Scheme dropped, host lowercased and de-www'd, trailing slash removed,
    tracking params stripped, remaining params sorted so param order cannot make
    two identical links look different, fragment dropped.

    A string that does not parse as a URL is not an error — it may be something
    half-typed — so it falls back to a trimmed, lowercased comparison rather
    than raising. Faithful to the TypeScript, which does the same.
    """
    trimmed = raw.strip()
    if trimmed == "":
        return None

    # urlsplit needs a scheme to find a host, and a pasted link rarely has one.
    with_scheme = trimmed if re.match(r"^https?://", trimmed, re.I) else f"https://{trimmed}"

    try:
        parts = urlsplit(with_scheme)
        host = (parts.hostname or "").lower()
    except ValueError:
        return trimmed.lower()
    if not host:
        return trimmed.lower()

    host = host.removeprefix("www.")
    path = _TRAILING_SLASHES.sub("", parts.path)

    # keep_blank_values matches the TypeScript, where a bare "?x" survives as
    # "x=" rather than vanishing.
    # Any utm_* key is tracking by definition, matched by prefix rather than by
    # name. The enumerated list missed utm_id on a real link, and enumerating is
    # a losing game — analytics tools invent new utm_ suffixes freely, and each
    # one missed is a duplicate that slips through as a new job.
    kept = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in _TRACKING_PARAMS and not key.lower().startswith("utm_")
    ]
    kept.sort(key=lambda pair: pair[0])
    query = "?" + "&".join(f"{k}={v}" for k, v in kept) if kept else ""

    return f"{host}{path}{query}"


def urls_match(a: str, b: str) -> bool:
    """True when two links point at the same posting."""
    key = normalize_url(a)
    return key is not None and key == normalize_url(b)
