"""Published quadratic, reciprocal and categorical emotion policy components."""

from collections.abc import Mapping, Sequence
from math import fsum

from negotiator.domain.preferences import finite_number

DIFFERENCE_WEIGHTS = {1: (1.0,), 2: (0.25, 0.75), 3: (0.11, 0.22, 0.66), 4: (0.05, 0.15, 0.3, 0.5)}
EMOTION_WEIGHTS = {
    "Surprise": 0.33,
    "Happiness": 0.165,
    "Happy": 0.165,
    "Neutral": 0.0,
    "Disgust": 0.0,
    "Fear": 0.0,
    "Anger": -0.165,
    "Sadness": -0.33,
    "Sad": -0.33,
    "Contempt": 0.0,
}


def time_target(t: float, p0: float = 0.9, p1: float = 0.7, p2: float = 0.4) -> float:
    return (1 - t) ** 2 * p0 + 2 * (1 - t) * t * p1 + t * t * p2


def behavior_target(
    previous: float,
    differences: Sequence[float],
    t: float,
    *,
    awareness: float = 0.0,
    emotion: float = 0.0,
    multiplier: float = 1.0,
) -> float:
    recent = list(differences[-4:])
    delta = (
        fsum(u * w for u, w in zip(recent, DIFFERENCE_WEIGHTS[len(recent)], strict=True))
        if recent
        else 0.0
    )
    return (
        previous
        + awareness**2 * emotion
        - (1 - awareness**2) * (0.5 + 0.5 * t) * delta * multiplier
    )


def categorical_probabilities(probabilities: Mapping[str, float]) -> dict[str, float]:
    canonical = {}
    aliases = {"Happiness": "Happy", "Sadness": "Sad"}
    for name, probability in probabilities.items():
        if name not in EMOTION_WEIGHTS:
            raise ValueError(f"Unknown categorical emotion {name!r}.")
        name = aliases.get(name, name)
        if name in canonical:
            raise ValueError("Duplicate aliases for the same categorical emotion.")
        value = finite_number(probability, "Emotion probability")
        if not 0 <= value <= 1:
            raise ValueError("Emotion probabilities must lie in [0, 1].")
        canonical[name] = value
    if not canonical or fsum(canonical.values()) > 1 + 1e-6:
        raise ValueError("Categorical probabilities need nonempty mass no greater than one.")
    return canonical


def emotion_effect(probabilities: Mapping[str, float] | None) -> float | None:
    if probabilities is None:
        return None
    return fsum(
        EMOTION_WEIGHTS[name] * value
        for name, value in categorical_probabilities(probabilities).items()
    )


def ac_next(received: float | None, proposed: float, reservation: float) -> bool:
    return received is not None and received >= max(proposed, reservation)
