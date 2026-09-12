"""Oracles for the order and Nash comparison in the 2025 paper's Algorithm 1."""

import pytest

from negotiator.domain.actions import Offer
from negotiator.examples import builtin_domain, example_profiles
from negotiator.strategies import Observation, create_agent
from negotiator.strategies.policies import time_target


def agent_and_history():
    domain = builtin_domain("fruits")
    _, own = example_profiles(domain)
    agent = create_agent("solver-2025", own, seed=12)
    low = min(domain.bids(), key=lambda b: own.utility(b, "agent"))
    high = max(domain.bids(), key=lambda b: own.utility(b, "agent"))
    return agent, tuple(
        Offer(str(i), "human" if i % 2 == 0 else "agent", low if i % 2 == 0 else high)
        for i in range(17)
    )


def test_silent_adaptation_reduces_behavior_response():
    agent, _ = agent_and_history()
    before = agent.delta_multiplier
    agent.update_sensitivity("silent")
    assert 0 < agent.delta_multiplier < before


def test_adaptation_precedes_current_time_curve(monkeypatch):
    agent, history = agent_and_history()

    def adapt(received, own_offers):
        agent.p1 = 0.3
        agent.awareness = 0.6
        return "fortunate"

    monkeypatch.setattr(agent, "_sensitivity", adapt)
    result = agent.decide(Observation(history, 0.5, {"Happy": 1}))
    assert result.diagnostics["time_target"] == pytest.approx(time_target(0.5, 0.9, 0.3, 0.4))
    assert result.diagnostics["sensitivity"] == "fortunate"
    assert "next_sensitivity" not in result.diagnostics


def test_nash_candidate_is_compared_with_generated_candidate(monkeypatch):
    agent, history = agent_and_history()
    # Independent exhaustive oracle, with the production opponent estimate frozen
    # after the same received offers. No true participant preference is supplied.
    for offer in history:
        if offer.actor == "human":
            agent.model.observe(offer.bid)
            agent._seen.add(offer.offer_id)
    expected = max(agent._pool, key=lambda item: item[0] * agent.model.preference.utility(item[1]))
    low = min(agent._pool, key=lambda item: item[0])
    monkeypatch.setattr(agent, "_choose_below", lambda target: low)
    result = agent.decide(Observation(history, 0.5))
    assert expected[0] > low[0]
    assert isinstance(result.action, Offer)
    assert result.action.bid == expected[1]
    assert result.diagnostics["candidate_rule"] == "nash-improves-own-utility"


def test_adaptation_threshold_and_constants_are_recorded():
    agent, history = agent_and_history()
    result = agent.decide(Observation(history[:3], 0.1))
    assert result.diagnostics["method_parameters"]["adaptation_min_human_offers"] == 9
    assert result.diagnostics["method_parameters"]["parameter_evidence"] == "maintained-choices"
    assert result.diagnostics["nash_comparison"] == "warmup"


@pytest.mark.parametrize(
    "parameters",
    [
        {"adaptation_min_human_offers": 1},
        {"adaptation_min_human_offers": 2.5},
        {"concession_step": 0},
        {"silent_multiplier": 1},
        {"selfish_multiplier": 1},
        {"unlisted": 1},
    ],
)
def test_invalid_method_choices_cannot_start_a_session(parameters):
    from negotiator.application.contracts import Condition

    with pytest.raises(ValueError):
        Condition(strategy="solver-2025", strategy_parameters=parameters)


def test_configured_adaptation_and_non_solver_parameters_are_checked():
    from negotiator.application.contracts import Condition

    agent, _ = agent_and_history()
    updated = create_agent(
        "solver-2025", agent.own, parameters={"concession_step": 0.1, "silent_multiplier": 0.8}
    )
    updated.update_sensitivity("concession")
    assert updated.p1 == pytest.approx(0.8)
    updated.update_sensitivity("fortunate")
    assert updated.p1 == pytest.approx(0.7)
    updated.update_sensitivity("silent")
    assert updated.delta_multiplier == 0.8
    with pytest.raises(ValueError):
        Condition(strategy="hybrid", strategy_parameters={"concession_step": 0.1})
