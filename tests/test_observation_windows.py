"""Small, independent observation fixtures for decision timing and affect windows."""

import pytest

from negotiator.application.runner import SessionRunner
from negotiator.application.session import Session, SessionConfig
from negotiator.domain.actions import End, Offer
from negotiator.examples import builtin_domain, example_profiles
from negotiator.strategies import Observation, create_agent
from negotiator.strategies.agents import Decision
from negotiator.strategies.policies import emotion_effect


def test_changed_time_is_a_new_observation_even_with_the_same_offer_history():
    own = example_profiles(builtin_domain("fruits"))[1]
    agent = create_agent("hybrid", own)
    first = agent.decide(Observation((), 0.1))
    second = agent.decide(Observation((), 0.8))
    # Independent evaluation of the quadratic curve at the new time.
    assert second.diagnostics["time_target"] == pytest.approx(
        0.2**2 * 0.9 + 2 * 0.2 * 0.8 * 0.7 + 0.8**2 * 0.4
    )
    assert first.diagnostics["time_target"] != second.diagnostics["time_target"]
    assert agent.decide(Observation((), 0.8)) is second


def test_changed_affect_is_not_hidden_by_the_history_cache():
    own = example_profiles(builtin_domain("fruits"))[1]
    agent = create_agent("solver-2025", own)
    assert agent.decide(Observation((), 0.1, {"Happy": 1})).diagnostics["emotion_effect"] == 0.165
    assert agent.decide(Observation((), 0.1, {"Sad": 1})).diagnostics["emotion_effect"] == -0.33


@pytest.mark.parametrize("scores", [{"Happy": 1, "Happiness": 1}, {"Surprise": 1, "Sad": 1}])
def test_categorical_probability_mass_cannot_be_double_counted(scores):
    with pytest.raises(ValueError):
        emotion_effect(scores)


def test_ignored_categories_are_not_renormalized():
    assert emotion_effect({"Happy": 0.2, "Fear": 0.8}) == pytest.approx(0.033)


class RecordingAgent:
    def __init__(self):
        self.views = []

    def decide(self, observation):
        self.views.append(observation)
        return Decision(End("agent", "candidate_exhaustion"))


def observed(session, key, scores, **extra):
    return session.perception(
        {
            "source": "synthetic fixture",
            "emotions": scores,
            "valence": None,
            "arousal": None,
            "missing_reason": "categorical_only",
            **extra,
        },
        key,
    )


def test_runner_averages_only_frames_between_own_offer_and_human_response(tmp_path):
    domain = builtin_domain("fruits")
    human, agent = example_profiles(domain)
    session = Session.create(
        tmp_path, SessionConfig("test", "P1", "S1", first_actor="agent"), human, agent
    )
    observed(session, "stale", {"Sad": 1})
    bid = next(domain.bids())
    session.submit(Offer("a1", "agent", bid), "a1")
    observed(session, "frame-1", {"Happy": 1})
    observed(session, "frame-2", {"Surprise": 1})
    session.submit(Offer("h1", "human", bid), "h1")
    observed(session, "too-late", {"Anger": 1})
    recorder = RecordingAgent()
    SessionRunner(session, agent=recorder).respond()
    assert dict(recorder.views[0].emotions) == {"Happy": 0.5, "Surprise": 0.5}
    event = session.journal.read()[-1]
    assert event.payload["diagnostics"]["affect_window"]["sample_count"] == 2


def test_no_current_window_does_not_reuse_a_previous_emotion(tmp_path):
    domain = builtin_domain("fruits")
    human, agent = example_profiles(domain)
    session = Session.create(
        tmp_path, SessionConfig("test", "P1", "S1", first_actor="agent"), human, agent
    )
    observed(session, "stale", {"Happy": 1})
    bid = next(domain.bids())
    session.submit(Offer("a1", "agent", bid), "a1")
    session.submit(Offer("h1", "human", bid), "h1")
    recorder = RecordingAgent()
    SessionRunner(session, agent=recorder).respond()
    assert recorder.views[0].emotions is None


def test_failed_agent_write_retries_the_identical_decision(tmp_path, monkeypatch):
    human, own = example_profiles(builtin_domain("fruits"))
    session = Session.create(
        tmp_path, SessionConfig("test", "P1", "S1", first_actor="agent"), human, own
    )
    recorder = RecordingAgent()
    runner = SessionRunner(session, agent=recorder)
    append = session.journal.append

    def fail(**kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(session.journal, "append", fail)
    with pytest.raises(OSError):
        runner.respond()
    monkeypatch.setattr(session.journal, "append", append)
    runner.respond()
    assert len(recorder.views) == 1
    assert session.state.status == "ended"
