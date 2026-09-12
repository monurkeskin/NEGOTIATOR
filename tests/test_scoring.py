"""A paper's reward threshold is not a constraint on accepting an offer."""

import pytest

from negotiator.analysis.report import read_session
from negotiator.application.session import Session, SessionConfig
from negotiator.domain.actions import Accept, Offer
from negotiator.examples import builtin_domain, example_profiles


def test_below_target_agreement_keeps_utility_and_receives_zero_game_score(tmp_path):
    domain = builtin_domain("fruits")
    human, agent = example_profiles(domain)
    human = type(human)(domain, human.weights, human.scores, reservation=0)
    session = Session.create(
        tmp_path,
        SessionConfig(
            "s",
            "P1",
            "S1",
            first_actor="agent",
            score_targets={"human": 0.4},
            reward_minimums={"human": 0.4},
        ),
        human,
        agent,
    )
    bid = next(b for b in domain.bids() if 0 < human.utility(b) < 0.4)
    session.submit(Offer("a1", "agent", bid), "a1")
    event = session.submit(Accept("human", "a1"), "accept")
    assert event.payload["reason"] == "agreement"
    assert event.payload["utilities"]["human"] == pytest.approx(human.utility(bid))
    assert event.payload["payoffs"]["human"] == 0
    assert session.snapshot()["outcome"] == event.payload
    participant = session.snapshot(role="participant")
    assert set(participant["outcome"]["payoffs"]) == {"human"}
    assert set(participant["config"]["score_targets"]) == {"human"}
    result = read_session(session.journal.path)
    assert result["outcome"]["payoffs"]["human"] == 0


@pytest.mark.parametrize("value,expected", [(0.399999, 0), (0.4, 0.4), (1.0, 1.0)])
def test_reward_boundary_has_no_rounding(value, expected):
    from negotiator.domain.scoring import reward_scores

    assert (
        reward_scores({"human": value, "agent": 0.5}, {"human": 0.4}, "agreement")["human"]
        == expected
    )


def test_missing_reward_is_not_fabricated_as_zero():
    from negotiator.domain.scoring import reward_scores

    assert reward_scores(None, {"human": 0.4}, "interrupted") is None
    assert reward_scores(None, {"human": 0.4}, "deadline") == {"human": 0, "agent": 0}


@pytest.mark.parametrize(
    "minimums", [{"someone": 0.4}, {"human": -1}, {"human": float("nan")}, {"human": 2}]
)
def test_invalid_rules_are_rejected_before_session_creation(minimums):
    with pytest.raises(ValueError):
        SessionConfig("s", "P1", "S1", reward_minimums=minimums)
