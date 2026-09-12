import hashlib
import json
import math
import random
from importlib.resources import files

import pytest

from negotiator.domain import Domain, Issue, Preference
from negotiator.domain.actions import Accept, End, Offer
from negotiator.examples import builtin_domain, example_profiles
from negotiator.models.cbom import CBOMModel
from negotiator.strategies import Observation, create_agent, strategy_names
from negotiator.strategies.policies import ac_next, behavior_target, emotion_effect, time_target
from negotiator.strategies.sensitivity import FixedCentroids, awareness, move, move_rates


@pytest.mark.parametrize("t,expected", [(0, 0.9), (0.5, 0.675), (1, 0.4)])
def test_quadratic_time_equation(t, expected):
    assert time_target(t) == pytest.approx(expected)


@pytest.mark.parametrize("n,delta", [(1, 0.1), (2, 0.175), (3, 0.253), (4, 0.325)])
def test_behavior_uses_recent_difference_weights_without_renormalizing(n, delta):
    differences = [0.1, 0.2, 0.3, 0.4][:n]
    expected_delta = sum(
        a * b
        for a, b in zip(
            differences,
            {1: [1], 2: [0.25, 0.75], 3: [0.11, 0.22, 0.66], 4: [0.05, 0.15, 0.3, 0.5]}[n],
            strict=True,
        )
    )
    assert expected_delta == pytest.approx(delta)
    assert behavior_target(0.9, differences, 0.5, awareness=0.5, emotion=0.1) == pytest.approx(
        0.9 + 0.25 * 0.1 - 0.75 * 0.75 * expected_delta
    )


def test_ac_next_equality_reservation_and_no_pending_offer():
    assert ac_next(0.7, 0.7, 0.6)
    assert not ac_next(0.7, 0.7, 0.8)
    assert not ac_next(None, 0.7, 0.0)
    assert not ac_next(0.69, 0.7, 0.0)


def test_categorical_emotion_weights_and_missing_values():
    assert emotion_effect({"Sadness": 1}) == -0.33
    assert emotion_effect({"Happiness": 1}) == 0.165
    assert emotion_effect({"Anger": 0.5, "Surprise": 0.5}) == pytest.approx(0.0825)
    assert emotion_effect(None) is None
    assert emotion_effect({"Neutral": 1}) == 0
    for invalid in ({"new-emotion": 1}, {"Neutral": math.nan}, {"Neutral": -0.1}, {"Neutral": 2}):
        with pytest.raises(ValueError):
            emotion_effect(invalid)


def test_fixed_centroids_preserve_approved_asset_and_have_no_fitting_or_rng_effect():
    raw = files("negotiator").joinpath("data", "solver-centroids.json").read_bytes()
    assert (
        hashlib.sha256(raw).hexdigest()
        == "0aa7b292e53ef6f70511ef1f7341e26cf0ce1642a45d79adcc074db948b95777"
    )
    centers = json.loads(raw)["centers"]
    before = random.getstate()
    model = FixedCentroids()
    assert [model.classify(center) for center in centers] == list(range(5))
    assert random.getstate() == before
    for bad in ([0] * 5, [float("nan")] * 6, [-1] * 6):
        with pytest.raises(ValueError):
            model.classify(bad)


@pytest.mark.parametrize(
    "own,other,expected",
    [
        (0, 0, "silent"),
        (0, 0.1, "nice"),
        (0, -0.1, "nice"),
        (0.1, 0.1, "fortunate"),
        (-0.1, -0.1, "unfortunate"),
        (-0.1, 0.1, "concession"),
        (0.1, -0.1, "selfish"),
    ],
)
def test_legacy_move_categories(own, other, expected):
    assert move(own, other) == expected
    assert sum(move_rates([expected])) == 1


def test_awareness_short_history_no_response_and_category_lag():
    assert awareness([], []) == 0
    assert awareness(["silent"] * 5, ["silent"] * 5) == 0
    assert (
        awareness(
            ["silent", "selfish", "selfish"], ["silent", "silent", "concession", "concession"]
        )
        == 1
    )
    assert awareness(["silent", "selfish"], ["silent"]) == 0


@pytest.mark.parametrize("domain_name", ["holiday", "fruits", "island"])
def test_cbom_adapter_matches_public_model_at_each_update(domain_name):
    from negotiator._vendor.cbom.model import ConflictBasedOpponentModel

    d = builtin_domain(domain_name)
    _, own = example_profiles(d)
    adapter = CBOMModel(own, history_size=4)
    oracle = ConflictBasedOpponentModel(adapter.reference, history_size=4)
    bids = list(d.bids())
    for bid in bids[:12] + bids[-12:]:
        adapter.observe(bid)
        oracle.update({name: str(value) for name, value in bid.items})
        assert adapter.observations == oracle.observations
        estimated = adapter.preference
        for test_bid in bids[::47]:
            assert estimated.utility(test_bid) == pytest.approx(
                oracle.preference.utility({name: str(value) for name, value in test_bid.items}),
                abs=1e-14,
            )
        assert estimated.provenance == "estimated"


