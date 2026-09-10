"""Tests for staging: what reaches the inbox, and what it costs to get there.

Two things are being protected here, and only one of them is about correctness.

The first is the three-way match. A job whose link you already track must
disappear; a job that merely resembles one must arrive carrying what it
resembles; a new job must arrive clean. Collapsing the middle case into either
neighbour is the failure that matters — it either hides a real posting or
pretends an obvious repeat is new.

The second is the ORDER of the pipeline. Deduplication is free and eliminates
the most, classification costs money per call. Run backwards, the feature bills
you to re-judge the same few hundred postings every night forever, and nothing
about the output would look wrong. That is exactly the kind of regression a test
has to hold in place, because no one notices it until the invoice arrives.

The classifier is mocked throughout — the real one is a paid call, and its own
behavior is covered in test_parsing_service.py.
"""

from datetime import UTC, datetime, timedelta
import pytest
from unittest.mock import MagicMock, patch

from sqlalchemy import select
from sqlalchemy.orm import Session

from config import Settings
from models.application import Application, ApplicationStatus, ApplicationType
from models.discovered_job import DiscoveredJob, DiscoveryState
from models.user import User
from schemas.discovery import FeedListing, PullResult
from services.discovery import enrich_pending, resolve, stage_listings


def _settings() -> Settings:
    return Settings(anthropic_api_key="test-key", jwt_secret="test-secret")


def _listing(**overrides: object) -> FeedListing:
    base = {
        "id": "feed-1",
        "company_name": "Acme Corp",
        "title": "Software Engineer Intern",
        "url": "https://jobs.example.com/acme/1",
        "category": "Software",
        "active": True,
        "terms": ["Summer 2027"],
        "degrees": ["Bachelor's"],
        "locations": ["Austin, TX"],
        "date_posted": datetime.now(UTC).timestamp(),
    }
    base.update(overrides)
    return FeedListing(**base)  # type: ignore[arg-type]


def _application(db: Session, user: User, **overrides: object) -> Application:
    base = {
        "user_id": user.id,
        "type": ApplicationType.internship,
        "status": ApplicationStatus.applied,
        "organization": "Acme Corp",
        "role_or_program": "Software Engineer Intern",
        "posting_url": "https://jobs.example.com/acme/1",
    }
    base.update(overrides)
    row = Application(**base)  # type: ignore[arg-type]
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _staged(db: Session) -> list[DiscoveredJob]:
    """Rows that will actually reach the inbox.

    Deliberately not every row in the table: a posting the classifier rejects
    also gets written, as a `filtered` row nobody sees, so that it is never paid
    to be judged twice. Use _all_rows when that distinction is the point.
    """
    return [
        row
        for row in db.execute(select(DiscoveredJob)).scalars().all()
        if row.state is not DiscoveryState.filtered
    ]


def _all_rows(db: Session) -> list[DiscoveredJob]:
    return list(db.execute(select(DiscoveredJob)).scalars().all())


def _stage(db: Session, user: User, listings: list[FeedListing], families: dict | None):
    with patch("services.discovery.classify_role_families") as classifier:
        classifier.return_value = families
        result = stage_listings(db, user.id, listings, _settings(), PullResult())
    return result, classifier


# --- The three-way match -----------------------------------------------------


def test_the_same_link_you_already_track_never_reaches_you(
    db: Session, user: User
) -> None:
    _application(db, user, posting_url="https://jobs.example.com/acme/1")

    result, classifier = _stage(db, user, [_listing()], {0: "Software Engineer Intern"})

    assert _staged(db) == []
    assert result.duplicates == 1
    # And it was never classified — the whole reason dedupe runs first.
    classifier.assert_not_called()


def test_tracking_parameters_do_not_make_a_duplicate_look_new(
    db: Session, user: User
) -> None:
    """The link you saved and the link the feed publishes are rarely byte-equal.

    One came off a share sheet with a Facebook click id on it, the other did
    not. Comparing raw strings reports a duplicate as new every time.
    """
    _application(db, user, posting_url="https://jobs.example.com/acme/1")

    listing = _listing(url="https://www.jobs.example.com/acme/1/?fbclid=abc&utm_id=9")
    result, _ = _stage(db, user, [listing], {0: "Software Engineer Intern"})

    assert _staged(db) == []
    assert result.duplicates == 1


