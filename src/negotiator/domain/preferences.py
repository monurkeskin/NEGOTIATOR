"""Full-precision additive utilities and versioned rank conversion."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import fsum, isclose, isfinite
from types import MappingProxyType
from typing import Any

from .values import Actor, Bid, Domain, Value


def finite_number(value: float, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite number.")
    try:
        result = float(value)
    except OverflowError as exc:
        raise ValueError(f"{label} must be a finite number.") from exc
    if not isfinite(result):
        raise ValueError(f"{label} must be a finite number.")
    return result


@dataclass(frozen=True)
class Preference:
    domain: Domain
    weights: Mapping[str, float]
    scores: Mapping[str, Mapping[Value, float]]
    provenance: str = "assigned"
    reservation: float = 0.0
    conversion: str | None = None

    def __post_init__(self) -> None:
        names = {i.name for i in self.domain.issues}
        if set(self.weights) != names or set(self.scores) != names:
            raise ValueError("Preference must describe exactly the domain's issues.")
        weights = {name: finite_number(w, "Issue weight") for name, w in self.weights.items()}
        if any(w < 0 for w in weights.values()) or not isclose(
            fsum(weights.values()), 1.0, rel_tol=0.0, abs_tol=1e-12
        ):
            raise ValueError("Nonnegative issue weights must sum to 1 at full precision.")
        scores = {}
        for issue in self.domain.issues:
            source = self.scores[issue.name]
            expected = int if self.domain.allocation else str
            if any(type(v) is not expected for v in source) or set(source) != set(issue.values):
                raise ValueError(f"Preference must score every value of {issue.name}.")
            values = {v: finite_number(s, "Value score") for v, s in source.items()}
            if any(s < 0 or s > 1 for s in values.values()):
                raise ValueError("Value scores must be in [0, 1].")
            scores[issue.name] = MappingProxyType(values)
        reservation = finite_number(self.reservation, "Reservation")
        if not 0 <= reservation <= 1:
            raise ValueError("Reservation must be in [0, 1].")
        if self.provenance not in ("assigned", "elicited", "estimated"):
            raise ValueError("Unknown profile provenance.")
        object.__setattr__(self, "weights", MappingProxyType(weights))
        object.__setattr__(self, "scores", MappingProxyType(scores))
        object.__setattr__(self, "reservation", reservation)

    def utility(self, canonical_bid: Bid, actor: Actor = "human") -> float:
        bid = self.domain.for_actor(canonical_bid, actor)
        return fsum(
            self.weights[i.name] * self.scores[i.name][bid[i.name]] for i in self.domain.issues
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "weights": dict(self.weights),
            "scores": {
                i.name: [{"value": v, "score": self.scores[i.name][v]} for v in i.values]
                for i in self.domain.issues
            },
            "provenance": self.provenance,
            "reservation": self.reservation,
            "conversion": self.conversion,
        }

    @classmethod
    def from_dict(cls, domain: Domain, data: Mapping[str, Any]) -> "Preference":
        for entries in data["scores"].values():
            keys = [entry["value"] for entry in entries]
            if len(keys) != len(set(keys)):
                raise ValueError("Duplicate profile value scores are not allowed.")
        scores = {
            name: {entry["value"]: entry["score"] for entry in entries}
            for name, entries in data["scores"].items()
        }
        return cls(
            domain,
            data["weights"],
            scores,
            data.get("provenance", "assigned"),
            data.get("reservation", 0.0),
            data.get("conversion"),
        )


def ranked_preferences(
    domain: Domain,
    issue_order: Sequence[str],
    value_order: Mapping[str, Sequence[Value]],
) -> tuple[Preference, Preference]:
    """Highest first; agent weights swap pairs and value ranks rotate by floor(n/2).

    The transform retains the legacy rank rule, fixing odd issue counts and early
    rounding. It is a configurable conflict construction, not a maximal-conflict proof.
    """
    names = {i.name for i in domain.issues}
    if len(issue_order) != len(names) or set(issue_order) != names or set(value_order) != names:
        raise ValueError("Rank every issue exactly once.")
    for issue in domain.issues:
        rank = value_order[issue.name]
        expected = int if domain.allocation else str
        if (
            any(type(v) is not expected for v in rank)
            or len(rank) != len(issue.values)
            or set(rank) != set(issue.values)
        ):
            raise ValueError(f"Rank every value of {issue.name} exactly once.")
    n = len(issue_order)
    total = n * (n + 1) / 2
    paired = list(range(n))
    for index in range(0, n - 1, 2):
        paired[index], paired[index + 1] = paired[index + 1], paired[index]
    human_weights = {name: (n - i) / total for i, name in enumerate(issue_order)}
    agent_weights = {name: (n - paired[i]) / total for i, name in enumerate(issue_order)}
    human_scores, agent_scores = {}, {}
    for name in issue_order:
        values = list(value_order[name])
        size = len(values)
        ranks = list(range(size))
        rotated = ranks[size // 2 :] + ranks[: size // 2]
        human_scores[name] = {value: (size - i) / size for i, value in enumerate(values)}
        agent_scores[name] = {value: (size - rotated[i]) / size for i, value in enumerate(values)}
    return (
        Preference(
            domain, human_weights, human_scores, "elicited", conversion="rank-linear-paired-v1"
        ),
        Preference(
            domain, agent_weights, agent_scores, "assigned", conversion="rank-linear-paired-v1"
        ),
    )
