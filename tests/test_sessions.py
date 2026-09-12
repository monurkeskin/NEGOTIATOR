"""Session, durable journal and replay must agree on every canonical action."""

import json
import os

import pytest

from negotiator.application.session import Session, SessionConfig
from negotiator.domain import Domain, Issue, Preference
from negotiator.domain.actions import Accept, End, Offer
from negotiator.events.journal import Journal, JournalError
from negotiator.events.projection import replay


@pytest.fixture
def setup_session(tmp_path):
    d = Domain("city", (Issue("city", ("Berlin", "London")),))
    human = Preference(d, {"city": 1}, {"city": {"Berlin": 0.9, "London": 0.2}})
    agent = Preference(d, {"city": 1}, {"city": {"Berlin": 0.1, "London": 1}})
    now = [100.0]

    def make(session_id="session-a", **kwargs):
        config = SessionConfig(
            study_id="study",
            participant_id="P001",
            session_id=session_id,
            duration_seconds=10,
            **kwargs,
        )
        return Session.create(tmp_path, config, human, agent, now=lambda: now[0])

    return d, now, make


def test_agreement_snapshot_journal_and_replay_use_actual_bid(setup_session):
    d, now, make = setup_session
    session = make()
    session.submit(Offer("human-1", "human", d.bid({"city": "Berlin"})), "request-1")
    event = session.submit(Offer("agent-1", "agent", d.bid({"city": "London"})), "request-2")
    assert event.payload["utilities"] == {"human": 0.2, "agent": 1.0}
    now[0] += 4
    session.submit(Accept("human", "agent-1"), "request-3")
    snapshot = session.snapshot()
    assert snapshot["status"] == "ended"
    assert snapshot["outcome"]["reason"] == "agreement"
    assert snapshot["outcome"]["utilities"]["human"] == 0.2
    assert snapshot["remaining_seconds"] == 6
    now[0] += 100
    assert session.snapshot()["remaining_seconds"] == 6
    restored = replay(session.journal.read())
    assert restored.to_dict() == session.state.to_dict()
    reopened = Session.open(session.journal.path)
    assert reopened.snapshot()["outcome"] == snapshot["outcome"]
    assert len([e for e in reopened.journal.read() if e.kind == "session.ended"]) == 1


def test_duplicate_request_is_idempotent_but_conflicting_reuse_is_rejected(setup_session):
    d, _, make = setup_session
    session = make()
    action = Offer("o1", "human", d.bid({"city": "Berlin"}))
    first = session.submit(action, "request-1")
    assert session.submit(action, "request-1") == first
    assert len(session.state.offers) == 1
    with pytest.raises(ValueError, match="different"):
        session.submit(Offer("o2", "human", d.bid({"city": "London"})), "request-1")
    with pytest.raises(ValueError, match="turn"):
        session.submit(Offer("o2", "human", d.bid({"city": "London"})), "request-2")


@pytest.mark.parametrize("offset", [10, 11])
def test_deadline_rejects_new_offer_and_terminates_once(setup_session, offset):
    d, now, make = setup_session
    session = make()
    now[0] += offset
    result = session.submit(Offer("too-late", "human", d.bid({"city": "Berlin"})), "late")
    assert result.kind == "session.ended"
    assert result.payload["reason"] == "deadline"
    assert session.state.offers == []
    assert session.snapshot()["remaining_seconds"] == 0
    session.tick()
    assert len(session.journal.read()) == 2


@pytest.mark.parametrize("offer_count", [0, 1])
@pytest.mark.parametrize("reason", ["withdrawal", "candidate_exhaustion", "operator"])
def test_short_endings_replay_and_close_resources_once(setup_session, offer_count, reason):
    d, _, make = setup_session
    session = make()
    closed = []
    session.on_close(lambda: closed.append(True))
    if offer_count:
        session.submit(Offer("o1", "human", d.bid({"city": "Berlin"})), "offer")
    action = End("human", reason)
    ended = session.submit(action, "end")
    assert session.submit(action, "end") == ended
    assert closed == [True]
    assert len(replay(session.journal.read()).offers) == offer_count
    with pytest.raises(ValueError, match="ended"):
        session.submit(action, "end-again")


def test_two_sessions_are_isolated_and_previous_records_survive(setup_session):
    d, _, make = setup_session
    first = make()
    first.submit(Offer("o1", "human", d.bid({"city": "Berlin"})), "request")
    second = make("session-b")
    second.submit(Offer("o1", "human", d.bid({"city": "London"})), "request")
    assert first.snapshot()["offers"][0]["bid"] == {"city": "Berlin"}
    assert second.snapshot()["offers"][0]["bid"] == {"city": "London"}
    assert first.journal.path != second.journal.path
    with pytest.raises(FileExistsError):
        make()


def test_write_failure_never_changes_visible_state_or_acknowledges(setup_session, monkeypatch):
    d, _, make = setup_session
    session = make()
    before = session.journal.path.read_bytes()

    def fail(_):
        raise OSError("disk failure")

    monkeypatch.setattr(os, "fsync", fail)
    with pytest.raises(JournalError):
        session.submit(Offer("o1", "human", d.bid({"city": "Berlin"})), "request")
    assert session.state.offers == []
    assert session.journal.path.read_bytes() == before
    with pytest.raises(JournalError):
        session.note("after failure", "note")