def test_a_similar_posting_is_staged_carrying_what_it_resembles(
    db: Session, user: User
) -> None:
    """The middle outcome, and the one worth the complexity.

    Same employer, near-identical title, different link. Hiding it would lose a
    real posting; saying nothing would let you reapply blind. So it arrives with
    the row it might already be.
    """
    existing = _application(
        db,
        user,
        posting_url="https://boards.greenhouse.io/acme/jobs/99",
        role_or_program="Software Engineering Intern, Summer 2027",
    )

    result, _ = _stage(db, user, [_listing()], {0: "Software Engineer Intern"})

    rows = _staged(db)
    assert len(rows) == 1
    assert rows[0].possible_application_ids == [existing.id]
    assert result.staged == 1
    assert result.duplicates == 0


def test_a_different_role_at_the_same_employer_is_not_flagged(
    db: Session, user: User
) -> None:
    # Holding several roles at one company is normal. Flagging on employer alone
    # would mark nearly everything, which trains you to ignore the flag.
    _application(
        db, user, posting_url="https://x/1", role_or_program="Product Design Intern"
    )

    _stage(db, user, [_listing()], {0: "Software Engineer Intern"})

    assert _staged(db)[0].possible_application_ids is None


def test_a_genuinely_new_posting_is_staged_clean(db: Session, user: User) -> None:
    result, _ = _stage(db, user, [_listing()], {0: "Software Engineer Intern"})

    rows = _staged(db)
    assert len(rows) == 1
    assert rows[0].organization == "Acme Corp"
    assert rows[0].role_family == "Software Engineer Intern"
    assert rows[0].possible_application_ids is None
    assert rows[0].state is DiscoveryState.pending
    assert result.staged == 1


# --- Not showing you the same thing twice ------------------------------------


def test_a_job_already_in_the_inbox_is_not_staged_again(
    db: Session, user: User
) -> None:
    _stage(db, user, [_listing()], {0: "Software Engineer Intern"})

    result, classifier = _stage(db, user, [_listing()], {0: "Software Engineer Intern"})

    assert len(_staged(db)) == 1
    assert result.duplicates == 1
    classifier.assert_not_called()


def test_a_job_you_dismissed_does_not_come_back(db: Session, user: User) -> None:
    """The reason resolved rows are kept rather than deleted.

    The feed republishes its whole catalogue daily. Delete a dismissal and
    tomorrow's pull finds no record of it and hands you the job again.
    """
    _stage(db, user, [_listing()], {0: "Software Engineer Intern"})
    resolve(db, _staged(db)[0], DiscoveryState.dismissed)

    _stage(db, user, [_listing()], {0: "Software Engineer Intern"})

    rows = _staged(db)
    assert len(rows) == 1
    assert rows[0].state is DiscoveryState.dismissed


def test_another_users_inbox_does_not_block_yours(db: Session, user: User) -> None:
    # The dedupe question is always "have I seen this", never "has anyone".
    other = User(email="other@example.com", password_hash="x")
    db.add(other)
    db.commit()
    _stage(db, other, [_listing()], {0: "Software Engineer Intern"})

    result, _ = _stage(db, user, [_listing()], {0: "Software Engineer Intern"})

    assert result.staged == 1
    assert len(_staged(db)) == 2


# --- Classification ----------------------------------------------------------


def test_only_new_postings_are_ever_classified(db: Session, user: User) -> None:
    """The ordering that decides what this feature costs to run.

    Two of these three are already known. If classification ran before dedupe,
    all three would be billed every night, forever, and the staged output would
    look identical — which is why this needs a test rather than a comment.
    """
    _application(db, user, posting_url="https://jobs.example.com/acme/1")
    _stage(db, user, [_listing(id="feed-2", url="https://x/2")], {0: "Software Engineer Intern"})

    _, classifier = _stage(
        db,
        user,
        [
            _listing(),                                        # duplicate link
            _listing(id="feed-2", url="https://x/2"),           # already staged
            _listing(id="feed-3", url="https://x/3", title="Backend Intern"),
        ],
        {0: "Backend Engineer Intern"},
    )

    titles = classifier.call_args.args[0]
    assert titles == ["Backend Intern"]


def test_an_unwanted_family_is_dropped_and_counted(db: Session, user: User) -> None:
    # Counted by family rather than into one bucket, so "the classifier decided
    # everything is AI/ML" reads as a number instead of as an empty inbox.
    result, _ = _stage(
        db, user, [_listing(title="ML Research Intern")], {0: "AI and ML Engineer Intern"}
    )

    assert _staged(db) == []
    assert result.dropped == {"family:AI and ML Engineer Intern": 1}
    # Recorded, not forgotten: this is what stops it being re-judged nightly.
    assert _all_rows(db)[0].state is DiscoveryState.filtered


