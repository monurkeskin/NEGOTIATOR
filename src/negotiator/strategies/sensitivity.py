"""Legacy six-category move analysis and fixed-centroid classification."""

import json
from collections import Counter
from collections.abc import Sequence
from importlib.resources import files
from math import fsum

from negotiator.domain.preferences import finite_number

MOVE_ORDER = ("silent", "nice", "fortunate", "unfortunate", "concession", "selfish")
CLASS_ORDER = ("standard", "silent", "selfish", "fortunate", "concession")


def move(own_delta: float, other_delta: float, *, threshold: float = 0.0) -> str:
    own_delta = 0.0 if abs(own_delta) <= threshold else own_delta
    other_delta = 0.0 if abs(other_delta) <= threshold else other_delta
    if own_delta == 0:
        return "silent" if other_delta == 0 else "nice"
    if own_delta > 0 and other_delta > 0:
        return "fortunate"
    if own_delta < 0 and other_delta < 0:
        return "unfortunate"
    if own_delta < 0 and other_delta > 0:
        return "concession"
    return "selfish"


def move_rates(moves: Sequence[str]) -> tuple[float, ...]:
    counts = Counter(moves)
    if set(counts) - set(MOVE_ORDER):
        raise ValueError("Unknown move category.")
    return tuple(counts[name] / len(moves) if moves else 0.0 for name in MOVE_ORDER)


def awareness(agent_moves: Sequence[str], human_moves: Sequence[str]) -> float:
    """Legacy category-change response with one human-move lag; short histories are bounded."""
    changes = responses = 0
    for index in range(1, min(len(agent_moves), len(human_moves) - 1)):
        if agent_moves[index] != agent_moves[index - 1]:
            changes += 1
            responses += human_moves[index + 1] != human_moves[index]
    return responses / changes if changes else 0.0


class FixedCentroids:
    def __init__(self) -> None:
        data = json.loads(
            files("negotiator")
            .joinpath("data", "solver-centroids.json")
            .read_text(encoding="utf-8")
        )
        self.centers = tuple(tuple(float(v) for v in center) for center in data["centers"])
        if len(self.centers) != 5 or any(len(c) != 6 for c in self.centers):
            raise ValueError("Solver asset must have five centers and six ordered move features.")

    def classify(self, features: Sequence[float]) -> int:
        if len(features) != 6 or any(
            not 0 <= finite_number(v, "Move frequency") <= 1 for v in features
        ):
            raise ValueError("Provide six finite move frequencies in [0, 1].")
        return min(
            range(len(self.centers)),
            key=lambda index: fsum(
                (a - b) ** 2 for a, b in zip(features, self.centers[index], strict=True)
            ),
        )
