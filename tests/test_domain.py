"""Behavioral contracts for domains, bids and elicited preferences."""

import copy
import math
from dataclasses import FrozenInstanceError

import pytest

from negotiator.domain import Bid, Domain, Issue, Preference, ranked_preferences
from negotiator.domain.importers import from_json, from_xml, to_json


def categorical(n=3):
    return Domain("trip", tuple(Issue(f"i{i}", ("a", "b", "c")) for i in range(n)))


def test_bid_identity_preserves_issue_mapping_and_owns_input():
    values = {"first": "a", "second": "b"}
    bid = Bid(values)
    swapped = Bid({"first": "b", "second": "a"})
    assert bid != swapped
    assert len({bid, swapped, Bid(dict(reversed(list(values.items()))))}) == 2
    values["first"] = "b"
    assert bid["first"] == "a"
    with pytest.raises((FrozenInstanceError, AttributeError)):
        bid.items = ()


@pytest.mark.parametrize("n", [1, 3, 4, 6])
def test_ranks_normalize_full_precision_and_pair_odd_issues(n):
    domain = categorical(n)
    ranks = {issue.name: list(issue.values) for issue in domain.issues}
    original = copy.deepcopy(ranks)
    human, agent = ranked_preferences(domain, list(ranks), ranks)
    assert ranks == original
    assert math.fsum(human.weights.values()) == pytest.approx(1, abs=1e-15)
    assert math.fsum(agent.weights.values()) == pytest.approx(1, abs=1e-15)
    assert human.weights["i0"] == n / (n * (n + 1) / 2)
    if n % 2:
        assert agent.weights[f"i{n - 1}"] == human.weights[f"i{n - 1}"]
    assert human.provenance == "elicited"
    assert human.conversion == "rank-linear-paired-v1"
    assert max(human.utility(b) for b in domain.bids()) == pytest.approx(1)


def test_allocation_uses_each_total_and_two_actor_perspectives():
    domain = Domain("supplies", (Issue("water", total=7), Issue("map", total=1)))
    offered = domain.bid({"water": 2, "map": 1})
    complement = domain.for_actor(offered, "agent")
    assert complement == Bid({"water": 5, "map": 0})
    assert domain.for_actor(offered, "human") == offered
    assert domain.canonical(complement, "agent") == offered
    assert domain.size == 16


@pytest.mark.parametrize(
    "values",
    [
        {},
        {"i0": "a"},
        {"i0": "a", "i1": "b", "i2": "z"},
        {"i0": "a", "i1": "b", "i2": "c", "extra": "a"},
    ],
)
def test_invalid_complete_bid_is_rejected(values):
    with pytest.raises(ValueError):
        categorical().bid(values)


@pytest.mark.parametrize("values", [{"x": -1}, {"x": 3}, {"x": True}, {"x": 1.5}])
def test_allocation_rejects_invalid_counts(values):
    with pytest.raises(ValueError):
        Domain("d", (Issue("x", total=2),)).bid(values)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1, True])
def test_profile_rejects_invalid_weights(bad):
    d = Domain("d", (Issue("x", ("a", "b")),))
    with pytest.raises(ValueError):
        Preference(d, {"x": bad}, {"x": {"a": 1, "b": 0}})


def test_profile_validates_without_mutating_and_serializes_provenance():
    d = categorical(1)
    scores = {"i0": {"a": 1.0, "b": 0.7, "c": 0.0}}
    p = Preference(d, {"i0": 1.0}, scores, provenance="assigned")
    scores["i0"]["b"] = 0.1
    assert p.utility(d.bid({"i0": "b"})) == 0.7
    with pytest.raises(TypeError):
        p.weights["i0"] = 0.5
    assert Preference.from_dict(d, p.to_dict()) == p
    with pytest.raises(ValueError, match="sum"):
        Preference(d, {"i0": 0.99}, scores)
    for score in (-0.01, 1.01, math.nan):
        with pytest.raises(ValueError):
            Preference(d, {"i0": 1.0}, {"i0": {"a": score, "b": 0.0, "c": 0.0}})


def test_enumeration_cap_is_explicit_and_includes_exact_boundary():
    exact = Domain("exact", (Issue("a", total=249), Issue("b", total=199)))
    assert len(list(exact.bids())) == 50_000
    large = Domain("large", (Issue("a", total=250), Issue("b", total=199)))
    with pytest.raises(ValueError, match="50,000"):
        list(large.bids())


