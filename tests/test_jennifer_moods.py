"""Independent mood priority cases from the Jennifer algorithm and tables."""

import pytest

from negotiator.interaction.mood import JenniferMoodPolicy


@pytest.mark.parametrize(
    "year,positive,negative,mild,accept,hurry,end",
    [
        (2021, "Pleasant", "Dissatisfied", "Mild", "Acceptance", "Hurry up", "Times up"),
        (2022, "Pleasant", "Unpleasant", "Mild", "Satisfied", "Stressed", "Times up"),
    ],
)
def test_published_mood_priority_and_single_warning(
    year, positive, negative, mild, accept, hurry, end
):
    policy = JenniferMoodPolicy(year, warning_fraction=0.8, reservation=0.3)
    assert policy.observe(0.4, 0.1, next_utility=0.9, mild_threshold=0.7) is None
    assert policy.observe(0.45, 0.2, next_utility=0.9, mild_threshold=0.7) == positive
    assert policy.observe(0.45, 0.3, next_utility=0.9, mild_threshold=0.7) == "Neutral"
    assert policy.observe(0.4, 0.4, next_utility=0.9, mild_threshold=0.7) == negative
    assert policy.observe(0.75, 0.5, next_utility=0.9, mild_threshold=0.7) == mild
    assert policy.observe(0.2, 0.8, next_utility=0.9, mild_threshold=0.7) == hurry
    assert policy.observe(0.2, 0.9, next_utility=0.9, mild_threshold=0.7) == "Offended"
    assert policy.observe(0.9, 0.95, next_utility=0.9, mild_threshold=0.7) == accept
    assert policy.observe(0.9, 1, next_utility=0.9, mild_threshold=0.7) == end


def test_mood_requires_explicit_warning_threshold_and_valid_utilities():
    with pytest.raises((TypeError, ValueError)):
        JenniferMoodPolicy(2022, reservation=0.3)
    with pytest.raises(ValueError):
        JenniferMoodPolicy(2022, warning_fraction=1.2, reservation=0.3)


@pytest.mark.parametrize("year", [2021, 2022])
@pytest.mark.parametrize("reservation", [0.0, 0.1, 0.6])
def test_social_offended_threshold_is_independent_of_reservation(year, reservation):
    policy = JenniferMoodPolicy(
        year, warning_fraction=0.8, reservation=reservation, offended_threshold=0.3
    )
    policy.observe(0.4, 0.1, next_utility=0.9, mild_threshold=0.7)
    assert policy.observe(0.2, 0.2, next_utility=0.9, mild_threshold=0.7) == "Offended"


@pytest.mark.parametrize("threshold", [-0.1, 1.1, float("nan"), True])
def test_social_threshold_must_be_a_finite_unit_interval_number(threshold):
    with pytest.raises(ValueError):
        JenniferMoodPolicy(2022, warning_fraction=0.8, reservation=0, offended_threshold=threshold)


def test_legacy_policy_keeps_its_recorded_reservation_based_behavior():
    policy = JenniferMoodPolicy(2022, warning_fraction=0.8, reservation=0)
    policy.observe(0.4, 0.1, next_utility=0.9, mild_threshold=0.7)
    assert policy.observe(0.2, 0.2, next_utility=0.9, mild_threshold=0.7) == "Unpleasant"


def test_threshold_equality_and_acceptance_keep_their_separate_rules():
    policy = JenniferMoodPolicy(2022, warning_fraction=0.8, reservation=0.6, offended_threshold=0.3)
    policy.observe(0.4, 0.1, next_utility=0.9, mild_threshold=0.7)
    assert policy.observe(0.3, 0.2, next_utility=0.9, mild_threshold=0.7) == "Unpleasant"
    assert policy.observe(0.5, 0.3, next_utility=0.4, mild_threshold=0.7) == "Pleasant"
    assert policy.observe(0.6, 0.4, next_utility=0.4, mild_threshold=0.7) == "Satisfied"


@pytest.mark.parametrize(
    "policy,parameters",
    [
        ("unknown", {}),
        ("generic", {"offended_threshold": 0.3}),
        ("jennifer-2022", {}),
        ("jennifer-2021", {"warning_fraction": 1.2, "mild_multiplier": 0.95}),
    ],
)
def test_direct_session_api_rejects_invalid_presentation_before_writing(
    tmp_path, policy, parameters
):
    from negotiator.application.session import Session, SessionConfig
    from negotiator.examples import builtin_domain, example_profiles

    human, agent = example_profiles(builtin_domain("fruits"))
    with pytest.raises(ValueError):
        Session.create(
            tmp_path,
            SessionConfig("study", "P1", "S1", mood_policy=policy, mood_parameters=parameters),
            human,
            agent,
        )
    assert not list(tmp_path.iterdir())