def test_a_title_the_classifier_skipped_is_left_alone(db: Session, user: User) -> None:
    # classify_role_families omits an index it could not resolve after every
    # round. Staging it anyway would put an unjudged job in the inbox.
    result, _ = _stage(db, user, [_listing()], {})

    assert _staged(db) == []
    assert result.dropped == {"unclassified": 1}
    assert _all_rows(db)[0].state is DiscoveryState.filtered


def test_a_dead_classifier_stages_nothing_and_says_so(db: Session, user: User) -> None:
    """Nothing is written, so the next run tries again.

    Staging everything unjudged would fill the inbox with noise; staging nothing
    silently would look exactly like a quiet night.
    """
    result, _ = _stage(db, user, [_listing()], None)

    assert _staged(db) == []
    assert result.dropped == {"classifier unavailable": 1}


def test_a_dead_chunk_does_not_condemn_the_others(db: Session, user: User) -> None:
    """Classification is chunked, so failures are per chunk, not per run.

    The listings in a failed chunk go unwritten, which is what lets the next run
    retry exactly them, while everything else stages normally.
    """
    listings = [
        _listing(id=f"feed-{i}", url=f"https://x/{i}", title="Software Engineer Intern")
        for i in range(3)
    ]
    with patch("services.discovery.classify_role_families") as classifier, patch(
        "services.discovery._CLASSIFY_BATCH", 2
    ):
        # First chunk answers, second chunk is dead.
        classifier.side_effect = [{0: "Software Engineer Intern", 1: "Software Engineer Intern"}, None]
        result = stage_listings(db, user.id, listings, _settings(), PullResult())

    assert result.staged == 2
    assert result.dropped == {"classifier unavailable": 1}


def test_chunked_answers_map_back_to_the_right_listing(db: Session, user: User) -> None:
    """Each chunk numbers its answers from zero, so they must be shifted back.

    Getting this wrong does not raise — it silently files the second chunk's
    verdicts against the first chunk's jobs, which would read as a classifier
    that had lost its mind rather than as an off-by-N.
    """
    listings = [
        _listing(id="a", url="https://x/a", title="Software Engineer Intern"),
        _listing(id="b", url="https://x/b", title="ML Research Intern"),
    ]
    with patch("services.discovery.classify_role_families") as classifier, patch(
        "services.discovery._CLASSIFY_BATCH", 1
    ):
        classifier.side_effect = [{0: "Software Engineer Intern"}, {0: "AI and ML Engineer Intern"}]
        stage_listings(db, user.id, listings, _settings(), PullResult())

    rows = _staged(db)
    assert len(rows) == 1
    assert rows[0].external_id == "a"
    # The ML title landed as a filtered row, which is how we know the second
    # chunk's verdict was applied to the second listing and not the first.
    assert [r.external_id for r in _all_rows(db) if r.state is DiscoveryState.filtered] == ["b"]


def test_a_rejected_posting_is_never_judged_twice(db: Session, user: User) -> None:
    """The bug this state exists for, caught by running the pull twice.

    Without a record of the rejection, every run re-classifies every posting it
    has already turned down. That is a bill for the same judgement nightly, and
    because the classifier is not perfectly deterministic, a job rejected last
    night can appear tonight with no explanation. The second run here must reach
    the classifier with nothing at all.
    """
    listing = _listing(title="ML Research Intern")
    _stage(db, user, [listing], {0: "AI and ML Engineer Intern"})

    result, classifier = _stage(db, user, [listing], {0: "Software Engineer Intern"})

    classifier.assert_not_called()
    assert _staged(db) == []
    assert result.duplicates == 1


# --- Enrichment --------------------------------------------------------------


def _enrich(db: Session, user: User, *, text: str, parsed=None, years=((2028, 5), (2029, 5)), fails=False):
    from services.fetch_posting import PostingFetchError
    from schemas.parsing import FetchedPosting

    with patch("services.discovery.fetch_posting") as fetch, patch(
        "services.discovery.parse_job_description"
    ) as parse, patch("services.discovery._your_graduation_dates") as grad:
        grad.return_value = list(years)
        parse.return_value = parsed
        if fails:
            fetch.side_effect = PostingFetchError("needs a browser")
        else:
            fetch.return_value = FetchedPosting(text=text, source="workday", url="https://x/1")
        return enrich_pending(db, user.id, _settings())