def test_reopen_active_session_records_interruption_instead_of_resuming(setup_session):
    _, _, make = setup_session
    session = make()
    reopened = Session.open(session.journal.path)
    assert reopened.snapshot()["outcome"]["reason"] == "interrupted"
    assert len(reopened.journal.read()) == 2
    Session.open(reopened.journal.path)
    assert len(reopened.journal.read()) == 2


def test_corruption_is_detected_and_original_bytes_preserved(setup_session):
    _, _, make = setup_session
    session = make()
    raw = session.journal.path.read_text(encoding="utf-8")
    session.journal.path.write_text(raw.replace('"P001"', '"P002"'), encoding="utf-8")
    corrupted = session.journal.path.read_bytes()
    with pytest.raises(JournalError, match="hash"):
        Session.open(session.journal.path)
    assert session.journal.path.read_bytes() == corrupted


def test_truncated_last_line_is_not_silently_discarded(setup_session):
    _, _, make = setup_session
    session = make()
    with session.journal.path.open("ab") as stream:
        stream.write(b'{"sequence":2')
    raw = session.journal.path.read_bytes()
    with pytest.raises(JournalError, match="truncated"):
        Journal(session.journal.path).read()
    assert session.journal.path.read_bytes() == raw


def test_manifest_hashes_configuration_and_participant_view_excludes_agent_profile(setup_session):
    _, _, make = setup_session
    session = make(condition="hidden-condition")
    manifest = json.loads(
        session.journal.path.with_name("manifest.json").read_text(encoding="utf-8")
    )
    assert len(manifest["configuration_sha256"]) == 64
    participant = session.snapshot(role="participant")
    encoded = json.dumps(participant)
    assert "hidden-condition" not in encoded
    assert "agent_profile" not in encoded
    assert "human_profile" in participant
    assert "condition" in session.snapshot()["config"]


def test_affect_values_and_extrema_are_independent_and_missing_is_explicit(setup_session):
    _, _, make = setup_session
    session = make()
    session.perception({"valence": -0.7, "arousal": -0.2, "source": "manual"}, "p1")
    session.perception({"valence": 0.9, "arousal": 0.4, "source": "manual"}, "p2")
    session.perception(
        {"valence": None, "arousal": None, "source": "manual", "missing_reason": "not_observed"},
        "p3",
    )
    values = [e.payload for e in session.journal.read() if e.kind == "perception.observed"]
    assert [v["arousal"] for v in values] == [-0.2, 0.4, None]
    with pytest.raises(ValueError):
        session.perception({"valence": float("nan"), "arousal": 0.0, "source": "manual"}, "bad")


def test_allocation_utility_is_evaluated_for_correct_actor(tmp_path):
    d = Domain("water", (Issue("bottles", total=7),))
    p = Preference(d, {"bottles": 1}, {"bottles": {i: i / 7 for i in range(8)}})
    s = Session.create(tmp_path, SessionConfig("study", "P001", "allocation"), p, p)
    event = s.submit(Offer("o1", "human", d.bid({"bottles": 2})), "offer")
    assert event.payload["utilities"] == {"human": 2 / 7, "agent": 5 / 7}


@pytest.mark.parametrize("bad_id", ["../escape", "/absolute", "", "real/name", "a\\b"])
def test_session_identity_cannot_escape_store(bad_id):
    with pytest.raises(ValueError):
        SessionConfig("study", "P001", bad_id)


@pytest.mark.parametrize("acceptance", [False, True])
def test_calculation_crossing_deadline_does_not_commit_offer_or_agreement(
    setup_session, monkeypatch, acceptance
):
    d, now, make = setup_session
    s = make(first_actor="agent" if acceptance else "human")
    if acceptance:
        s.submit(Offer("a1", "agent", d.bid({"city": "London"})), "agent")
    original = s._utilities

    def slow_utility(bid):
        now[0] += 10
        return original(bid)

    monkeypatch.setattr(s, "_utilities", slow_utility)
    action = (
        Accept("human", "a1") if acceptance else Offer("h1", "human", d.bid({"city": "Berlin"}))
    )
    event = s.submit(action, "slow")
    assert event.kind == "session.ended"
    assert event.payload["reason"] == "deadline"
    assert event.payload["agreement"] is None


@pytest.mark.parametrize(
    "changes", [dict(duration_seconds=0), dict(seed=True), dict(sequence_index=0)]
)
def test_invalid_configuration_never_creates_a_trial(changes):
    with pytest.raises(ValueError):
        SessionConfig("s", "p", "trial", **changes)