def test_import_island_without_items_or_name_and_json_roundtrip():
    xml = '<negotiation_domain><utility_space domain_type="Resource Allocation">'
    xml += "".join(f'<issue index="{i + 1}" name="item{i}" max_count="1"/>' for i in range(8))
    xml += "</utility_space></negotiation_domain>"
    imported = from_xml(xml, name="Island")
    assert imported.domain.size == 256
    assert imported.domain.name == "Island"
    assert imported.notes
    assert from_json(to_json(imported.domain)) == imported.domain


def test_xml_entities_and_duplicate_issues_fail():
    with pytest.raises(ValueError):
        from_xml('<!DOCTYPE x [<!ENTITY a "boom">]><x>&a;</x>')
    with pytest.raises(ValueError):
        Domain("x", (Issue("x", ("a",)), Issue("x", ("a",))))


def test_rank_validation_is_complete_and_non_destructive():
    d = categorical(1)
    for ranks in ({"i0": ["a", "b"]}, {"i0": ["a", "b", "b"]}, {}):
        with pytest.raises(ValueError):
            ranked_preferences(d, ["i0"], ranks)
    with pytest.raises(ValueError):
        ranked_preferences(d, [], {"i0": ["a", "b", "c"]})


def test_domain_and_issue_invariants():
    for factory in [
        lambda: Domain("", (Issue("x", ("a",)),)),
        lambda: Domain("x", ()),
        lambda: Issue("", ("a",)),
        lambda: Issue("x", ()),
        lambda: Issue("x", ("a", "a")),
        lambda: Issue("x", total=-1),
        lambda: Issue("x", total=True),
        lambda: Issue("x", ("a",), total=2),
    ]:
        with pytest.raises(ValueError):
            factory()


def test_profile_duplicate_scores_and_extreme_numbers_are_rejected():
    d = categorical(1)
    profile, _ = ranked_preferences(d, ["i0"], {"i0": ["a", "b", "c"]})
    data = profile.to_dict()
    data["scores"]["i0"].append({"value": "a", "score": 0.1})
    with pytest.raises(ValueError, match="Duplicate"):
        Preference.from_dict(d, data)
    from negotiator.domain.preferences import finite_number

    with pytest.raises(ValueError, match="finite"):
        finite_number(10**1000, "score")
    with pytest.raises(ValueError, match="50,000"):
        Issue("large", total=50000)


def test_malformed_domain_json_is_a_validation_error():
    for text in ("[]", '{"name":"x","issues":[1]}', '{"name":"x","issues":null}'):
        with pytest.raises(ValueError):
            from_json(text)


def test_xml_profile_roundtrip_preserves_input_and_full_precision():
    from negotiator.domain.importers import to_xml

    d = categorical(3)
    human, _ = ranked_preferences(
        d, [i.name for i in d.issues], {i.name: list(i.values) for i in d.issues}
    )
    before = human.to_dict()
    result = from_xml(to_xml(d, human))
    assert result.domain == d
    assert result.profile.weights == human.weights
    assert result.profile.scores == human.scores
    assert human.to_dict() == before


def test_profile_and_import_boundaries_reject_ambiguous_input():
    from dataclasses import replace

    from negotiator.domain.actions import Accept, Offer
    from negotiator.domain.importers import from_dict, to_xml
    from negotiator.examples import example_profiles

    d = categorical(1)
    profile, _ = example_profiles(d)
    for change in (
        {"weights": {}},
        {"scores": {"i0": {"a": 1}}},
        {"reservation": 1.1},
        {"provenance": "unrecorded"},
    ):
        with pytest.raises(ValueError):
            replace(profile, **change)
    for fn in (
        lambda: from_dict({"name": "x", "issues": [], "schema_version": 2}),
        lambda: from_json(" " * 2_000_001),
        lambda: from_xml(" " * 2_000_001),
        lambda: from_xml("<x/>"),
        lambda: from_xml("<utility_space><issue/></utility_space>"),
        lambda: to_xml(categorical(2), profile),
        lambda: Offer("", "human", next(d.bids())),
        lambda: Accept("human", ""),
        lambda: Accept("robot", "o"),
        lambda: Domain("mixed", (Issue("x", ("a",)), Issue("y", total=1))),
    ):
        with pytest.raises(ValueError):
            fn()
    with pytest.raises(KeyError):
        next(d.bids())["unknown"]
    assert from_xml(to_xml(d)).domain == d


def test_duplicate_xml_weights_never_silently_change_imported_preferences():
    xml = '<utility_space><issue index="1" name="x"><item value="a" evaluation="1"/></issue><weight index="1" value="0.3"/><weight index="1" value="1"/></utility_space>'
    with pytest.raises(ValueError, match="Duplicate"):
        from_xml(xml)
