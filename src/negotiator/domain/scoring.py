"""Distinguish additive utility, aspirational targets, and an experiment's reward rule."""

from collections.abc import Mapping

from .preferences import finite_number


def validate_thresholds(values: Mapping[str, float]) -> None:
    if set(values) - {"human", "agent"}:
        raise ValueError("Score rules may name only human and agent.")
    if any(not 0 <= finite_number(v, "Score threshold") <= 1 for v in values.values()):
        raise ValueError("Score thresholds must lie in [0, 1].")


def reward_scores(
    utilities: Mapping[str, float] | None, minimums: Mapping[str, float], reason: str
) -> dict[str, float] | None:
    validate_thresholds(minimums)
    if utilities is None:
        return {"human": 0.0, "agent": 0.0} if reason == "deadline" else None
    return {
        actor: value if value >= minimums.get(actor, 0) else 0.0
        for actor, value in utilities.items()
    }
