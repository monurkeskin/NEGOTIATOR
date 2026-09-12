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
