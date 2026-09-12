"""Published notification/response stages and experimental presentation controls."""

from types import SimpleNamespace

import pytest

from negotiator.application.contracts import CommandRequest, StudySpec
from negotiator.application.session import Session, SessionConfig
from negotiator.application.studies import PhaseError, StudyStore
from negotiator.application.synthetic import run_study
from negotiator.domain.actions import Offer
from negotiator.examples import builtin_domain, example_profiles
from negotiator.interaction.presentation import Presenter


def test_synthetic_example_obeys_notification_protocol(tmp_path):
    result = run_study(
        StudySpec(preference_mode="assigned", interaction_protocol="ready-offer-response"), tmp_path
    )
    assert result["synthetic"] is True
    assert len(result["completed_sessions"]) == 1


def test_notification_rejection_and_new_offer_are_distinct_durable_stages(tmp_path):
    store = StudyStore(tmp_path)
    pid = store.create(
        StudySpec(preference_mode="assigned", interaction_protocol="ready-offer-response")
    )["plan_id"]
    store.start(pid)
    state = store.snapshot(pid)
    sid = state["current"]["config"]["session_id"]
    assert state["current"]["interaction_phase"] == "notification"

    def send(kind, rid, **changes):
        return store.command(
            pid, CommandRequest(session_id=sid, kind=kind, request_id=rid, **changes)
        )

    with pytest.raises(PhaseError, match="ready"):
        send("text", "thinking", text="Hotel")
    send("ready", "ready-1", expected_offer_count=0)
    send("ready", "ready-1", expected_offer_count=0)
    assert store.snapshot(pid)["current"]["interaction_phase"] == "offer"
    session = store._sessions[sid]
    bid = min(session.domain.bids(), key=lambda b: session.agent_profile.utility(b, "agent"))
    send("offer", "h1", values=bid.to_dict())
    state = store.snapshot(pid)
    assert state["current"]["interaction_phase"] == "response"
    assert len(state["current"]["offers"]) == 2
    pending = state["current"]["offers"][-1]["offer_id"]
    with pytest.raises(PhaseError):
        send("offer", "h2-too-soon", values=bid.to_dict())
    send("reject", "no-1", expected_offer_count=2, offer_id=pending)
    assert store.snapshot(pid)["current"]["interaction_phase"] == "notification"
    with pytest.raises(PhaseError):
        send("ready", "stale-ready", expected_offer_count=0)
    send("ready", "ready-2", expected_offer_count=2)
    assert len(store.snapshot(pid)["current"]["offers"]) == 2
    send("withdraw", "end")
    store.shutdown()


def test_failed_ready_log_does_not_enable_offer_entry(tmp_path, monkeypatch):
    store = StudyStore(tmp_path)
    pid = store.create(
        StudySpec(preference_mode="assigned", interaction_protocol="ready-offer-response")
    )["plan_id"]
    store.start(pid)
    sid = store.snapshot(pid)["current"]["config"]["session_id"]

    def fail(**kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(store._sessions[sid].journal, "append", fail)
    with pytest.raises(OSError):
        store.command(
            pid,
            CommandRequest(
                session_id=sid, kind="ready", request_id="ready", expected_offer_count=0
            ),
        )
    assert store.snapshot(pid)["current"]["interaction_phase"] == "notification"


def test_gesture_free_condition_preserves_speech_but_sends_no_gesture(tmp_path):
    domain = builtin_domain("fruits")
    human, own = example_profiles(domain)
    session = Session.create(
        tmp_path, SessionConfig("study", "P1", "S1", gestures=False), human, own
    )
    bid = min(domain.bids(), key=lambda b: own.utility(b, "agent"))
    session.submit(Offer("h1", "human", bid), "h1")
    event = session.submit(Offer("a1", "agent", bid), "a1")
    commands = []

    class Bridge:
        config = SimpleNamespace(gestures={"Frustrated": "gesture-file"}, faces={})

        def request(self, session_id, event_id, operation, payload):
            commands.append(payload)
            return {"delivered": True}

    Presenter(session, Bridge()).deliver(event)
    assert commands[0]["text"]
    assert commands[0]["gesture"] is None


def test_jennifer_presentation_replays_mood_after_failed_attempt_write(tmp_path, monkeypatch):
    domain = builtin_domain("fruits")
    human, own = example_profiles(domain)
    now = [0.0]
    session = Session.create(
        tmp_path,
        SessionConfig(
            "study",
            "P2",
            "S2",
            mood_policy="jennifer-2022",
            mood_parameters={"warning_fraction": 0.8, "mild_multiplier": 0.95},
        ),
        human,
        own,
        now=lambda: now[0],
    )
    low = min(domain.bids(), key=lambda b: own.utility(b, "agent"))
    high = max(domain.bids(), key=lambda b: own.utility(b, "agent"))
    commands = []

    class Bridge:
        config = SimpleNamespace(gestures={"Stressed": "stress"}, faces={})

        def request(self, session_id, event_id, operation, payload):
            commands.append(payload)
            return {"delivered": True}

    presenter = Presenter(session, Bridge())
    session.submit(Offer("h1", "human", low), "h1")
    presenter.deliver(session.submit(Offer("a1", "agent", high), "a1"))
    now[0] = 500
    session.submit(Offer("h2", "human", low), "h2")
    event = session.submit(Offer("a2", "agent", high), "a2")
    append = session.journal.append

    def fail(**kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(session.journal, "append", fail)
    with pytest.raises(OSError):
        presenter.deliver(event)
    monkeypatch.setattr(session.journal, "append", append)
    presenter.deliver(event)
    assert commands[-1]["mood"] == "Stressed"
    assert commands[-1]["gesture"] == "stress"
    assert len(commands) == 2