def test_a_posting_that_closed_before_you_finish_leaves_the_inbox(
    db: Session, user: User
) -> None:
    """The whole point of reading overnight.

    You should never open a posting to discover it wanted the Class of 2026.
    There is nothing to decide about a job you cannot hold, so it does not
    become a row whose only available action is dismiss — it is read, judged,
    and filed out of sight, with the record kept so tomorrow's pull cannot
    stage it again.
    """
    _stage(db, user, [_listing()], {0: "Software Engineer Intern"})

    count = _enrich(db, user, text="Must be graduating in the Class of 2026.")

    assert count == 1
    assert _staged(db) == []
    row = _all_rows(db)[0]
    assert row.state is DiscoveryState.filtered
    assert row.eligibility["verdict"] == "too_early"
    assert "2026" in row.eligibility["evidence"]


def test_a_posting_needing_your_earlier_date_stays_in_the_inbox(
    db: Session, user: User
) -> None:
    # Not a rejection. It is a decision about which of two true graduation dates
    # to claim, and only you can make it.
    _stage(db, user, [_listing()], {0: "Software Engineer Intern"})

    _enrich(db, user, text="Must be graduating in the Class of 2028.")

    row = _staged(db)[0]
    assert row.state is DiscoveryState.pending
    assert row.eligibility["verdict"] == "eligible_early"


def test_a_posting_that_cannot_be_read_keeps_its_row(db: Session, user: User) -> None:
    """A failed fetch must not cost you the discovery.

    Four in ten ordinary careers sites need a browser. A row you can still click
    through to is worth far more than a pull that gave up, so the fields stay
    null and the UI reads that as "not read" rather than as a verdict.
    """
    _stage(db, user, [_listing()], {0: "Software Engineer Intern"})

    count = _enrich(db, user, text="", fails=True)

    row = _staged(db)[0]
    assert count == 0
    assert row.eligibility is None
    # Not stamped, so a later pass tries again instead of treating it as done.
    assert row.enriched_at is None


def test_reading_is_capped_so_a_first_run_finishes(db: Session, user: User) -> None:
    # A first pull stages hundreds. Reading all of them in one request would
    # take minutes and time out whatever called it.
    listings = [_listing(id=f"f{i}", url=f"https://x/{i}") for i in range(5)]
    _stage(db, user, listings, {i: "Software Engineer Intern" for i in range(5)})

    from schemas.parsing import FetchedPosting

    with patch("services.discovery.fetch_posting") as fetch, patch(
        "services.discovery.parse_job_description", return_value=None
    ), patch("services.discovery._your_graduation_dates", return_value=[(2029, 5)]):
        fetch.return_value = FetchedPosting(text="hello", source="generic", url="https://x/1")
        first = enrich_pending(db, user.id, _settings(), limit=2)

    assert first == 2
    assert sum(1 for r in _staged(db) if r.enriched_at is None) == 3


def test_an_already_read_posting_is_not_read_again(db: Session, user: User) -> None:
    _stage(db, user, [_listing()], {0: "Software Engineer Intern"})
    _enrich(db, user, text="Graduating in 2029.")

    from schemas.parsing import FetchedPosting

    with patch("services.discovery.fetch_posting") as fetch, patch(
        "services.discovery.parse_job_description", return_value=None
    ), patch("services.discovery._your_graduation_dates", return_value=[(2029, 5)]):
        fetch.return_value = FetchedPosting(text="x", source="generic", url="https://x/1")
        again = enrich_pending(db, user.id, _settings())

    assert again == 0
    fetch.assert_not_called()


def test_accepting_carries_the_posting_onto_the_application(
    db: Session, user: User
) -> None:
    """The text is what resume tailoring reads.

    A row that arrived without it would look complete and then quietly refuse to
    tailor, which is the kind of gap you find at the worst moment.
    """
    from services.discovery import accept

    _stage(db, user, [_listing()], {0: "Software Engineer Intern"})
    _enrich(db, user, text="Graduating in 2029 required.")

    application = accept(db, _staged(db)[0], user.id)

    assert application.jd_text == "Graduating in 2029 required."
    assert application.role_family == "Software Engineer Intern"


# --- Fields carried across ---------------------------------------------------


def test_every_location_is_kept_not_just_the_first(db: Session, user: User) -> None:
    # Where a job is happens to be one of the things that decides whether you
    # apply, so dropping the second city loses a real fact.
    _stage(
        db,
        user,
        [_listing(locations=["Seattle, WA", "Austin, TX"])],
        {0: "Software Engineer Intern"},
    )

    assert _staged(db)[0].location == "Seattle, WA, Austin, TX"