@pytest.mark.parametrize(
    "values",
    [
        {},
        {"source": "manual"},
        {"source": "manual", "valence": 2, "arousal": 0},
        {"source": "manual", "valence": 0, "arousal": 0, "emotions": {"unknown": 1}},
        {"source": "manual", "valence": 0, "arousal": 0, "emotions": {"Happy": 1.1}},
    ],
)
def test_invalid_observation_cannot_contaminate_durable_data(setup_session, values):
    _, _, make = setup_session
    s = make()
    before = s.journal.path.read_bytes()
    with pytest.raises(ValueError):
        s.perception(values, "invalid")
    assert s.journal.path.read_bytes() == before


def test_reserved_transitions_and_empty_notes_cannot_bypass_session_validation(setup_session):
    _, _, make = setup_session
    s = make()
    assert s.pending is None
    for fn in (
        lambda: s.record("offer.committed", {}, "invalid"),
        lambda: s.note(" ", "invalid"),
        lambda: s.snapshot(role="unknown"),
    ):
        with pytest.raises(ValueError):
            fn()
    assert len(s.journal.read()) == 1


def test_resource_failure_still_closes_other_resources_and_keeps_terminal_clock(setup_session):
    _, now, make = setup_session
    s = make()
    closed = []

    def fail():
        raise RuntimeError("synthetic device failure")

    s.on_close(fail)
    s.on_close(lambda: closed.append(True))
    now[0] += 10
    s.tick()
    assert closed == [True]
    assert s.snapshot()["remaining_seconds"] == 0
    assert s.journal.read()[-1].kind == "resource.close_failed"
    with pytest.raises(ValueError):
        s.on_close(fail)
    assert s.pending is None


def test_manifest_mismatch_and_empty_journal_fail_before_recovery(setup_session, tmp_path):
    _, _, make = setup_session
    s = make()
    manifest = s.journal.path.with_name("manifest.json")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["configuration"]["config"]["seed"] = 2
    manifest.write_text(json.dumps(data), encoding="utf-8")
    before = s.journal.path.read_bytes()
    with pytest.raises(JournalError):
        Session.open(s.journal.path)
    assert s.journal.path.read_bytes() == before
    with pytest.raises(JournalError):
        Session(Journal.create(tmp_path / "empty", {}))


def test_duplicate_offer_and_below_reservation_acceptance_preserve_state(setup_session):
    from dataclasses import replace

    d, _, make = setup_session
    s = make()
    s.submit(Offer("h", "human", d.bid({"city": "Berlin"})), "h")
    with pytest.raises(ValueError, match="unique"):
        s.submit(Offer("h", "agent", d.bid({"city": "London"})), "duplicate")
    s.submit(Offer("a", "agent", d.bid({"city": "London"})), "a")
    s.human_profile = replace(s.human_profile, reservation=0.8)
    with pytest.raises(ValueError, match="reservation"):
        s.submit(Accept("human", "a"), "accept")
    assert s.state.status == "active" and len(s.state.offers) == 2


def test_concurrent_writer_is_detected_before_acknowledging_stale_state(setup_session):
    _, _, make = setup_session
    s = make()
    other = Session(Journal(s.journal.path))
    s.note("first writer", "one")
    before = s.journal.path.read_bytes()
    with pytest.raises(JournalError, match="another writer"):
        other.note("stale writer", "two")
    assert s.journal.path.read_bytes() == before


def test_journal_append_rejects_cross_session_and_duplicate_request_before_write(setup_session):
    _, _, make = setup_session
    s = make()
    before = s.journal.path.read_bytes()
    for sid, rid in [("different-session", "other"), (s.config.session_id, "session-start")]:
        with pytest.raises(JournalError):
            s.journal.append(
                session_id=sid,
                kind="operator.note",
                payload={},
                request_id=rid,
                fingerprint="synthetic",
                elapsed_seconds=0,
                expected_sequence=2,
            )
        assert s.journal.path.read_bytes() == before


def test_projection_rejects_impossible_lifecycle_transitions(setup_session):
    from negotiator.events.journal import Event, canonical_json

    d, _, make = setup_session
    s = make()
    start = s.journal.read()[0]
    offer = s.submit(Offer("o", "human", d.bid({"city": "Berlin"})), "offer")
    end = s.submit(End("human", "withdrawal"), "end")

    def at(event, sequence):
        data = event.to_dict()
        data["sequence"] = sequence
        return Event(canonical_json(data))

    cases = (
        [offer],
        [start, at(start, 2)],
        [start, end],
        [start, at(end, 2), at(offer, 3)],
        [start, at(end, 2), at(end, 3)],
    )
    for events in cases:
        with pytest.raises(JournalError):
            replay(events)
    data = at(start, 1).to_dict()
    data["kind"] = "operator.note"
    with pytest.raises(JournalError):
        replay([Event(canonical_json(data))])


def test_agreement_is_private_in_participant_view(setup_session):
    d, _, make = setup_session
    s = make(first_actor="agent")
    s.submit(Offer("a", "agent", d.bid({"city": "London"})), "a")
    s.submit(Accept("human", "a"), "accept")
    assert s.snapshot(role="participant")["outcome"]["utilities"] == {"human": 0.2}
    assert s.snapshot()["outcome"]["utilities"]["agent"] == 1