@pytest.mark.parametrize("strategy", ["hybrid", "solver-2021", "solver-2025", "tsbt", "babt"])
@pytest.mark.parametrize("count", [0, 1, 2, 8, 9])
def test_strategy_short_and_long_history_is_valid_and_has_no_hidden_profile(strategy, count):
    d = builtin_domain("holiday")
    _, own = example_profiles(d)
    pool = sorted(d.bids(), key=lambda b: own.utility(b, "agent"))
    offers = []
    for i in range(count):
        offers.append(Offer(f"h{i}", "human", pool[i]))
        if i < count - 1:
            offers.append(Offer(f"a{i}", "agent", pool[-1]))
    view = Observation(tuple(offers), 0.2, {"Neutral": 1.0})
    assert not hasattr(view, "human_profile")
    before = random.getstate()
    agent = create_agent(strategy, own, seed=7)
    decision = agent.decide(view)
    assert isinstance(decision.action, (Offer, Accept, End))
    if isinstance(decision.action, Offer):
        d.validate(decision.action.bid)
    assert agent.decide(view) == decision
    assert random.getstate() == before


def test_two_separate_agents_have_identical_seeded_decisions_and_independent_models():
    d = builtin_domain("holiday")
    _, own = example_profiles(d)
    first, second = (create_agent("solver-2025", own, seed=42) for _ in range(2))
    bid = min(d.bids(), key=lambda b: own.utility(b, "agent"))
    view = Observation((Offer("h1", "human", bid),), 0.1)
    assert first.decide(view) == second.decide(view)
    first.model.observe(bid)
    assert first.model.observations == second.model.observations + 1


def test_empty_feasible_pool_ends_and_equality_is_accepted():
    d = Domain("d", (Issue("x", ("a", "b")),))
    own = Preference(d, {"x": 1}, {"x": {"a": 0.3, "b": 0.2}}, reservation=0.8)
    agent = create_agent("hybrid", own)
    assert isinstance(agent.decide(Observation((), 0.1)).action, End)
    feasible = Preference(d, {"x": 1}, {"x": {"a": 1.0, "b": 0.5}})
    pending = Offer("h1", "human", d.bid({"x": "a"}))
    assert isinstance(
        create_agent("hybrid", feasible).decide(Observation((pending,), 0.1)).action, Accept
    )


def test_sensitivity_updates_are_explicitly_different_between_source_generations():
    d = builtin_domain("holiday")
    _, own = example_profiles(d)
    old, recent = (create_agent(name, own) for name in ("solver-2021", "solver-2025"))
    for model in (old, recent):
        model.update_sensitivity("selfish")
        model.update_sensitivity("silent")
        model.update_sensitivity("selfish")
    assert old.delta_multiplier == 2.25
    assert recent.delta_multiplier == 1.5
    recent.update_sensitivity("fortunate")
    assert recent.p1 == pytest.approx(0.5)
    recent.update_sensitivity("concession")
    assert recent.p1 == pytest.approx(0.7)
    assert recent.p2 == pytest.approx(0.6)


def test_observation_time_and_unknown_strategy_fail_clearly():
    for t in (-0.1, 1.1, math.nan):
        with pytest.raises(ValueError):
            Observation((), t)
    with pytest.raises(ValueError):
        create_agent("unknown", example_profiles(builtin_domain("holiday"))[1])
    assert "solver-2025" in strategy_names()


def test_babt_silent_opponent_repeats_previous_bid():
    d = builtin_domain("holiday")
    _, own = example_profiles(d)
    agent = create_agent("babt", own)
    low = min(d.bids(), key=lambda b: own.utility(b, "agent"))
    first = agent.decide(Observation((Offer("h1", "human", low),), 0.1)).action
    assert isinstance(first, Offer)
    second = agent.decide(
        Observation((Offer("h1", "human", low), first, Offer("h2", "human", low)), 0.2)
    ).action
    assert isinstance(second, Offer)
    assert second.bid == first.bid


def test_cached_decision_cannot_outlive_deadline():
    own = example_profiles(builtin_domain("holiday"))[1]
    agent = create_agent("hybrid", own)
    assert isinstance(agent.decide(Observation((), 0.1)).action, Offer)
    assert agent.decide(Observation((), 1.0)).action == End("agent", "deadline")


def test_babt_equal_utility_different_bids_repeat_previous_offer():
    d = Domain("ties", (Issue("x", ("a", "b", "c", "d")),))
    own = Preference(d, {"x": 1}, {"x": {"a": 0.1, "b": 0.1, "c": 0.9, "d": 0.9}})
    for seed in range(10):
        agent = create_agent("babt", own, seed=seed)
        first = agent.decide(Observation((Offer("h1", "human", d.bid({"x": "a"})),), 0.1)).action
        assert isinstance(first, Offer)
        second = agent.decide(
            Observation(
                (
                    Offer("h1", "human", d.bid({"x": "a"})),
                    first,
                    Offer("h2", "human", d.bid({"x": "b"})),
                ),
                0.2,
            )
        ).action
        assert isinstance(second, Offer)
        assert second.bid == first.bid