def test_the_feed_entry_is_kept_whole(db: Session, user: User) -> None:
    # The filter will be wrong at first, and this is the only record of what the
    # feed actually said when you go to tune it.
    _stage(db, user, [_listing()], {0: "Software Engineer Intern"})

    assert _staged(db)[0].raw["id"] == "feed-1"


def test_resolving_records_the_application_it_became(db: Session, user: User) -> None:
    _stage(db, user, [_listing()], {0: "Software Engineer Intern"})
    application = _application(db, user, posting_url="https://elsewhere/9")

    row = resolve(db, _staged(db)[0], DiscoveryState.accepted, application.id)

    assert row.state is DiscoveryState.accepted
    assert row.application_id == application.id
    assert row.resolved_at is not None


# --- Runs --------------------------------------------------------------------
# The pull became asynchronous because Cloudflare abandons any request the
# origin has not answered in 100 seconds. Asynchronous work that leaves no trace
# is work nobody can trust, so these cover the record it leaves behind.


def test_a_run_is_claimed_before_any_work_happens(db: Session, user: User) -> None:
    from models.discovery_run import RunState
    from services.discovery import start_run

    run = start_run(db, user.id)

    assert run.state is RunState.running
    assert run.finished_at is None


def test_a_second_run_is_refused_while_one_is_going(db: Session, user: User) -> None:
    from services.discovery import RunAlreadyGoing, start_run

    start_run(db, user.id)

    with pytest.raises(RunAlreadyGoing):
        start_run(db, user.id)


def test_a_stale_run_does_not_jam_the_pipeline_forever(
    db: Session, user: User
) -> None:
    """The failure mode that would be invisible and permanent.

    A process killed mid-pull leaves a `running` row behind with nothing to
    finish it. Without this, every future run — nightly, forever — is refused
    with a 409 and the inbox silently stops filling. No honest pull takes an
    hour, so anything older is treated as abandoned.
    """
    from models.discovery_run import DiscoveryRun, RunState
    from services.discovery import start_run

    stale = DiscoveryRun(
        user_id=user.id,
        started_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=3),
    )
    db.add(stale)
    db.commit()

    run = start_run(db, user.id)

    assert run.id != stale.id
    db.refresh(stale)
    assert stale.state is RunState.failed
    assert "Abandoned" in stale.error


def test_another_users_run_does_not_block_yours(db: Session, user: User) -> None:
    from services.discovery import start_run

    other = User(email="other@example.com", password_hash="x")
    db.add(other)
    db.commit()
    start_run(db, other.id)

    # No exception: the claim is per user, like everything else here.
    assert start_run(db, user.id) is not None


def test_a_failed_run_records_why_instead_of_raising(db: Session, user: User) -> None:
    """execute_run has no caller left to raise to.

    The response went out long before it ran, so an exception would vanish into
    a background task and the run would sit as "running" until the stale check
    swept it up an hour later. The error belongs on the row.
    """
    from models.discovery_run import DiscoveryRun, RunState
    from services.discovery import execute_run, start_run

    run = start_run(db, user.id)

    # execute_run owns and closes the session it opens. Here it is being lent
    # the fixture's, so the close is neutralised — otherwise every assertion
    # below hits a detached instance.
    with patch("services.discovery.SessionLocal", return_value=db), patch.object(
        db, "close"
    ), patch("services.discovery.run_pull", side_effect=RuntimeError("feed is down")):
        execute_run(run.id, user.id, _settings())

    row = db.get(DiscoveryRun, run.id)
    assert row.state is RunState.failed
    assert "feed is down" in row.error
    assert row.finished_at is not None


def test_a_successful_run_records_the_counts(db: Session, user: User) -> None:
    from models.discovery_run import DiscoveryRun, RunState
    from services.discovery import execute_run, start_run

    run = start_run(db, user.id)

    with patch("services.discovery.SessionLocal", return_value=db), patch.object(
        db, "close"
    ), patch(
        "services.discovery.run_pull",
        return_value=PullResult(fetched=16502, staged=7, duplicates=3, enriched=5, ruled_out=2),
    ):
        execute_run(run.id, user.id, _settings())

    row = db.get(DiscoveryRun, run.id)
    assert row.state is RunState.succeeded
    assert (row.staged, row.enriched, row.ruled_out) == (7, 5, 2)
    # Per source, so a second source later needs no migration to be counted.
    assert "simplify" in row.sources
